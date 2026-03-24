# GKE 1.31→1.32 Upgrade Plan with Istio Service Mesh

## Executive Summary

Service mesh upgrades require careful sequencing to avoid breaking inter-service communication. The key is ensuring Istio control plane compatibility BEFORE upgrading the GKE data plane (nodes), then validating mesh connectivity at each step.

**Critical insight:** Istio has specific GKE version support matrices. An incompatible Istio version can cause widespread service failures during or after the upgrade.

## Pre-Upgrade: Istio Compatibility Check

**First, verify your Istio version supports GKE 1.32:**

```bash
# Check current Istio version
kubectl get pods -n istio-system -l app=istiod -o jsonpath='{.items[0].spec.containers[0].image}'

# Check Istio release notes for GKE 1.32 support
# Istio 1.18+ generally supports K8s 1.31-1.32
# Istio 1.17 and below may not support K8s 1.32
```

**If your Istio version is older than 1.18, you MUST upgrade Istio first:**

1. Upgrade Istio to a version that supports both 1.31 and 1.32 (e.g., Istio 1.19+)
2. Validate mesh connectivity works on GKE 1.31 + new Istio
3. Then proceed with GKE upgrade

## Recommended Upgrade Sequence

### Phase 1: Control Plane Upgrade (Low Risk)
The GKE control plane upgrade is relatively safe for Istio since the data plane (sidecars) doesn't change yet.

```bash
# Set maintenance exclusion to prevent node auto-upgrades during CP upgrade
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "mesh-upgrade-protection" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time $(date -u -d "+7 days" +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Upgrade control plane only
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.latest
```

**Validation:**
```bash
# Verify control plane version
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"

# Check Istio control plane health
kubectl get pods -n istio-system
kubectl get mutatingwebhookconfigurations | grep istio
```

### Phase 2: Istio Sidecar Validation (Critical)
Before upgrading nodes, test that Istio sidecars work with the new API server.

```bash
# Deploy a test workload to trigger sidecar injection
kubectl create namespace mesh-upgrade-test
kubectl label namespace mesh-upgrade-test istio-injection=enabled

kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-mesh-app
  namespace: mesh-upgrade-test
spec:
  replicas: 2
  selector:
    matchLabels:
      app: test-mesh-app
  template:
    metadata:
      labels:
        app: test-mesh-app
    spec:
      containers:
      - name: app
        image: nginx:1.21
        ports:
        - containerPort: 80
---
apiVersion: v1
kind: Service
metadata:
  name: test-mesh-svc
  namespace: mesh-upgrade-test
spec:
  selector:
    app: test-mesh-app
  ports:
  - port: 80
EOF

# Verify sidecar injection works
kubectl get pods -n mesh-upgrade-test -o jsonpath='{.items[*].spec.containers[*].name}'
# Should show both 'app' and 'istio-proxy'

# Test service-to-service communication
kubectl exec -n mesh-upgrade-test deployment/test-mesh-app -c app -- \
  curl -v http://test-mesh-svc.mesh-upgrade-test.svc.cluster.local
```

**Red flags to watch for:**
- Webhook admission failures: "admission webhook rejected the request"
- Sidecar injection failures: pods only have 1 container instead of 2
- mTLS certificate errors in Istio logs
- 503 errors between services

### Phase 3: Node Pool Upgrade Strategy

For service mesh, **autoscaled blue-green** is strongly preferred over surge upgrades:

**Why autoscaled blue-green for Istio:**
- Avoids breaking active connections during pod restarts
- Allows time for new sidecars to join the mesh before old ones leave
- Reduces certificate rotation timing issues
- Provides easy rollback if mesh connectivity breaks

```bash
# Configure autoscaled blue-green upgrade
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 3 \
  --total-max-nodes 20 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

# Trigger node pool upgrade
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**Alternative for quota-constrained environments:**
If you can't afford 2x node capacity, use conservative surge:
```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### Phase 4: Real-time Monitoring During Node Upgrade

Watch these metrics continuously during the upgrade:

```bash
# Monitor mesh connectivity
kubectl exec -n istio-system deployment/istiod -- \
  pilot-discovery proxy-status | grep -c "SYNCED"

# Check for certificate issues
kubectl logs -n istio-system -l app=istiod --tail=100 | grep -i "certificate\|tls\|handshake"

# Watch for admission webhook failures
kubectl get events -A --field-selector type=Warning | grep webhook

# Monitor service response codes (if you have observability)
# Look for spikes in 503, 502, or connection refused errors
```

## Istio-Specific Gotchas

### 1. Webhook Compatibility Issues
After the control plane upgrade, Istio's admission webhooks might reject pod creation due to API version changes.

**Symptoms:**
- New pods fail to start with "admission webhook rejected the request"
- Sidecar injection inconsistencies

**Fix:**
```bash
# Check webhook configurations
kubectl get mutatingwebhookconfigurations istio-sidecar-injector -o yaml | grep apiVersion

# If webhook API versions are outdated, restart Istio control plane
kubectl rollout restart deployment/istiod -n istio-system
```

### 2. Certificate Rotation During Upgrade
Istio certificates may need renewal during the extended upgrade window.

**Monitor:**
```bash
# Check certificate expiry
kubectl get secret -n istio-system istio-ca-secret -o jsonpath='{.data.cert-chain\.pem}' | base64 -d | openssl x509 -noout -dates

# Watch for certificate rotation events
kubectl get events -n istio-system | grep certificate
```

### 3. Service Discovery Lag
New nodes joining the mesh may have delayed service discovery, causing temporary 503s.

**Monitor:**
```bash
# Check Envoy configuration sync
kubectl exec -n NAMESPACE PODNAME -c istio-proxy -- \
  pilot-agent request GET /config_dump | grep -A5 -B5 "version_info"
```

### 4. Load Balancer Health Check Changes
GKE 1.32 may change how load balancer health checks interact with Istio gateways.

**Test after upgrade:**
```bash
# Verify ingress gateway health
kubectl get pods -n istio-system -l app=istio-proxy
kubectl logs -n istio-system -l app=istio-proxy | grep -i health
```

## Rollback Strategy

If mesh connectivity breaks during the upgrade:

**For control plane issues:**
```bash
# Revert to previous Istio version (if you upgraded Istio first)
istioctl install --set values.pilot.image=PREVIOUS_VERSION

# Or patch webhook failure policy to non-blocking temporarily
kubectl patch mutatingwebhookconfigurations istio-sidecar-injector \
  -p '{"webhooks":[{"name":"rev.namespace.sidecar-injector.istio.io","failurePolicy":"Ignore"}]}'
```

**For node upgrade issues:**
- Blue-green upgrades support easy rollback: uncordon the old (blue) node pool
- For surge upgrades: create a new node pool at 1.31, migrate workloads, delete upgraded pool

## Post-Upgrade Validation Checklist

```markdown
Service Mesh Validation
- [ ] All Istio control plane pods running: `kubectl get pods -n istio-system`
- [ ] Sidecar injection working: test pod shows 2 containers (app + istio-proxy)
- [ ] Service-to-service mTLS working: `kubectl logs -c istio-proxy POD | grep "connection established"`
- [ ] No webhook admission failures in events
- [ ] External traffic flowing through ingress gateways
- [ ] Certificate rotation completing normally
- [ ] Service discovery converged: no 503 errors between known services
- [ ] Observability (metrics, traces) flowing to Jaeger/Prometheus
- [ ] Circuit breakers and retry policies functioning
```

## Key Takeaways

1. **Istio compatibility check is mandatory** — verify before starting
2. **Control plane first, nodes second** — never upgrade them simultaneously
3. **Use autoscaled blue-green** for mesh workloads when possible
4. **Monitor certificates and webhooks** in real-time during the upgrade
5. **Keep the maintenance exclusion** until you've validated full mesh connectivity
6. **Test with non-production traffic first** if you have staging mesh environments

Remove the maintenance exclusion only after confirming the mesh is fully functional:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "mesh-upgrade-protection"
```

This conservative approach minimizes the risk of breaking inter-service communication during the upgrade.
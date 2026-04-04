# GKE + Istio Upgrade Plan: 1.31 → 1.32

Service mesh upgrades require careful sequencing to avoid breaking traffic routing and sidecar injection. Here's the safe upgrade path:

## Pre-Upgrade Checklist

```markdown
- [ ] Cluster: ___ | Mode: Standard | Channel: ___
- [ ] Current GKE: 1.31 | Target GKE: 1.32
- [ ] Current Istio version: ___ | Target Istio version: ___

Istio Compatibility
- [ ] Verify Istio control plane version supports Kubernetes 1.32
- [ ] Check Istio release notes for 1.32 compatibility matrix
- [ ] Identify if Istio upgrade is required (control plane + data plane)
- [ ] Review breaking changes in target Istio version
- [ ] Backup Istio configuration: `kubectl get -o yaml -n istio-system gateway,virtualservice,destinationrule > istio-config-backup.yaml`

Mesh Health Baseline
- [ ] Capture current mesh metrics (success rates, latency p99)
- [ ] Document current Istio proxy versions: `kubectl get pods -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[?(@.name=="istio-proxy")].image}{"\n"}' --all-namespaces`
- [ ] Verify all workloads have sidecar injection: `kubectl get pods --all-namespaces -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.spec.containers[*].name}{"\n"}' | grep istio-proxy`
- [ ] Test traffic flows and service discovery work correctly

Workload Readiness
- [ ] PDBs configured for critical services
- [ ] No bare pods — all managed by controllers
- [ ] Admission webhooks compatibility verified (especially istio-sidecar-injector)
- [ ] Custom Envoy filters reviewed for API changes
```

## Upgrade Sequence (Critical Order)

### Phase 1: Control Plane Preparation
**Before touching GKE**, ensure your service mesh can handle the new Kubernetes version:

```bash
# 1. Check Istio compatibility with K8s 1.32
# Refer to: https://istio.io/latest/docs/releases/supported-releases/

# 2. If Istio upgrade needed, do it BEFORE GKE upgrade
# Example for Istio 1.20+ (adjust for your version):
istioctl upgrade --set values.pilot.env.EXTERNAL_ISTIOD=false

# 3. Verify control plane health
kubectl get pods -n istio-system
istioctl proxy-status
```

### Phase 2: GKE Control Plane Upgrade

```bash
# Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.0-gke.LATEST

# Verify control plane upgrade successful
kubectl get pods -n istio-system
istioctl version
```

**Critical validation after CP upgrade:**
```bash
# Check admission webhooks still working
kubectl get mutatingwebhookconfigurations | grep istio
kubectl describe mutatingwebhookconfigurations istio-sidecar-injector

# Test sidecar injection on new pod
kubectl run test-injection --image=nginx --restart=Never --labels="test=injection" -n default
kubectl get pod test-injection -o yaml | grep -A5 -B5 istio-proxy
kubectl delete pod test-injection
```

### Phase 3: Node Pool Upgrade Strategy

For service mesh, **autoscaled blue-green is strongly recommended** over surge:

**Why blue-green for Istio:**
- Avoids traffic disruption during sidecar restarts
- Preserves mesh topology during transition
- Allows validation before cutting over
- Quick rollback if service discovery breaks

```bash
# Configure autoscaled blue-green upgrade
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --enable-blue-green-upgrade \
  --node-pool-soak-duration=3600s \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25

# Start node pool upgrade
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.0-gke.LATEST
```

## Service Mesh Validation During Upgrade

### Monitor these metrics throughout:

```bash
# 1. Mesh connectivity health
istioctl proxy-status

# 2. Service discovery working
kubectl get endpoints -A | grep -v "<none>"

# 3. Certificate rotation not broken
kubectl exec -n istio-system deployment/istiod -- \
  pilot-discovery request GET /debug/syncz

# 4. Traffic success rates maintained
# Check your observability stack (Prometheus/Grafana)
# Key metrics: istio_request_total, istio_request_duration_milliseconds
```

### Smoke tests for each upgraded batch:
```bash
# Test internal service-to-service calls
kubectl exec -it deployment/APP_NAME -c APP_CONTAINER -- \
  curl -v http://SERVICE_NAME.NAMESPACE.svc.cluster.local:PORT/health

# Test ingress traffic
curl -v -H "Host: YOUR_DOMAIN" http://INGRESS_IP/health
```

## Common Istio + GKE Upgrade Pitfalls

### 1. Admission Webhook Certificate Issues
**Symptom:** Pods fail to create with "admission webhook rejected the request"

**Fix:**
```bash
# Check webhook status
kubectl get mutatingwebhookconfigurations istio-sidecar-injector -o yaml

# If cert issues, restart webhook pods
kubectl rollout restart deployment/istiod -n istio-system

# Temporary workaround (use carefully):
kubectl patch mutatingwebhookconfigurations istio-sidecar-injector \
  -p '{"webhooks":[{"name":"rev.namespace.sidecar-injector.istio.io","failurePolicy":"Ignore"}]}'
```

### 2. Envoy Proxy Version Skew
**Symptom:** Mixed proxy versions causing connection issues

**Monitor proxy versions:**
```bash
# Check all sidecar versions
kubectl get pods --all-namespaces -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.spec.containers[?(@.name=="istio-proxy")].image}{"\n"}' | sort | uniq -c
```

**Fix:** Force sidecar updates by restarting workloads:
```bash
kubectl rollout restart deployment/APP_NAME -n NAMESPACE
```

### 3. Service Discovery Breaking
**Symptom:** Services can't find each other, DNS resolution fails

**Diagnose:**
```bash
# Check Envoy cluster config
istioctl proxy-config cluster POD_NAME.NAMESPACE

# Check endpoints
kubectl get endpoints SERVICE_NAME -n NAMESPACE -o yaml
```

### 4. Custom Resources API Changes
**Symptom:** VirtualServices, DestinationRules fail to apply

**Fix:** Update CRDs if Istio was upgraded:
```bash
istioctl install --set values.pilot.env.EXTERNAL_ISTIOD=false --skip-confirmation
```

## Rollback Strategy

If mesh connectivity breaks:

### Immediate mitigation:
```bash
# 1. Scale problematic services to already-upgraded nodes
kubectl patch deployment APP_NAME -p '{"spec":{"template":{"spec":{"nodeSelector":{"cloud.google.com/gke-node-version":"1.32.0-gke.LATEST"}}}}}'

# 2. If that fails, bypass mesh temporarily
kubectl label namespace NAMESPACE istio-injection-
kubectl rollout restart deployment/APP_NAME -n NAMESPACE
```

### Full rollback (if needed):
```bash
# 1. Complete blue-green upgrade immediately to stabilize
gcloud container node-pools complete-upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE

# 2. If Istio was upgraded, consider control plane downgrade
# (Requires careful planning - contact Istio community)
```

## Post-Upgrade Validation Checklist

```markdown
- [ ] All nodes at 1.32: `kubectl get nodes`
- [ ] Istio control plane healthy: `kubectl get pods -n istio-system`
- [ ] All sidecars injected: `istioctl proxy-status`
- [ ] Service discovery working: `kubectl get endpoints -A | grep -v "<none>"`
- [ ] Traffic success rates ≥ pre-upgrade baseline
- [ ] Latency p99 ≤ pre-upgrade baseline + 10%
- [ ] Ingress gateways responding
- [ ] mTLS certificates rotating properly
- [ ] Custom Envoy filters still applied
- [ ] Jaeger/observability pipeline intact
```

## Key Takeaways

1. **Upgrade Istio control plane BEFORE GKE** if compatibility requires it
2. **Use blue-green node upgrades** to minimize mesh disruption
3. **Monitor service discovery continuously** during the upgrade
4. **Test admission webhooks** immediately after control plane upgrade
5. **Have bypass strategies ready** if mesh connectivity breaks
6. **Validate each phase** before proceeding to the next

The mesh adds complexity, but following this sequence minimizes the blast radius. The soak period in blue-green gives you time to validate mesh health before fully cutting over.
# GKE 1.31→1.32 Upgrade Plan with Istio Service Mesh

## Executive Summary

Service mesh upgrades require careful sequencing to avoid breaking mTLS, policy enforcement, and traffic routing. The key principle: **upgrade Istio control plane FIRST, then GKE control plane, then nodes**. This ensures compatibility at each step and provides rollback points.

## Upgrade Sequence & Compatibility

### Step 1: Verify Istio Version Compatibility
```bash
# Check current Istio version
kubectl get pods -n istio-system -l app=istiod -o jsonpath='{.items[0].spec.containers[0].image}'

# Verify Istio supports Kubernetes 1.32
# Istio 1.19+ supports K8s 1.28-1.32
# Istio 1.20+ supports K8s 1.29-1.32
# Istio 1.21+ supports K8s 1.30-1.32
```

**Critical compatibility check:** If you're running Istio <1.19, you MUST upgrade Istio first. K8s 1.32 requires Istio 1.19+ for full compatibility.

### Step 2: Upgrade Istio Control Plane (if needed)
```bash
# Download target Istio version
curl -L https://istio.io/downloadIstio | ISTIO_VERSION=1.21.0 sh -

# Upgrade control plane (canary approach)
istioctl install --revision 1-21-0 --set values.pilot.env.PILOT_ENABLE_CROSS_CLUSTER_WORKLOAD_ENTRY=true

# Verify new control plane
kubectl get pods -n istio-system -l app=istiod --show-labels
```

**Important:** Use revision-based upgrades (`--revision`) rather than in-place. This allows gradual workload migration and easy rollback.

### Step 3: Migrate Critical Workloads to New Istio Revision
```bash
# Label namespace for new revision
kubectl label namespace NAMESPACE istio.io/rev=1-21-0 istio-injection- --overwrite

# Restart workloads to pick up new sidecars
kubectl rollout restart deployment -n NAMESPACE
kubectl rollout restart daemonset -n NAMESPACE

# Verify sidecar versions
kubectl get pods -n NAMESPACE -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[1].image}{"\n"}{end}'
```

### Step 4: Configure GKE Maintenance Controls
```bash
# Set maintenance window for controlled timing
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Optional: Add "no minor or node upgrades" exclusion for maximum control
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "istio-upgrade-control" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

### Step 5: GKE Control Plane Upgrade
```bash
# Upgrade control plane to 1.32
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.0-gke.PATCH

# Verify control plane
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

### Step 6: Node Pool Upgrade Strategy
For service mesh, **surge upgrade with conservative settings** is recommended:

```bash
# Configure conservative surge settings
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# Upgrade node pools (skip-level: 1.31→1.32 directly)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.0-gke.PATCH
```

**Why conservative surge:** Service mesh workloads often have complex dependencies. Slow, controlled replacement gives time for mTLS certificate rotation, service discovery updates, and load balancer health checks.

## Service Mesh-Specific Risks & Mitigations

### 1. Admission Webhook Failures (highest risk)
**Problem:** Istio's mutating webhook may reject pod creation on K8s 1.32 if Istio version is incompatible.

**Mitigation:**
```bash
# Before GKE upgrade, test webhook compatibility
kubectl run test-pod --image=nginx --rm -it --restart=Never --dry-run=server -- echo "test"

# If webhook fails post-upgrade, temporarily set failurePolicy
kubectl patch mutatingwebhookconfigurations istio-sidecar-injector \
  -p '{"webhooks":[{"name":"rev.namespace.sidecar-injector.istio.io","failurePolicy":"Ignore"}]}'
```

### 2. Certificate Rotation During Node Replacement
**Problem:** Node replacement can disrupt Istio's automatic certificate rotation, causing mTLS failures.

**Monitoring:**
```bash
# Monitor certificate health
kubectl get secrets -A | grep istio

# Check for certificate rotation errors
kubectl logs -n istio-system -l app=istiod | grep -i certificate
```

### 3. Envoy Sidecar Version Skew
**Problem:** Old Envoy sidecars on new nodes may have incompatible configuration.

**Prevention:**
```bash
# Restart all workloads after node upgrade completes
kubectl get deployments -A -o name | xargs -I {} kubectl rollout restart {}

# Verify sidecar-istiod version compatibility
istioctl proxy-status
```

### 4. Load Balancer Health Check Disruption
**Problem:** Service mesh services may fail health checks during node transitions.

**Monitoring:**
```bash
# Monitor ingress gateway pods during upgrade
kubectl get pods -n istio-system -l app=istio-proxy -w

# Check load balancer backend health
kubectl describe service istio-ingressgateway -n istio-system
```

## Pre-Upgrade Checklist (Service Mesh Specific)

```markdown
Istio Compatibility & Readiness
- [ ] Current Istio version supports Kubernetes 1.32: ___
- [ ] Istio control plane healthy: `kubectl get pods -n istio-system`
- [ ] No failing webhook configurations: `kubectl get validatingwebhookconfigurations istio-validator`
- [ ] Sidecar injection working: test pod creation in istio-enabled namespace
- [ ] mTLS certificates rotating properly: `istioctl authn tls-check SERVICE`
- [ ] Ingress gateway pods healthy and receiving traffic

Workload Protection
- [ ] PDBs configured for critical services (especially databases behind mesh)
- [ ] Circuit breakers and retry policies configured in DestinationRules
- [ ] Health checks aligned with K8s probes (`/health`, `/ready`)
- [ ] No bare pods in istio-enabled namespaces

Observability
- [ ] Prometheus/Grafana capturing mesh metrics
- [ ] Jaeger/Zipkin tracing active (if used)  
- [ ] Kiali dashboard monitoring service topology
- [ ] Alert rules for mesh control plane components

Multi-Cluster (if applicable)
- [ ] Cross-cluster certificate trust bundles updated
- [ ] Network connectivity between clusters verified
- [ ] Pilot discovery endpoints accessible
```

## Monitoring During Upgrade

### Real-time mesh health
```bash
# Continuous monitoring script
while true; do
  echo "=== $(date) ==="
  echo "Control plane:"
  kubectl get pods -n istio-system --no-headers | grep -v Running || echo "All running"
  
  echo "Webhook health:"
  kubectl run test-webhook --image=nginx --rm -i --restart=Never --dry-run=server >/dev/null 2>&1 && echo "OK" || echo "FAILED"
  
  echo "Certificate status:"
  istioctl proxy-status | head -5
  
  sleep 30
done
```

### Key metrics to watch
- **Sidecar proxy connection rate:** Should remain stable
- **Certificate rotation errors:** Zero tolerance
- **5xx error rate:** Should not spike beyond baseline
- **Control plane CPU/memory:** May spike during node transitions

## Rollback Strategy

### If Istio control plane issues arise:
```bash
# Rollback to previous Istio revision
kubectl label namespace NAMESPACE istio.io/rev=PREVIOUS_REVISION --overwrite
kubectl rollout restart deployment -n NAMESPACE

# Remove failed revision
istioctl uninstall --revision FAILED_REVISION
```

### If GKE upgrade causes mesh issues:
1. **Cannot rollback control plane** (requires GKE support)
2. **Node pools can be rolled back:**
```bash
# Create new node pool at 1.31
gcloud container node-pools create rollback-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.0-gke.LATEST \
  --num-nodes 3

# Cordon 1.32 nodes, drain to 1.31 nodes
kubectl cordon -l cloud.google.com/gke-nodepool=ORIGINAL_POOL
```

## Common Failure Scenarios & Fixes

### Scenario 1: Pods stuck in "ContainerCreating"
```bash
# Check sidecar injection issues
kubectl describe pod POD_NAME | grep -A 10 Events

# Common fix: restart istiod
kubectl rollout restart deployment/istiod -n istio-system
```

### Scenario 2: mTLS failures between services
```bash
# Check certificate status
istioctl authn tls-check SERVICE_A.NAMESPACE.svc.cluster.local SERVICE_B.NAMESPACE.svc.cluster.local

# Force certificate refresh
kubectl delete secret -n istio-system cacerts
```

### Scenario 3: Ingress gateway not receiving traffic
```bash
# Check gateway configuration
istioctl analyze -n istio-system

# Verify load balancer backend health
kubectl get service istio-ingressgateway -n istio-system -o wide
```

## Post-Upgrade Validation

```bash
# Comprehensive mesh validation
istioctl analyze --all-namespaces
istioctl proxy-status
kubectl get pods -n istio-system
kubectl get gateways,virtualservices,destinationrules -A

# Traffic validation
curl -H "Host: your-app.com" http://INGRESS_IP/health
kubectl exec -it SOME_POD -- curl service-b:8080/api/health
```

## Key Takeaways

1. **Upgrade Istio FIRST** if running <1.19 — K8s 1.32 compatibility requirement
2. **Use revision-based Istio upgrades** for safe rollback capability  
3. **Conservative node upgrade settings** (maxSurge=2) for service mesh stability
4. **Monitor admission webhooks** — most common failure point
5. **Restart all workloads** after node upgrade to refresh sidecar versions
6. **Never skip the staging validation** — test the exact upgrade sequence in dev/staging first

The horror stories usually come from skipping the Istio compatibility check or upgrading everything simultaneously. This sequential approach with validation gates minimizes risk.
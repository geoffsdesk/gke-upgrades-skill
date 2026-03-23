# GKE + Istio Upgrade Plan: 1.31 → 1.32

## Executive Summary
Istio mesh upgrades require careful sequencing: **GKE infrastructure first, then Istio control plane**. The key risk is version skew between GKE's underlying Kubernetes APIs and Istio's expectations.

## Pre-Flight: Version Compatibility Check

```bash
# Check current Istio version
kubectl get pods -n istio-system -l app=istiod -o jsonpath='{.items[0].spec.containers[0].image}'

# Verify Istio 1.32 compatibility
# Istio follows K8s N-2 support policy
```

**Critical compatibility matrix:**
- **GKE 1.32** → Requires **Istio 1.20+** (minimum)
- **Istio 1.22+** → Recommended for GKE 1.32 (full compatibility)
- **Istio < 1.20** → Must upgrade Istio first before GKE

If your Istio version is < 1.20, **stop here** and upgrade Istio first.

## Upgrade Sequence (MANDATORY ORDER)

### Phase 1: GKE Infrastructure Upgrade
**Why first?** Istio needs the updated Kubernetes APIs available in 1.32.

#### 1.1 Control Plane Upgrade
```bash
# Pre-flight mesh health
kubectl get pods -n istio-system
kubectl get virtualservices,destinationrules,gateways -A

# Upgrade control plane
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.latest

# Wait for completion (~10-15 min)
```

#### 1.2 Node Pool Upgrade Strategy
**Conservative approach for mesh workloads:**
```bash
# Configure surge settings (minimize disruption)
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade node pools one at a time
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**Why conservative?** Istio sidecars need to reconnect to the control plane during node restarts. High churn can cause temporary mesh partitioning.

### Phase 2: Post-GKE Validation
```bash
# Verify mesh connectivity BEFORE Istio upgrade
kubectl exec -n NAMESPACE PODNAME -c istio-proxy -- \
  curl -s localhost:15000/clusters | grep cx_active

# Check Envoy admin interface
kubectl port-forward -n istio-system istiod-xxx 15014:15014
# Visit localhost:15014/debug/syncz
```

### Phase 3: Istio Control Plane Upgrade
**Only after GKE is fully upgraded and validated.**

```bash
# Download target Istio version
curl -L https://istio.io/downloadIstio | ISTIO_VERSION=1.22.x TARGET_ARCH=x86_64 sh -

# Canary upgrade (recommended)
istioctl install --set values.pilot.env.EXTERNAL_ISTIOD=false --set revision=1-22-x

# Or in-place upgrade (higher risk)
istioctl upgrade
```

### Phase 4: Data Plane (Sidecar) Upgrade
```bash
# Rolling restart to pick up new sidecars
kubectl rollout restart deployment -n NAMESPACE

# Verify sidecar versions
kubectl get pods -n NAMESPACE -o jsonpath='{.items[*].spec.containers[?(@.name=="istio-proxy")].image}'
```

## Mesh-Specific Gotchas

### 1. Envoy Version Skew
**Problem:** GKE 1.32 may ship a different Envoy version than your current Istio expects.
**Mitigation:** Upgrade Istio control plane immediately after GKE nodes to sync Envoy versions.

### 2. RBAC Policy Changes
**Problem:** Kubernetes RBAC updates in 1.32 may affect Istio's cluster access.
**Check:**
```bash
kubectl auth can-i get pods --as=system:serviceaccount:istio-system:istiod
```

### 3. Admission Controller Conflicts
**Problem:** Multiple admission webhooks (GKE + Istio) can conflict during upgrades.
**Mitigation:**
```bash
# Check webhook configurations
kubectl get validatingwebhookconfigurations | grep istio
kubectl get mutatingwebhookconfigurations | grep istio

# Temporarily reduce webhook scope if needed
```

### 4. Service Mesh Interface (SMI) Breaking Changes
If using SMI resources, verify compatibility between GKE 1.32 CRD validation and your SMI version.

### 5. CNI Plugin Interactions
**GKE 1.32 CNI changes may affect Istio networking:**
```bash
# Post-upgrade: verify pod-to-pod mesh connectivity
kubectl exec -it pod1 -- curl pod2.namespace.svc.cluster.local:8080/health

# Check iptables rules are intact
kubectl exec -it PODNAME -c istio-proxy -- iptables -L -n -t nat
```

## Pre-Upgrade Checklist

```markdown
- [ ] Istio version ≥ 1.20 (required for GKE 1.32)
- [ ] Istio upgrade plan prepared (target version identified)
- [ ] Baseline metrics captured: RPS, error rate, P99 latency
- [ ] Mesh topology documented (gateways, virtual services, destination rules)
- [ ] PDBs configured for Istio control plane (prevent istiod eviction)
- [ ] Canary deployment strategy ready for Istio upgrade
- [ ] Service mesh monitoring active (Kiali, Jaeger, Prometheus)
- [ ] Emergency circuit breaker plan (disable mesh if needed)
```

## Monitoring During Upgrade

### Critical Mesh Metrics
```bash
# Istio control plane health
kubectl get pods -n istio-system
kubectl logs -n istio-system -l app=istiod --tail=50

# Envoy proxy health per pod
kubectl exec PODNAME -c istio-proxy -- curl localhost:15000/ready

# Certificate rotation status
kubectl exec PODNAME -c istio-proxy -- curl localhost:15000/certs

# Service discovery sync
curl localhost:15014/debug/syncz  # via port-forward to istiod
```

### Red Flags to Watch
- **503 errors** → Service discovery issues
- **Connection refused** → Envoy startup problems  
- **Certificate errors** → mTLS certificate rotation failure
- **High memory usage in istiod** → Configuration explosion

## Emergency Rollback

### If Mesh Breaks During Node Upgrade:
```bash
# Bypass mesh temporarily
kubectl label namespace NAMESPACE istio-injection-

# Restart deployments without sidecars
kubectl rollout restart deployment -n NAMESPACE

# Re-enable after fixing
kubectl label namespace NAMESPACE istio-injection=enabled
```

### If Istio Control Plane Fails:
```bash
# Rollback Istio (if canary upgrade)
istioctl tag remove 1-22-x
kubectl delete deployment -n istio-system istiod-1-22-x

# Emergency: disable admission webhooks
kubectl delete mutatingwebhookconfigurations istio-sidecar-injector
```

## Success Validation

```bash
# End-to-end mesh connectivity test
kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: mesh-test
  labels:
    app: mesh-test
spec:
  containers:
  - name: curl
    image: curlimages/curl
    command: ['sleep', '3600']
EOF

# Test service-to-service calls through mesh
kubectl exec mesh-test -- curl -v other-service.namespace.svc.cluster.local:8080

# Verify mTLS is active
kubectl exec mesh-test -c istio-proxy -- \
  curl localhost:15000/clusters | grep -o "ssl.*cx_active.*"
```

## Timeline Estimate
- **GKE control plane:** 10-15 minutes
- **Node pool upgrade:** 2-4 hours (depends on cluster size)
- **Istio control plane:** 15-30 minutes  
- **Data plane restart:** 30-60 minutes
- **Total:** 4-6 hours for complete upgrade + validation

**Recommendation:** Plan a 8-hour maintenance window to account for troubleshooting time.

The key is **never rushing the Istio upgrade** — let GKE settle completely first, validate mesh connectivity, then upgrade Istio control plane as a separate operation.
# GKE + Istio Upgrade Plan: 1.31 → 1.32

## Executive Summary

Istio mesh upgrades require careful sequencing — **control plane first, then data plane** — with validation at each step. The key risk is version skew between Istio components and incompatible sidecar proxies after the GKE upgrade.

## Upgrade Strategy: Istio-First Approach

**Recommended sequence:**
1. Upgrade Istio control plane to version compatible with GKE 1.32
2. Upgrade GKE control plane to 1.32
3. Upgrade GKE node pools to 1.32 
4. Upgrade Istio data plane (sidecar proxies)

This "Istio-first" approach ensures the mesh control plane can handle both old and new Kubernetes APIs during the transition.

## Pre-Flight Checks

```markdown
## Istio + GKE Compatibility Check
- [ ] Current Istio version: `istioctl version`
- [ ] Current GKE version: 1.31.x
- [ ] Target GKE version: 1.32.x
- [ ] Verify Istio version compatibility with GKE 1.32 ([Istio supported releases](https://istio.io/latest/docs/releases/supported-releases/))
- [ ] Check Istio release notes for breaking changes between current → target Istio version

## Mesh Health Baseline
- [ ] All Istio control plane pods healthy: `kubectl get pods -n istio-system`
- [ ] Proxy status clean: `istioctl proxy-status`
- [ ] Configuration sync status: `istioctl proxy-config cluster -n istio-system`
- [ ] No configuration conflicts: `istioctl analyze --all-namespaces`
- [ ] Capture baseline metrics: traffic success rate, latency p99, mesh certificate status

## Data Plane Inventory
- [ ] Count injected workloads: `kubectl get pods -A -l istio.io/rev --no-headers | wc -l`
- [ ] Identify revision labels: `kubectl get namespaces -l istio.io/rev`
- [ ] Check for manual sidecar injection: `kubectl get pods -A -l sidecar.istio.io/inject=true`
- [ ] Catalog critical services using mesh (ingress gateways, high-traffic services)
```

## Version Compatibility Matrix

| GKE Version | Compatible Istio Versions | Notes |
|-------------|---------------------------|-------|
| 1.31.x | 1.19.x, 1.20.x, 1.21.x | Current state |
| 1.32.x | 1.20.x, 1.21.x, 1.22.x | Target state |

**Key insight:** Istio 1.20.x+ should work with both GKE 1.31 and 1.32, making it a safe bridge version.

## Step-by-Step Upgrade Runbook

### Phase 1: Istio Control Plane Upgrade

```bash
# 1. Check current Istio version
istioctl version

# 2. Download target Istio version (compatible with GKE 1.32)
curl -L https://istio.io/downloadIstio | ISTIO_VERSION=1.21.0 sh -
cd istio-1.21.0/bin

# 3. Canary upgrade approach - install new control plane revision
./istioctl install --set values.pilot.env.EXTERNAL_ISTIOD=false \
  --set revision=1-21-0 \
  --set values.defaultRevision=""

# 4. Verify new control plane
kubectl get pods -n istio-system -l app=istiod
./istioctl proxy-status
```

**Validation checkpoint:**
```bash
# Both old and new control planes should be running
kubectl get pods -n istio-system | grep istiod
# Existing workloads should still show healthy proxy status
./istioctl proxy-status | grep SYNCED
```

### Phase 2: GKE Control Plane Upgrade

```bash
# Configure maintenance window (if not already set)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start 2024-01-20T02:00:00Z \
  --maintenance-window-end 2024-01-20T06:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Upgrade control plane
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.0-gke.1234

# Monitor progress (~10-15 min)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

**Validation checkpoint:**
```bash
# Verify Istio control plane unaffected by K8s API changes
kubectl get pods -n istio-system
istioctl proxy-config cluster -n istio-system istiod-xxx | head -20
# Check for any configuration sync issues
istioctl analyze --all-namespaces
```

### Phase 3: GKE Node Pool Upgrade

```bash
# Configure conservative surge settings for mesh workloads
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade node pools
gcloud container node-pools upgrade default-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.0-gke.1234

# Monitor mesh connectivity during node replacement
watch 'kubectl get pods -A | grep -E "(istio-proxy|Running|Terminating)"'
```

**Critical monitoring during node upgrades:**
```bash
# Watch for mesh connectivity issues during pod rescheduling
istioctl proxy-status | grep -v SYNCED
kubectl get pods -A | grep -E "(CrashLoopBackOff|ImagePullBackOff)"

# Monitor ingress gateway pod distribution
kubectl get pods -n istio-system -l app=istio-proxy -o wide
```

### Phase 4: Istio Data Plane Upgrade (Sidecar Proxies)

This is the highest-risk phase — rolling restart of all meshed workloads.

```bash
# Option A: Namespace-by-namespace (recommended for production)
# Label namespace for new Istio revision
kubectl label namespace NAMESPACE_NAME istio.io/rev=1-21-0 --overwrite
kubectl label namespace NAMESPACE_NAME istio.io/rev- # Remove old label if present

# Restart workloads to pick up new sidecars
kubectl rollout restart deployment -n NAMESPACE_NAME
kubectl rollout status deployment -n NAMESPACE_NAME --timeout=300s

# Option B: Automatic injection (higher risk, but faster)
# Set new revision as default
istioctl install --set values.defaultRevision=1-21-0

# Restart all injected workloads
kubectl get namespaces -l istio.io/rev -o name | \
  xargs -I {} kubectl rollout restart deployment -n {}
```

**Validation after each namespace:**
```bash
# Verify proxy version updated
istioctl proxy-status | grep 1.21.0
# Check service connectivity
kubectl exec -it deployment/sleep -- curl -s http://httpbin:8000/headers
# Verify certificates are valid
istioctl authn tls-check sleep.default.svc.cluster.local
```

### Phase 5: Cleanup

```bash
# Remove old Istio control plane (only after all workloads migrated)
istioctl uninstall --revision default
kubectl delete namespace istio-system # If completely empty
```

## Mesh-Specific Risks & Mitigations

### 1. Certificate Rotation During Upgrade
**Risk:** Istio's root CA certificates may become invalid during extended upgrades.
**Mitigation:** 
- Check certificate expiry: `istioctl authn tls-check`
- Monitor certificate chain: `istioctl proxy-config secret`
- Have certificate rotation playbook ready

### 2. Ingress Gateway Downtime
**Risk:** External traffic disruption when ingress gateway pods restart.
**Mitigation:**
```bash
# Ensure multiple gateway replicas across zones
kubectl get pods -n istio-system -l app=istio-proxy -o wide

# Use PDBs to prevent all gateways draining simultaneously  
kubectl get pdb -n istio-system
```

### 3. East-West Traffic Interruption
**Risk:** Service-to-service communication failures during sidecar upgrades.
**Mitigation:**
- Upgrade non-critical namespaces first (staging, dev tools)
- Validate each namespace before proceeding: `kubectl exec deployment/sleep -- curl service-name`
- Have circuit breaker/retry policies configured

### 4. Configuration Drift
**Risk:** Istio configuration becoming incompatible with new versions.
**Mitigation:**
```bash
# Run analysis before each phase
istioctl analyze --all-namespaces
# Check for deprecated APIs
kubectl api-resources | grep istio
```

### 5. Observability Gaps
**Risk:** Metrics/tracing pipeline disruption during control plane upgrade.
**Mitigation:**
- Verify Prometheus targets: `kubectl get pods -n istio-system -l app=prometheus`
- Check Jaeger connectivity: `istioctl dashboard jaeger`
- Monitor Envoy admin interfaces: `kubectl port-forward -n NAMESPACE pod/POD-NAME 15000:15000`

## Rollback Plan

If issues arise during data plane upgrade:

```bash
# Emergency rollback: revert namespace to previous Istio revision
kubectl label namespace NAMESPACE_NAME istio.io/rev=1-20-0 --overwrite
kubectl rollout restart deployment -n NAMESPACE_NAME

# If control plane issues: switch back to previous revision
istioctl install --set values.defaultRevision=1-20-0

# Verify rollback success
istioctl proxy-status
istioctl analyze --all-namespaces
```

## Post-Upgrade Validation

```markdown
## Mesh Health Verification
- [ ] All proxy versions updated: `istioctl proxy-status`
- [ ] No configuration conflicts: `istioctl analyze --all-namespaces`
- [ ] Certificate chain healthy: `istioctl authn tls-check`
- [ ] Ingress gateway responding: `curl -I https://your-gateway.example.com`
- [ ] East-west connectivity: `kubectl exec deployment/sleep -- curl service-name`
- [ ] Metrics collection active: check Prometheus/Grafana dashboards
- [ ] Distributed tracing working: verify spans in Jaeger/Zipkin

## Performance Validation
- [ ] Latency within baseline (mesh adds ~1-2ms overhead)
- [ ] Success rate maintained (>99.9% for critical services)
- [ ] No memory leaks in Envoy sidecars: `kubectl top pods -A --containers`
- [ ] CPU usage normal for istio-proxy containers
```

## Key Takeaways

1. **Istio-first approach** reduces risk by ensuring mesh compatibility before K8s API changes
2. **Canary control plane** upgrades let you test new Istio versions without disrupting existing workloads
3. **Conservative surge settings** (maxSurge=1) minimize simultaneous pod disruptions in the mesh
4. **Namespace-by-namespace** data plane upgrades provide granular rollback capability
5. **Continuous validation** at each phase prevents cascading failures

The mesh adds complexity, but following this sequence — Istio control plane → GKE control plane → GKE nodes → Istio data plane — minimizes the blast radius of any issues.
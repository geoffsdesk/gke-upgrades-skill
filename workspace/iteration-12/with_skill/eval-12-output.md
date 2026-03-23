# Istio + GKE Upgrade Plan: 1.31 → 1.32

## Executive Summary

**Recommended approach:** GKE first, then Istio. The key insight is that Istio's control plane runs as pods on your GKE nodes — upgrading GKE first ensures Istio has a stable foundation. Most "horror stories" come from skipping version compatibility checks or rushing through the Istio upgrade without proper validation.

**Risk level:** Medium — with proper sequencing and testing, this is a well-traveled path.

## Pre-Flight Compatibility Assessment

### Check current versions
```bash
# GKE cluster version
kubectl version --short

# Istio version
istioctl version

# Check if you're using Anthos Service Mesh (ASM) instead
kubectl get pods -n istio-system -l app=istiod -o jsonpath='{.items[0].metadata.labels.istio\.io/rev}'
```

### Istio 1.32 compatibility matrix
Istio follows Kubernetes support policy (current + 2 previous minors). For GKE 1.32:
- **Supported Istio versions:** 1.20.x, 1.21.x, 1.22.x, 1.23.x (latest)
- **If you're running Istio < 1.20:** You'll need to upgrade Istio BEFORE GKE 1.32
- **If you're running ASM:** Check the [ASM GKE compatibility matrix](https://cloud.google.com/service-mesh/docs/supported-features) — ASM has its own versioning

## Upgrade Sequence

### Phase 1: GKE Control Plane (Week 1)
```bash
# Configure maintenance exclusion to control timing
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "istio-upgrade-prep" \
  --add-maintenance-exclusion-start-time "2024-01-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-02-15T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Upgrade control plane only
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x
```

**Validation:**
```bash
kubectl get pods -n istio-system
# All Istio pods should remain healthy after CP upgrade
istioctl proxy-status
# All proxies should show SYNCED
```

### Phase 2: Node Pool Upgrade Preparation
Before upgrading nodes, configure surge settings for your workload profile:

```bash
# Default pools (stateless workloads)
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# If you have dedicated Istio gateway nodes
gcloud container node-pools update gateway-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### Phase 3: GKE Node Pool Upgrade (Week 2)
```bash
# Remove the maintenance exclusion to allow node upgrades
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "istio-upgrade-prep"

# Upgrade node pools (or let auto-upgrade handle it)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x
```

**Critical validation during node rollout:**
```bash
# Monitor Envoy proxy reconnections
kubectl logs -n istio-system -l app=istiod --tail=100 -f | grep -E "connection|disconnect"

# Check gateway pods survive node rollout
kubectl get pods -n istio-system -l app=istio-proxy -w

# Verify no traffic drops
kubectl top pods -n istio-system
```

### Phase 4: Istio Upgrade (Week 3-4)
Only after GKE upgrade is complete and validated.

```bash
# Download target Istio version (example: 1.23.0)
curl -L https://istio.io/downloadIstio | ISTIO_VERSION=1.23.0 sh -

# Install new Istio control plane alongside existing (canary upgrade)
istioctl install --revision=1-23-0 --set values.pilot.env.EXTERNAL_ISTIOD=false

# Gradually migrate workloads
kubectl label namespace production istio.io/rev=1-23-0 --overwrite
kubectl rollout restart deployment/app -n production

# Validate traffic flow, then remove old version
istioctl uninstall --revision=1-21-0
```

## Istio-Specific Risks & Mitigations

### 1. Envoy proxy version coupling
**Risk:** GKE node image updates may include newer Envoy builds that conflict with older Istio versions.

**Mitigation:**
- Test in a staging cluster first
- Check Envoy version after node upgrade: `kubectl exec -n istio-system ISTIOD_POD -- pilot-discovery version`
- If mismatch detected, expedite Istio upgrade

### 2. CNI plugin interactions
**Risk:** GKE uses Calico or Cilium CNI. Istio CNI plugin must remain compatible.

**Mitigation:**
```bash
# Check if using Istio CNI
kubectl get daemonset -n kube-system | grep istio-cni

# Monitor CNI pods during node upgrade
kubectl get pods -n kube-system -l k8s-app=istio-cni -w
```

### 3. Gateway disruption during node rollout
**Risk:** Ingress gateways lose connections when their nodes are replaced.

**Mitigation:**
```bash
# Ensure gateway PDBs are configured
kubectl get pdb -n istio-system

# If missing, create one:
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: istio-gateway
  namespace: istio-system
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: istio-proxy
      istio: gateway
```

### 4. Custom Istio configurations
**Risk:** Custom EnvoyFilters, VirtualServices, or Gateways may break with newer Envoy versions.

**Mitigation:**
- Audit custom resources: `kubectl get envoyfilters,virtualservices,gateways -A`
- Test complex routing rules in staging first
- Have rollback EnvoyFilters ready for common patterns

## Monitoring & Validation Checklist

### During GKE upgrade:
```markdown
- [ ] Istio control plane pods healthy: `kubectl get pods -n istio-system`
- [ ] Proxy sync status: `istioctl proxy-status | grep -v SYNCED`
- [ ] Gateway Load Balancer IP unchanged
- [ ] Sample requests flowing: `curl -v http://YOUR_GATEWAY_IP/health`
- [ ] Grafana/Kiali dashboards showing normal traffic
- [ ] No certificate rotation issues (check istio-proxy logs)
```

### Post-GKE, Pre-Istio upgrade:
```markdown
- [ ] All workloads running on GKE 1.32 nodes
- [ ] Istio metrics collection stable
- [ ] Custom CRDs still compatible: `kubectl get crd | grep istio`
- [ ] Service mesh traffic patterns normal (baseline for Istio upgrade)
```

## Rollback Strategy

### If GKE upgrade causes Istio issues:
1. **Node-level rollback:** Create new node pool at 1.31, migrate workloads, delete upgraded pool
2. **Istio restart:** `kubectl rollout restart deployment/istiod -n istio-system`
3. **Gateway recreation:** Delete and recreate gateway pods to clear connection state

### If Istio upgrade fails:
1. **Revision rollback:** Change namespace labels back to old revision
2. **Control plane cleanup:** `istioctl uninstall --revision=NEW_VERSION`

## ASM (Anthos Service Mesh) Differences

If you're using ASM instead of open-source Istio:

```bash
# Check if ASM managed
kubectl get controlplanerevision -n istio-system

# ASM follows different upgrade path
gcloud container fleet mesh update \
  --control-plane automatic \
  --data-plane automatic
```

ASM upgrades are Google-managed and follow GKE compatibility automatically. Less manual coordination needed.

## Timeline Recommendation

- **Week 1:** GKE control plane upgrade + validation
- **Week 2:** GKE node pool upgrade + Istio compatibility verification  
- **Week 3:** Istio control plane canary upgrade
- **Week 4:** Complete Istio data plane migration + cleanup

Total duration: ~1 month with proper soak time. Rushing this process is where most issues occur.

**Key success factor:** Stage the upgrades and validate thoroughly at each step. The "horror stories" usually involve doing both upgrades simultaneously or skipping compatibility validation.
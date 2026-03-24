# GKE + Istio Upgrade Plan: 1.31 → 1.32

## Executive Summary

The key to safe Istio upgrades is **sequencing**: upgrade GKE first, then Istio. This ensures Istio can leverage any new Kubernetes features while maintaining backward compatibility during the transition.

## Upgrade Sequence (Critical Order)

### Phase 1: GKE Control Plane Upgrade
### Phase 2: Istio Control Plane Upgrade  
### Phase 3: GKE Node Pool Upgrade
### Phase 4: Istio Data Plane Upgrade

This sequence minimizes risk by keeping the service mesh control plane stable during node churn.

## Pre-Upgrade Compatibility Check

**Critical:** Verify your current Istio version supports Kubernetes 1.32:

```bash
# Check current Istio version
istioctl version

# Check Istio-Kubernetes compatibility matrix
# Istio 1.20+ supports K8s 1.32
# Istio 1.19+ supports K8s 1.31
```

**Compatibility requirements:**
- Kubernetes 1.32 requires Istio 1.20.0+ 
- If you're on Istio 1.19.x or older, upgrade Istio BEFORE starting GKE upgrade
- Check [Istio supported releases](https://istio.io/latest/docs/releases/supported-releases/) for your version's K8s compatibility

## Phase 1: GKE Control Plane Upgrade

```bash
# Set maintenance exclusion to prevent node auto-upgrades during mesh transition
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "istio-upgrade" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+7 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Upgrade control plane only
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.0-gke.1200

# Verify control plane upgrade
kubectl get pods -n kube-system
istioctl proxy-status  # Should show all proxies still connected
```

## Phase 2: Istio Control Plane Upgrade

**If already on Istio 1.20+, skip to Phase 3. If on older version:**

```bash
# Backup current Istio config
kubectl get istio -A -o yaml > istio-backup-$(date +%Y%m%d).yaml

# Check for breaking changes in Istio release notes between versions
# Upgrade Istio control plane (method depends on your installation)

# For istioctl-based installs:
istioctl upgrade --skip-confirmation

# For Helm-based installs:
helm repo update
helm upgrade istio-base istio/base -n istio-system
helm upgrade istiod istio/istiod -n istio-system --wait

# Verify control plane health
kubectl get pods -n istio-system
istioctl verify-install
```

## Phase 3: GKE Node Pool Upgrade

**Configure surge settings for mesh workloads:**

```bash
# Mesh workloads need careful drain timing due to sidecar dependencies
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Start node pool upgrade
gcloud container node-pools upgrade default-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.0-gke.1200
```

**Monitor mesh connectivity during node upgrades:**
```bash
# Watch for service mesh disruptions
watch 'kubectl get pods -A -l security.istio.io/tlsMode | grep -v Running'

# Check Envoy proxy health
istioctl proxy-status | grep -v SYNCED
```

## Phase 4: Istio Data Plane Upgrade

```bash
# Remove maintenance exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "istio-upgrade"

# Restart workloads to get updated sidecars (rolling restart)
kubectl rollout restart deployment -n NAMESPACE

# Verify sidecar versions match control plane
istioctl proxy-status
kubectl get pods -n NAMESPACE -o yaml | grep 'image.*proxyv2'
```

## Istio-Specific Risks & Mitigations

### 1. Sidecar Version Skew
**Risk:** Mismatched sidecar/control plane versions cause connection failures
**Mitigation:** 
- Keep control plane upgrade window narrow (hours, not days)
- Use Istio's automatic sidecar injection with version tracking
- Monitor proxy-status during node upgrades

### 2. Certificate Rotation Issues
**Risk:** Node upgrades can disrupt Istio's certificate distribution
**Mitigation:**
```bash
# Check certificate expiry before upgrade
istioctl proxy-config secret deployment/DEPLOYMENT -n NAMESPACE

# Monitor for certificate rotation issues
kubectl logs -n istio-system -l app=istiod -f | grep cert
```

### 3. Gateway/Ingress Disruption
**Risk:** Gateway pods restarting during node upgrades breaks external traffic
**Mitigation:**
- Use multiple gateway replicas across zones
- Set strict PDB for gateway deployments:
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: istio-gateway-pdb
  namespace: istio-system
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: istio-gateway
```

### 4. Service Discovery Lag
**Risk:** New pods on upgraded nodes don't appear in service registry immediately
**Mitigation:**
- Wait 30-60 seconds between node batches for service sync
- Monitor endpoint registration: `kubectl get endpoints`

## Validation Checklist

```bash
# Control plane health
kubectl get pods -n istio-system
istioctl verify-install

# Data plane connectivity
istioctl proxy-status
kubectl get pods -A -l security.istio.io/tlsMode

# Certificate health
istioctl authn tls-check deployment/DEPLOYMENT.NAMESPACE

# End-to-end connectivity test
kubectl exec -n NAMESPACE deployment/CLIENT -- curl -v SERVICE.NAMESPACE:PORT

# Gateway/ingress functionality
curl -v https://your-domain.com/health
```

## Rollback Strategy

If issues arise during the upgrade:

```bash
# Immediate: Cordon problematic nodes
kubectl cordon NODE_NAME

# Create new node pool at previous version for emergency rollback
gcloud container node-pools create rollback-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.0-gke.XXXX \
  --num-nodes 3

# Drain workloads to rollback nodes
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data
```

## Timeline Estimate

- **Phase 1 (Control Plane):** 10-15 minutes
- **Phase 2 (Istio Control Plane):** 15-30 minutes  
- **Phase 3 (Node Pools):** 2-4 hours (depends on cluster size)
- **Phase 4 (Data Plane):** 30-60 minutes
- **Total:** 3-5 hours for medium cluster

## Common Gotchas

1. **Don't upgrade nodes first** — control plane must be upgraded before nodes
2. **Version skew limits** — Istio control plane must support the target K8s version
3. **Gateway disruption** — external traffic may be briefly interrupted without proper PDBs
4. **Certificate rotation** — watch for cert-related connection failures post-upgrade
5. **Webhook compatibility** — Istio admission webhooks may need updates for new K8s APIs

This sequenced approach minimizes mesh disruption while ensuring compatibility throughout the upgrade process.
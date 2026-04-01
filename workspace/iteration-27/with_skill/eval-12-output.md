# GKE + Istio Upgrade Plan: 1.31 → 1.32

Service mesh upgrades require careful orchestration between GKE and Istio components. Here's your step-by-step plan to avoid the common pitfalls.

## Critical Order of Operations

**The golden rule: Control plane first, then data plane, then GKE nodes**

1. **Istio control plane upgrade** (istiod)
2. **Istio data plane upgrade** (envoy sidecars) 
3. **GKE cluster upgrade** (control plane → node pools)

This order ensures Istio components can handle the new Kubernetes API versions before GKE switches to them.

## Pre-Upgrade Planning

### Version Compatibility Check
```bash
# Check current Istio version
kubectl get pods -n istio-system -l app=istiod -o jsonpath='{.items[0].metadata.labels.istio\.io/rev}'

# Verify Istio 1.x supports Kubernetes 1.32
# Check Istio supported platform matrix: https://istio.io/latest/docs/releases/supported-releases/
```

**Key insight:** Istio typically supports Kubernetes N through N-2. If you're on Istio 1.19+, you should have K8s 1.32 support, but verify this first.

### Workload Assessment
```bash
# Identify meshed workloads
kubectl get pods -A -o json | jq -r '.items[] | select(.spec.containers[] | select(.name == "istio-proxy")) | "\(.metadata.namespace)/\(.metadata.name)"'

# Check Istio gateway configurations
kubectl get gateway -A
kubectl get virtualservice -A
```

## Step 1: Istio Control Plane Upgrade

### Pre-flight Checks
```bash
# Backup current Istio configuration
kubectl get all -n istio-system -o yaml > istio-backup-$(date +%Y%m%d).yaml
kubectl get crd -o yaml | grep istio > istio-crds-backup.yaml

# Check control plane health
istioctl proxy-status
istioctl analyze
```

### Upgrade Istio Control Plane
```bash
# Download target Istio version
curl -L https://istio.io/downloadIstio | ISTIO_VERSION=1.20.0 sh -
cd istio-1.20.0

# Install new control plane revision (canary approach)
istioctl install --set values.pilot.env.PILOT_ENABLE_WORKLOAD_ENTRY_AUTOREGISTRATION=true --revision=1-20-0

# Verify new control plane
kubectl get pods -n istio-system -l app=istiod
istioctl proxy-status --revision=1-20-0
```

**Critical: Use revision-based upgrades, not in-place upgrades.** This allows rollback if issues arise.

## Step 2: Istio Data Plane Migration

### Gradual Sidecar Migration
```bash
# Label namespaces for new revision (start with non-production)
kubectl label namespace STAGING_NAMESPACE istio-injection- istio.io/rev=1-20-0

# Restart deployments to get new sidecars
kubectl rollout restart deployment -n STAGING_NAMESPACE

# Verify sidecar versions
kubectl get pods -n STAGING_NAMESPACE -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.metadata.annotations.sidecar\.istio\.io/proxyImage}{"\n"}{end}'
```

### Gateway Migration
```bash
# Update gateway deployments to new revision
kubectl patch deployment istio-gateway -n istio-system -p '{"spec":{"template":{"metadata":{"labels":{"istio.io/rev":"1-20-0"}}}}}'

# Verify gateway connectivity
kubectl get svc -n istio-system istio-gateway
```

### Production Workload Migration
Migrate production namespaces one at a time with soak periods:
```bash
# Per namespace:
kubectl label namespace PRODUCTION_NAMESPACE istio-injection- istio.io/rev=1-20-0
kubectl rollout restart deployment -n PRODUCTION_NAMESPACE
# Wait 30 minutes, monitor metrics, then proceed to next namespace
```

## Step 3: GKE Cluster Upgrade

Only proceed once Istio upgrade is complete and stable.

### Configure Maintenance Controls
```bash
# Set maintenance window (off-peak hours)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-14T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# For maximum control during mesh upgrade
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "mesh-upgrade-control" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

### GKE Control Plane Upgrade
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.xxxx

# Wait ~10-15 minutes, then verify
kubectl get pods -n kube-system
istioctl proxy-status  # Ensure mesh connectivity remains
```

### Node Pool Upgrade Strategy

**Recommended for Istio: Surge with conservative settings**
```bash
# Configure surge (conservative for mesh stability)
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade node pools
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxxx
```

**Why conservative surge?** Istio sidecars need time to establish connectivity. High surge rates can cause temporary mesh partitions.

## Mesh-Specific Monitoring

### During Each Phase
```bash
# Istio control plane health
istioctl proxy-status
kubectl get pods -n istio-system

# Service mesh connectivity
kubectl get virtualservice -A
kubectl get destinationrule -A

# Check for envoy config sync issues  
istioctl proxy-config cluster WORKLOAD_POD.NAMESPACE | grep BlackHole
```

### Service Mesh Metrics to Watch
- **Request success rates** (watch for drops during upgrades)
- **mTLS certificate rotation** (ensure certs don't expire during upgrade)
- **Cross-cluster connectivity** (if using multi-cluster mesh)
- **Gateway ingress latency** (external traffic impact)

## Common Istio + GKE Upgrade Pitfalls

### 1. Admission Webhook Failures
**Symptom:** Pods fail to create after GKE control plane upgrade
```bash
# Check Istio webhook status
kubectl get validatingwebhookconfigurations | grep istio
kubectl get mutatingwebhookconfigurations | grep istio

# Temporary fix if webhooks fail
kubectl patch mutatingwebhookconfigurations istio-sidecar-injector \
  -p '{"webhooks":[{"name":"rev.namespace.sidecar-injector.istio.io","failurePolicy":"Ignore"}]}'
```

### 2. Certificate Rotation Issues
**Symptom:** mTLS connections failing, "certificate verify failed" errors
```bash
# Check certificate expiry
istioctl proxy-config secret WORKLOAD_POD.NAMESPACE | grep ROOTCA

# Force certificate refresh if needed
kubectl delete pods -n istio-system -l app=istiod
```

### 3. Split-Brain During Node Upgrades
**Symptom:** Services can't reach each other during node replacement

**Prevention:** Use PDBs on Istio components:
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: istiod-pdb
  namespace: istio-system
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: istiod
```

### 4. Gateway Configuration Drift
**Symptom:** External traffic routing breaks after upgrade
```bash
# Verify gateway configurations survive upgrade
kubectl get gateway -A -o yaml > gateways-post-upgrade.yaml
diff gateways-pre-upgrade.yaml gateways-post-upgrade.yaml
```

## Rollback Strategy

### If Istio Control Plane Upgrade Fails
```bash
# Switch workloads back to old revision
kubectl label namespace NAMESPACE istio.io/rev=1-19-0 istio-injection-

# Remove failed revision
istioctl uninstall --revision=1-20-0 --skip-confirmation
```

### If GKE Upgrade Causes Mesh Issues
```bash
# You cannot rollback GKE control plane, but you can:
# 1. Rollback Istio data plane to previous revision
# 2. Apply mesh configuration fixes
# 3. Contact GKE support for control plane issues
```

## Post-Upgrade Cleanup

### Remove Old Istio Revision
```bash
# After all workloads migrated and stable for 24+ hours
istioctl uninstall --revision=1-19-0 --skip-confirmation

# Clean up old CRDs (carefully!)
kubectl get crd | grep istio | grep "1-19-0"
```

### Validation Checklist
```
Post-Upgrade Validation
- [ ] All istiod pods running and ready
- [ ] istioctl proxy-status shows all workloads connected
- [ ] External gateway traffic routing correctly
- [ ] mTLS connections working (no certificate errors)
- [ ] Istio metrics flowing to monitoring system
- [ ] Cross-namespace service discovery working
- [ ] All custom Istio resources (VirtualService, DestinationRule) applied correctly
```

## Key Takeaways

1. **Never upgrade GKE and Istio simultaneously** — always upgrade Istio first
2. **Use Istio revision-based upgrades** for safe rollback capability  
3. **Test the upgrade path in staging** with identical Istio configuration
4. **Conservative node pool surge settings** (maxSurge=1) prevent mesh partitions
5. **Monitor service mesh connectivity** at each phase, not just pod status
6. **Have PDBs configured** for both GKE workloads and Istio control plane

The mesh upgrade horror stories usually come from teams who upgraded GKE first or tried to upgrade both simultaneously. Follow this order and you'll have a smooth migration.
# GKE Standard Cluster Upgrade Plan: Mixed Spot/On-Demand Node Pools

## Key Considerations for Spot VM Upgrades

### Spot VM Characteristics
- **Workloads are preemption-tolerant by design** — upgrade risk is inherently lower than on-demand
- **Higher fault tolerance** — applications already handle interruption gracefully
- **Lower upgrade risk profile** — makes them ideal candidates for testing upgrade settings

### Recommended Upgrade Strategy

**1. Upgrade Sequence: Spot Pools First**
```bash
# Upgrade spot pools BEFORE on-demand pools
# They carry lower risk and validate your surge/drain settings
```

**2. Spot-Specific Surge Settings**
```bash
# For spot node pools - more aggressive than on-demand
gcloud container node-pools update SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5 \
  --max-unavailable-upgrade 1

# For on-demand pools - more conservative
gcloud container node-pools update ONDEMAND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

**Rationale:** Spot workloads already tolerate interruption, so you can use higher `maxSurge` (2-5% of pool size vs 1-2% for on-demand) and allow some unavailability during drain.

**3. PDB Configuration**
Even though spot workloads are interruption-tolerant, still configure PDBs for orderly drain:
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: spot-workload-pdb
spec:
  minAvailable: 80%  # More permissive than on-demand (typically 90%+)
  selector:
    matchLabels:
      app: your-spot-workload
```

## Complete Upgrade Plan

### Phase 1: Pre-flight Checks
```bash
# Verify current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Check spot vs on-demand pool identification
kubectl get nodes -o custom-columns="NAME:.metadata.name,PREEMPTIBLE:.spec.taints[?(@.key=='cloud.google.com/gke-preemptible')]"
```

### Phase 2: Control Plane Upgrade
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.0-gke.1500
```

### Phase 3: Node Pool Upgrades (Spot First)

**Step 1: Configure and upgrade spot pools**
```bash
# Configure spot pool for faster upgrade
gcloud container node-pools update SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5 \
  --max-unavailable-upgrade 1

# Upgrade spot pool
gcloud container node-pools upgrade SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.0-gke.1500

# Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
```

**Step 2: After spot pool completes, upgrade on-demand pools**
```bash
# Configure on-demand pool more conservatively
gcloud container node-pools update ONDEMAND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# Upgrade on-demand pool
gcloud container node-pools upgrade ONDEMAND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.0-gke.1500
```

## Pre-Upgrade Checklist

```
Mixed Spot/On-Demand Upgrade Checklist
- [ ] Control plane upgrade: 1.31 → 1.32
- [ ] Spot workloads verified as interruption-tolerant
- [ ] PDBs configured (more permissive for spot pools)
- [ ] Spot pools identified and will be upgraded first
- [ ] Higher maxSurge configured for spot pools (5 vs 2)
- [ ] On-demand pools configured conservatively
- [ ] Monitoring active for both pool types during upgrade
- [ ] Rollback plan documented for each pool type
```

## Monitoring During Upgrade

```bash
# Watch node upgrade progress by pool
kubectl get nodes -o wide -L cloud.google.com/gke-nodepool,cloud.google.com/gke-preemptible

# Monitor pod disruptions
kubectl get events -A --field-selector reason=Evicted -w

# Check PDB compliance
kubectl get pdb -A -o wide
```

## Benefits of This Approach

1. **Risk Validation**: Spot pools test your upgrade configuration with lower-risk workloads
2. **Faster Learning**: Higher surge settings on spot pools reveal issues faster
3. **Workload Alignment**: Upgrade strategy matches workload fault tolerance
4. **Cost Efficiency**: Spot instances cost less during the temporary surge period
5. **Operational Confidence**: Success with spot pools builds confidence for on-demand upgrades

The key insight is leveraging spot workloads' inherent fault tolerance to validate your upgrade approach before applying it to more sensitive on-demand workloads.
# GKE Upgrade Plan: Mixed Spot/On-Demand Node Pools

## Spot VM Upgrade Considerations

Spot instances have unique characteristics that actually make upgrades **less risky** than on-demand nodes:

### Key Advantages
- **Workloads are preemption-tolerant by design** — they already handle interruption gracefully
- **Lower blast radius** — spot workloads expect and recover from node loss
- **Cost-effective testing ground** — validate upgrade procedures with lower-risk workloads first

### Recommended Strategy

**1. Upgrade sequence: Spot pools FIRST**
```bash
# Upgrade spot pools before on-demand pools
gcloud container node-pools upgrade SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.X-gke.XXXX
```

This approach lets you:
- Test surge/drain settings on lower-risk workloads
- Validate the target version with real traffic
- Fine-tune upgrade parameters before touching critical on-demand workloads

**2. Optimized surge settings for spot pools**
```bash
# Configure more aggressive settings than on-demand
gcloud container node-pools update SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5% \
  --max-unavailable-upgrade 2
```

**Rationale:** 
- Higher `maxSurge` (2-5% vs 1-2% for on-demand) because workloads tolerate interruption
- `maxUnavailable=1-2` is safe since workloads handle node loss anyway
- Faster upgrade completion reduces the window where pools are in mixed-version state

**3. PDBs still matter**
Even for preemption-tolerant workloads, configure PDBs to ensure orderly drain:
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: spot-workload-pdb
spec:
  minAvailable: 50%  # Or whatever maintains service levels
  selector:
    matchLabels:
      app: your-spot-app
```

## Complete Upgrade Runbook

### Pre-flight Checks
```bash
# Verify current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Check workload distribution
kubectl get pods -o wide --all-namespaces | grep SPOT_NODE_NAMES
kubectl get pods -o wide --all-namespaces | grep ON_DEMAND_NODE_NAMES
```

### Upgrade Sequence

**Step 1: Control plane**
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.X-gke.XXXX
```

**Step 2: Spot node pools (first)**
```bash
# Configure optimized settings
gcloud container node-pools update SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5 \
  --max-unavailable-upgrade 2

# Upgrade
gcloud container node-pools upgrade SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.X-gke.XXXX
```

**Step 3: Monitor and validate**
```bash
# Watch spot pool upgrade progress
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=SPOT_POOL_NAME'

# Validate workloads on upgraded spot nodes
kubectl get pods -o wide | grep UPGRADED_SPOT_NODES
```

**Step 4: On-demand pools (after spot validation)**
```bash
# More conservative settings for production workloads
gcloud container node-pools update ON_DEMAND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# Upgrade
gcloud container node-pools upgrade ON_DEMAND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.X-gke.XXXX
```

## Architecture-Specific Considerations

**If using separate node pools for spot vs on-demand:**
- Upgrade spot pool first (lower risk)
- Use different surge settings per pool type
- Monitor cross-pool workload migration during upgrades

**If using mixed spot/on-demand within single pools:**
- Both instance types upgrade together
- Use conservative settings (spot advantages are diluted)
- Consider splitting into separate pools for better upgrade control

## Monitoring During Upgrade

```bash
# Track preemptions during upgrade window
kubectl get events --all-namespaces --field-selector reason=Preempted

# Monitor workload redistribution
kubectl get pods -o wide --show-labels | grep spot-workload

# Validate no stuck pods
kubectl get pods --all-namespaces | grep -E "Terminating|Pending"
```

## Post-Upgrade Validation

- [ ] All spot workloads running normally on upgraded nodes
- [ ] Preemption handling still working (test with `gcloud compute instances simulate-maintenance-event`)  
- [ ] Cost monitoring confirms spot discounts maintained
- [ ] On-demand upgrade proceeded without issues after spot validation

The key insight: **spot instances make excellent upgrade canaries** because their workloads are already designed for disruption tolerance. Use this to your advantage by upgrading spot pools first to validate your upgrade strategy before touching critical on-demand workloads.
# GKE Node Pool Upgrade Plan: Spot VM Considerations

## Spot VM Upgrade Strategy

Spot instances have unique characteristics that actually make them **lower risk** for upgrades compared to on-demand nodes:

### Key Advantages
- **Workloads are preemption-tolerant by design** — your applications already handle interruption gracefully
- **Lower upgrade risk** — if something goes wrong during drain/eviction, the impact is similar to a normal spot preemption
- **Faster upgrade cadence** — you can be more aggressive with surge settings

### Recommended Upgrade Settings for Spot Pools

```bash
# Configure more aggressive surge settings for spot pools
gcloud container node-pools update SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5% \
  --max-unavailable-upgrade 2

# For comparison, on-demand pools typically use:
gcloud container node-pools update ONDEMAND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**Why higher surge for spot:**
- 5% surge (minimum 1 node): Scales with pool size, faster than default 1-node-at-a-time
- `maxUnavailable=2`: Spot workloads tolerate node loss, so draining 2 nodes simultaneously is acceptable
- Result: Significantly faster upgrade completion with acceptable risk

### Upgrade Sequencing Strategy

**Upgrade spot pools FIRST, then on-demand pools:**

1. **Phase 1: Spot pools** (lower risk, faster)
   ```bash
   gcloud container node-pools upgrade SPOT_POOL_NAME \
     --cluster CLUSTER_NAME \
     --zone ZONE \
     --cluster-version 1.32.x-gke.xxx
   ```

2. **Phase 2: On-demand pools** (after spot validation)
   ```bash
   gcloud container node-pools upgrade ONDEMAND_POOL_NAME \
     --cluster CLUSTER_NAME \
     --zone ZONE \
     --cluster-version 1.32.x-gke.xxx
   ```

**Benefits of this sequence:**
- Spot pools act as a canary for your upgrade settings
- If drain/surge settings cause issues, you discover them on preemption-tolerant workloads first
- Validates GKE 1.32 compatibility with lower-risk workloads

### PDB Considerations

**Still configure PDBs for spot workloads:**
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: spot-workload-pdb
spec:
  minAvailable: 50%
  selector:
    matchLabels:
      app: your-spot-app
```

**Why PDBs matter for spot:** While your workloads handle preemption, PDBs ensure **orderly drain** during upgrades rather than simultaneous eviction. This prevents thundering herd effects and maintains some service capacity during the upgrade window.

### Mixed Pool Architecture Recommendations

For your mixed on-demand + spot setup:

**Option A: Separate upgrade timing (recommended)**
```bash
# Week 1: Upgrade spot pools during business hours (lower risk)
# Spot pools: Tuesday 2-4 PM
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-16T14:00:00Z" \
  --maintenance-window-end "2024-01-16T16:00:00Z"

# Week 2: Upgrade on-demand pools during off-peak
# On-demand pools: Saturday 2-6 AM  
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-20T02:00:00Z" \
  --maintenance-window-end "2024-01-20T06:00:00Z"
```

**Option B: Same maintenance window, sequential execution**
- GKE upgrades one node pool at a time automatically
- Spot pools complete first (due to faster settings), then on-demand
- 4-6 hour weekend window accommodates both

### Monitoring During Spot Pool Upgrades

```bash
# Monitor upgrade progress
watch 'kubectl get nodes -l cloud.google.com/gke-preemptible=true -o wide'

# Check for workload redistribution
kubectl get pods -A -o wide | grep SPOT_NODE_NAME

# Verify no unexpected pod failures (beyond normal preemption)
kubectl get events -A --field-selector reason=FailedScheduling --sort-by='.lastTimestamp'
```

### Pre-Upgrade Checklist: Spot-Specific Items

```markdown
Spot VM Upgrade Checklist
- [ ] Spot workloads have appropriate restart/interruption handling
- [ ] PDBs configured (even for preemption-tolerant workloads)
- [ ] Aggressive surge settings configured: maxSurge=5%, maxUnavailable=2
- [ ] Spot pools scheduled to upgrade before on-demand pools
- [ ] Monitoring configured to distinguish upgrade disruption from normal preemption
- [ ] Baseline preemption rates captured for comparison
```

## Version Compatibility: 1.31 → 1.32

No spot-specific breaking changes between these versions. Standard GKE 1.32 compatibility applies:
- Check deprecated API usage: `kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated`
- Review [GKE 1.32 release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes#january_08_2025) for general changes

Would you like me to help you configure the specific surge settings for your spot pools, or do you need guidance on the overall upgrade timeline for your mixed environment?
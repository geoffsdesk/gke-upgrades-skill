# Spot Instance Upgrade Considerations

Here are the key considerations for upgrading your mixed spot/on-demand node pool from 1.31 → 1.32:

## Spot VM Upgrade Behavior

**Double disruption risk:** Spot VMs face two types of interruptions during upgrades:
1. **GKE-initiated drain** for the upgrade process
2. **Google Cloud preemption** (can happen anytime, 30-second notice)

This means workloads on spot nodes may be disrupted twice — once for the upgrade and potentially again if the spot VM gets preempted during the upgrade window.

**No surge capacity guarantee:** Spot VMs have no capacity guarantee. If your node pool uses `maxSurge > 0`, the surge spot instances may fail to provision, causing the upgrade to stall. This is especially problematic during peak demand periods.

## Recommended Upgrade Strategy

**Option 1: Conservative approach (recommended)**
```bash
# Use maxUnavailable mode to avoid surge capacity issues
gcloud container node-pools update YOUR_NODE_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1

# Then upgrade
gcloud container node-pools upgrade YOUR_NODE_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxxx
```

**Option 2: If you have separate pools (better)**
If possible, split your workloads:
- **Critical workloads** → on-demand node pool (surge upgrade with `maxSurge=2, maxUnavailable=0`)
- **Fault-tolerant workloads** → spot-only node pool (drain mode with `maxSurge=0, maxUnavailable=1`)

## Workload Placement Strategy

**Use node affinity to control placement:**
```yaml
# For spot-tolerant workloads
nodeAffinity:
  requiredDuringSchedulingIgnoredDuringExecution:
    nodeSelectorTerms:
    - matchExpressions:
      - key: cloud.google.com/gke-spot
        operator: In
        values: ["true"]

# For spot-intolerant workloads  
nodeAffinity:
  requiredDuringSchedulingIgnoredDuringExecution:
    nodeSelectorTerms:
    - matchExpressions:
      - key: cloud.google.com/gke-spot
        operator: DoesNotExist
```

**Add tolerations for spot nodes:**
```yaml
tolerations:
- key: cloud.google.com/gke-spot
  operator: Equal
  value: "true"
  effect: NoSchedule
```

## Pre-Upgrade Checklist for Spot Workloads

```markdown
Spot VM Pre-Upgrade Checklist
- [ ] Workloads are designed for interruption (stateless or checkpointing)
- [ ] PDBs are not overly restrictive (allow at least 1 disruption)
- [ ] Critical workloads have node affinity to avoid spot nodes
- [ ] Batch jobs can resume from checkpoints or are idempotent
- [ ] Monitoring in place for spot preemption rates during upgrade window
- [ ] Consider upgrading during off-peak hours (lower preemption rates)
- [ ] Cluster Autoscaler configured with mixed instance types if using separate pools
```

## Monitoring During Upgrade

**Track both upgrade progress and spot preemptions:**
```bash
# Monitor upgrade progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-spot'

# Check for preemption events
kubectl get events -A --field-selector reason=Preempted

# Monitor workload health
kubectl get pods -A | grep -E "Terminating|Pending|CrashLoopBackOff"
```

## Alternative: Blue-Green with Mixed Capacity

If your workloads can't tolerate the double disruption, consider a blue-green approach:

```bash
# Create new node pool with same spot/on-demand mix
gcloud container node-pools create nodepool-132 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxxx \
  --spot \
  --num-nodes X \
  --enable-autoscaling \
  --min-nodes Y --max-nodes Z

# Cordon old pool and migrate
kubectl cordon -l cloud.google.com/gke-nodepool=OLD_POOL_NAME
# Wait for natural spot preemption + pod rescheduling to new pool
# Or force migration with kubectl drain if needed

# Delete old pool when migration complete
gcloud container node-pools delete OLD_POOL_NAME --cluster CLUSTER_NAME --zone ZONE
```

## Key Recommendation

**Separate your pools if possible.** Mixed spot/on-demand pools are harder to manage during upgrades. Consider:
- On-demand pool for critical services (fast surge upgrades)
- Spot pool for batch/fault-tolerant workloads (conservative drain upgrades)
- Use Cluster Autoscaler to balance cost vs. availability across both pools

This gives you much better control over upgrade timing and disruption patterns for different workload types.
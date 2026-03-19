# GKE Node Pool Upgrade Plan: Spot VM Considerations

**Cluster**: Standard | **Upgrade**: 1.29 → 1.30 | **Node Pool**: Mixed spot + on-demand

## Spot VM Upgrade Behavior

Spot VMs have **identical upgrade behavior** to on-demand instances during GKE node pool upgrades. The key difference is that spot VMs face **dual eviction risk**:

1. **GKE upgrade eviction** (controlled, respects PDBs for up to 1 hour)
2. **Google Cloud spot preemption** (immediate, no grace period)

This means your workloads already handle sudden eviction, which actually makes them **well-suited** for upgrades.

## Recommended Upgrade Strategy

### Surge settings for mixed spot/on-demand pools
```bash
gcloud container node-pools update YOUR_NODE_POOL \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

**Rationale**: Higher surge compensates for potential spot preemptions during upgrade. If a surge node gets preempted, GKE creates another.

### If spot availability is constrained
```bash
# More conservative approach if spot quota is limited
gcloud container node-pools update YOUR_NODE_POOL \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 1
```

## Key Considerations

### 1. Spot availability during upgrade
- **Surge nodes inherit the same spot/on-demand ratio** as your existing pool configuration
- If spot VMs are unavailable in your zones, GKE may fail to provision surge nodes
- **Monitor**: `kubectl get nodes -w` during upgrade to catch provisioning delays

### 2. Workload tolerance
Your spot-tolerant workloads should already have:
- ✅ **Proper disruption handling** (graceful shutdown)
- ✅ **No local state dependency** (or proper checkpointing)
- ✅ **Reasonable replica counts** with spread topology

These same patterns protect against upgrade evictions.

### 3. Cost optimization opportunity
- Upgrade may temporarily increase costs due to surge capacity
- Mixed pools can see **spot → on-demand** transitions during surge if spot unavailable
- Duration: typically 30-60 minutes for the pool upgrade

### 4. PDB interaction
```bash
# Verify PDBs aren't overly restrictive
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS > 0
```

Spot-aware workloads should have PDBs that allow some disruption since preemption can happen anyway.

## Pre-Upgrade Checklist

```markdown
Spot VM Node Pool Upgrade Checklist
- [ ] Current spot/on-demand ratio documented
- [ ] Sufficient spot quota in all zones for surge nodes
- [ ] Workloads tested for graceful eviction handling
- [ ] PDBs configured but not overly restrictive (allow ≥1 disruption)
- [ ] Monitoring active for node provisioning delays
- [ ] Cost spike during upgrade approved (temporary surge capacity)
- [ ] Fallback plan if spot capacity unavailable (increase on-demand percentage)
```

## Upgrade Commands

```bash
# 1. Pre-flight: Check current node composition
kubectl get nodes -l cloud.google.com/gke-nodepool=YOUR_NODE_POOL \
  -o custom-columns=NAME:.metadata.name,PREEMPTIBLE:.spec.taints[?(@.key=='cloud.google.com/gke-preemptible')]

# 2. Configure surge (adjust based on spot availability)
gcloud container node-pools update YOUR_NODE_POOL \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# 3. Upgrade node pool
gcloud container node-pools upgrade YOUR_NODE_POOL \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --cluster-version 1.30

# 4. Monitor progress (watch for spot provisioning delays)
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=YOUR_NODE_POOL -o wide'
```

## Troubleshooting Spot-Specific Issues

### Surge nodes stuck provisioning
```bash
kubectl get events -A --field-selector reason=FailedCreate
# Look for "zone has no available capacity for spot VMs"
```

**Fix**: Temporarily increase on-demand percentage or switch to `maxUnavailable` mode:
```bash
gcloud container node-pools update YOUR_NODE_POOL \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

### Spot preemption during upgrade
If spot nodes get preempted mid-upgrade, GKE automatically creates replacements and continues. No manual intervention needed, but monitor for completion.

## Bottom Line

Spot VMs don't fundamentally change the upgrade process, but they add capacity uncertainty. Your workloads' existing spot-tolerance makes them upgrade-resilient. Plan for slightly higher surge settings and monitor provisioning closely.
# GKE Node Pool Upgrade Plan: Spot VM Considerations

## Spot VM Upgrade Behavior

**Key insight:** GKE treats spot and on-demand nodes identically during upgrades. The upgrade process (surge/blue-green) works the same regardless of node pricing model. However, spot VMs add an additional layer of potential disruption that requires specific planning.

## Special Considerations for Mixed Spot/On-Demand Pools

### 1. Spot VM Preemption Risk During Upgrade
- **Double disruption potential:** Spot nodes can be preempted by Google Cloud during the upgrade window, adding unpredictability to the planned upgrade disruption
- **No preemption protection:** Unlike maintenance events, upgrades don't provide preemption protection for spot VMs
- **Timing consideration:** Longer upgrade windows (due to surge settings) increase preemption exposure

### 2. Surge Strategy Adjustments

For mixed spot/on-demand pools, modify your surge settings:

```bash
# Recommended: Higher surge, zero unavailable
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0
```

**Rationale:** 
- Higher `maxSurge` compensates for potential spot preemptions during upgrade
- `maxUnavailable=0` ensures you don't voluntarily reduce capacity when spot preemptions might already be reducing it
- Creates buffer capacity to absorb both planned upgrade disruption and unplanned preemptions

### 3. Workload Resilience Requirements

Ensure workloads can handle:
- **Planned disruption:** Normal upgrade node replacement
- **Unplanned disruption:** Spot preemption during upgrade
- **Combined disruption:** Multiple spot nodes preempted while surge nodes are being created

## Upgrade Plan for Your 1.31 → 1.32 Upgrade

### Pre-Upgrade Checklist
```
Spot VM Specific Checks
- [ ] PDBs configured for critical workloads (essential with spot VMs)
- [ ] No bare pods on spot nodes
- [ ] Workloads have appropriate replica counts to survive combined disruptions
- [ ] Spot usage balanced across zones (for multi-zone pools)
- [ ] Sufficient compute quota for higher surge settings
- [ ] Consider spot price volatility in target regions during upgrade window
```

### Recommended Settings

```bash
# Step 1: Configure surge for spot resilience
gcloud container node-pools update MIXED_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0

# Step 2: Control plane upgrade first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32

# Step 3: Node pool upgrade
gcloud container node-pools upgrade MIXED_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

### Alternative: Separate Pool Strategy

For maximum control, consider splitting the pool:

```bash
# Create dedicated spot pool
gcloud container node-pools create spot-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --spot \
  --num-nodes 3 \
  --machine-type n2-standard-4

# Create dedicated on-demand pool  
gcloud container node-pools create ondemand-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --num-nodes 2 \
  --machine-type n2-standard-4
```

**Benefits:**
- Different surge strategies per pool type
- Spot pool can use higher surge (more tolerance for preemption)
- On-demand pool can use conservative settings
- Better workload placement control via node affinity

### Workload Placement Strategy

```yaml
# For critical workloads: prefer on-demand nodes
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      affinity:
        nodeAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            preference:
              matchExpressions:
              - key: cloud.google.com/gke-spot
                operator: NotIn
                values: ["true"]
```

```yaml
# For batch/fault-tolerant workloads: prefer spot nodes
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      affinity:
        nodeAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            preference:
              matchExpressions:
              - key: cloud.google.com/gke-spot
                operator: In
                values: ["true"]
```

## Monitoring During Upgrade

```bash
# Track spot preemptions during upgrade
kubectl get events -A --field-selector reason=Preempted -w

# Monitor node replacement progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-spot'

# Check workload disruption
kubectl get pods -A | grep -E "Terminating|Pending"
```

## Post-Upgrade Validation

```bash
# Verify spot/on-demand node distribution
kubectl get nodes -L cloud.google.com/gke-spot,kubernetes.io/arch

# Confirm workload placement
kubectl get pods -A -o wide | grep NODE_NAME

# Check for any stuck workloads
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded
```

## Recommendations

1. **Use higher surge settings** (`maxSurge=3, maxUnavailable=0`) to buffer against preemptions
2. **Schedule during lower spot demand periods** (typically weekends/off-hours)
3. **Ensure robust PDBs** for critical applications
4. **Consider splitting into dedicated spot/on-demand pools** for better control
5. **Monitor spot pricing trends** in your region before the upgrade window

The 1.31 → 1.32 upgrade itself has no breaking changes affecting spot VMs specifically, so your main focus should be on handling the combined disruption potential.
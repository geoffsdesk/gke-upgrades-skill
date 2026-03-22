# GKE Upgrade Plan: Standard Cluster with Spot VMs

## Spot VM Upgrade Considerations

Spot VMs add specific challenges to node pool upgrades that require adjusted planning:

### Key Spot VM Constraints

**1. Spot availability during upgrades**
- Surge upgrades need NEW spot instances for temporary capacity
- Spot availability varies by zone/machine-type and may be limited during upgrade
- If spot instances can't be provisioned for surge nodes, the upgrade will stall
- **Recommendation**: Consider upgrading during off-peak hours when spot availability is typically higher

**2. Mixed spot/on-demand complexity**
- GKE treats the entire node pool as one unit during upgrades
- Both spot and on-demand nodes follow the same upgrade strategy
- You can't upgrade spot and on-demand nodes separately within the same pool

**3. Workload tolerance**
- Spot workloads should already be fault-tolerant (spot can be preempted anytime)
- On-demand workloads in mixed pools inherit spot-level reliability during upgrades

## Recommended Upgrade Strategy

### Option 1: Conservative Surge (Recommended)
```bash
# Configure conservative surge settings
gcloud container node-pools update YOUR_NODE_POOL \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**Why this works well for spot:**
- Only needs 1 additional spot instance at a time
- Higher chance of spot availability for small increments
- Minimizes risk of upgrade stalling due to spot unavailability
- Zero capacity loss during upgrade

### Option 2: Autoscaled Blue-Green (If spot capacity is uncertain)
```bash
# Enable autoscaled blue-green upgrade
gcloud container node-pools update YOUR_NODE_POOL \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --enable-autoscaled-blue-green-upgrade
```

**Benefits for mixed spot/on-demand:**
- Green pool scales based on actual workload demand
- Can handle spot unavailability more gracefully
- Longer eviction periods help workloads complete gracefully
- Better cost control during the transition

### Option 3: Separate Pool Strategy (Advanced)
If you have strict availability requirements for some workloads:

1. **Create separate node pools** before upgrade:
   - `critical-ondemand-pool` (on-demand only, high-priority workloads)
   - `batch-spot-pool` (spot only, fault-tolerant workloads)

2. **Migrate workloads** using node affinity/taints
3. **Upgrade pools independently** with different strategies

## Pre-Upgrade Checklist for Spot VMs

```
Spot VM Upgrade Checklist
- [ ] Workload fault tolerance verified (all workloads can handle spot preemption)
- [ ] PDBs configured but not overly restrictive
- [ ] No single points of failure on individual nodes
- [ ] Upgrade timing planned for off-peak hours (better spot availability)
- [ ] Node pool surge strategy chosen:
      - Conservative surge (maxSurge=1, maxUnavailable=0) ✓ Recommended
      - Autoscaled blue-green (for uncertain spot capacity)
      - Manual coordination (advanced users only)
- [ ] Monitoring in place for upgrade progress and spot preemptions
- [ ] Cluster autoscaler disabled temporarily (if enabled) to prevent interference
```

## Upgrade Commands

### 1. Control Plane First
```bash
# Upgrade control plane to 1.32
gcloud container clusters upgrade YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --master \
  --cluster-version 1.32.0-gke.X
```

### 2. Configure Node Pool Strategy
```bash
# Set conservative surge for spot VMs
gcloud container node-pools update YOUR_NODE_POOL \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### 3. Upgrade Node Pool
```bash
# Start node pool upgrade
gcloud container node-pools upgrade YOUR_NODE_POOL \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --cluster-version 1.32.0-gke.X
```

### 4. Monitor Progress
```bash
# Watch node replacement (spot and on-demand)
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-preemptible,cloud.google.com/gke-spot'

# Check for any stuck pods
kubectl get pods -A | grep -v Running | grep -v Completed
```

## Potential Issues & Solutions

**Issue**: Upgrade stalls because spot instances can't be provisioned
```bash
# Check upgrade status
gcloud container operations list --cluster YOUR_CLUSTER --zone YOUR_ZONE

# If stuck for >30 minutes, temporarily switch to on-demand surge
# (requires creating a temporary mixed node pool configuration)
```

**Issue**: Spot preemptions during upgrade window
- This is normal behavior - workloads should handle it gracefully
- Monitor for excessive preemptions that might indicate capacity issues

**Issue**: Cost optimization concerns
```bash
# Monitor node pool composition during upgrade
kubectl get nodes -L cloud.google.com/gke-preemptible,cloud.google.com/gke-spot -L beta.kubernetes.io/instance-type
```

## Post-Upgrade Validation

```
Post-Upgrade Checklist
- [ ] All nodes at version 1.32: `kubectl get nodes -o wide`
- [ ] Spot/on-demand ratio maintained as expected
- [ ] All workloads rescheduled successfully
- [ ] No increase in application error rates
- [ ] Cluster autoscaler re-enabled (if previously used)
- [ ] Cost monitoring confirms expected spot savings maintained
```

The key with spot VMs is being **conservative with surge settings** and **timing the upgrade** when spot availability is likely to be higher. The workloads should already be fault-tolerant, so the upgrade process itself shouldn't introduce new reliability concerns beyond the normal spot preemption behavior.
# GKE Standard Cluster Upgrade Plan: Spot VM Considerations

## Spot VM Upgrade Characteristics

Spot VMs in GKE node pools have unique behavior during upgrades that requires special planning:

**Key differences from on-demand:**
- **Double eviction risk**: Spot VMs can be preempted by Google Cloud AND evicted by GKE upgrade operations
- **No surge capacity**: Spot instances have limited availability and may not be available for surge upgrades
- **Pricing advantage**: Spot VMs are 60-91% cheaper but come with availability tradeoffs

## Recommended Upgrade Strategy

### 1. Configure Conservative Surge Settings

For mixed spot/on-demand pools, use minimal surge to account for spot availability:

```bash
gcloud container node-pools update YOUR_POOL_NAME \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**Why this works:**
- `maxSurge=1`: Requests only one additional spot VM at a time (higher chance of success)
- `maxUnavailable=0`: Ensures no capacity loss during upgrade
- If spot surge fails, GKE will retry or use alternative strategies

### 2. Consider Blue-Green for Critical Workloads

For workloads that can't tolerate the uncertainty of spot availability:

```bash
# Create new pool at target version
gcloud container node-pools create temp-upgrade-pool \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --cluster-version 1.32.x-gke.xxxx \
  --spot \
  --num-nodes 3 \
  --machine-type YOUR_MACHINE_TYPE

# Cordon old pool after new nodes ready
kubectl cordon -l cloud.google.com/gke-nodepool=YOUR_OLD_POOL
```

### 3. Workload-Specific Considerations

**Fault-tolerant workloads (batch, stateless):**
- Can handle double eviction (spot preemption + upgrade eviction)
- Use standard surge upgrade: `maxSurge=1, maxUnavailable=0`
- Ensure jobs have checkpointing or can restart cleanly

**Spot-intolerant workloads on mixed pools:**
- Use node affinity to pin critical workloads to on-demand nodes
- Consider separate pools: spot pool for batch, on-demand pool for critical services

```yaml
# Example node affinity for on-demand only
spec:
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
        - matchExpressions:
          - key: cloud.google.com/gke-spot
            operator: DoesNotExist
```

## Pre-Upgrade Checklist (Spot-Specific)

```
Spot VM Upgrade Checklist
- [ ] Current versions: Control plane ___ | Node pool ___
- [ ] Target version: 1.32.x-gke.xxxx confirmed available
- [ ] Mixed pool composition documented: ___% spot, ___% on-demand

Spot Availability Assessment
- [ ] Recent spot preemption rate reviewed (Cloud Monitoring: compute.googleapis.com/instance/preempted)
- [ ] Spot quota sufficient in target zones
- [ ] Alternative zones identified if primary zone lacks spot capacity

Workload Readiness
- [ ] Fault-tolerant workloads identified (can handle double eviction)
- [ ] Critical workloads using node affinity to avoid spot (if needed)
- [ ] PDBs configured appropriately (not overly restrictive for spot workloads)
- [ ] Job restart/checkpointing mechanisms verified

Upgrade Strategy
- [ ] Conservative surge settings: maxSurge=1, maxUnavailable=0
- [ ] Blue-green alternative planned if surge fails
- [ ] Maintenance window during low-demand hours (higher spot availability)
```

## Upgrade Runbook

### Pre-flight Checks
```bash
# Check current spot vs on-demand distribution
kubectl get nodes -o wide -l cloud.google.com/gke-nodepool=YOUR_POOL_NAME
kubectl get nodes -l cloud.google.com/gke-spot=true --no-headers | wc -l

# Review recent preemptions
gcloud logging read 'resource.type="gce_instance" 
  AND jsonPayload.event_subtype="compute.instances.preempted"' \
  --limit=10 --format=json
```

### Execute Upgrade
```bash
# Set conservative surge (critical for spot pools)
gcloud container node-pools update YOUR_POOL_NAME \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade control plane first
gcloud container clusters upgrade YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --master \
  --cluster-version 1.32.x-gke.xxxx

# Upgrade node pool
gcloud container node-pools upgrade YOUR_POOL_NAME \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --cluster-version 1.32.x-gke.xxxx
```

### Monitor Progress
```bash
# Watch node replacement (expect slower progress with spot)
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=YOUR_POOL_NAME -o wide'

# Check for spot preemptions during upgrade
kubectl get events --field-selector reason=NodeNotReady,reason=Rebooted
```

## Troubleshooting Spot-Specific Issues

### Surge Nodes Unavailable
**Symptom:** Upgrade stalls, logs show "insufficient spot capacity"
```bash
# Check operation status
gcloud container operations list --cluster YOUR_CLUSTER_NAME --zone YOUR_ZONE
```

**Fix:** Switch to blue-green or increase `maxUnavailable`:
```bash
# Allow capacity dip approach
gcloud container node-pools update YOUR_POOL_NAME \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

### Frequent Spot Preemptions During Upgrade
**Symptom:** New spot nodes get preempted before workloads migrate
**Fix:** Temporarily pause upgrade and wait for better spot availability, or migrate to blue-green with on-demand surge pool.

## Post-Upgrade Validation

```bash
# Verify all nodes upgraded successfully
kubectl get nodes -l cloud.google.com/gke-nodepool=YOUR_POOL_NAME \
  -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,SPOT:.metadata.labels.cloud\.google\.com/gke-spot

# Confirm spot/on-demand ratio maintained
echo "Spot nodes: $(kubectl get nodes -l cloud.google.com/gke-spot=true --no-headers | wc -l)"
echo "Total nodes: $(kubectl get nodes -l cloud.google.com/gke-nodepool=YOUR_POOL_NAME --no-headers | wc -l)"

# Check workload distribution post-upgrade
kubectl get pods -A -o wide | grep YOUR_POOL_NAME
```

## Cost Optimization Tips

- **Timing**: Upgrade during off-peak hours when spot availability is higher
- **Regional vs zonal**: Regional clusters can leverage spot capacity across multiple zones
- **Mixed strategy**: Keep critical path workloads on on-demand nodes, use spot for batch/non-critical
- **Preemption handling**: Ensure batch workloads gracefully handle both upgrade evictions and spot preemptions

The key insight is that spot VMs add uncertainty to the upgrade process, but with conservative surge settings and proper workload design, they can be upgraded successfully while maintaining cost benefits.
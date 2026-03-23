# GKE Upgrade Plan: Spot VM Node Pool Considerations

## Executive Summary

Spot VM node pools require special handling during upgrades due to their interruption behavior. The key is configuring surge settings that account for spot preemptions and ensuring workloads can tolerate the additional disruption.

## Spot VM Upgrade Challenges

**Preemption during upgrade:** Spot VMs can be preempted by Google Cloud at any time, including during the upgrade process. This creates a "double disruption" scenario:
- Normal upgrade eviction (planned)
- Spot preemption (unplanned, 30-second notice)

**Unpredictable timing:** Unlike on-demand upgrades with predictable drain timing, spot nodes may disappear mid-upgrade, potentially leaving pods in an unknown state.

**Capacity availability:** Spot capacity is not guaranteed. During upgrade, replacement spot nodes may not be available, causing the upgrade to stall until capacity becomes available.

## Recommended Upgrade Strategy

### 1. Increase surge capacity significantly
```bash
gcloud container node-pools update SPOT_NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 1
```

**Rationale:** Higher surge protects against spot preemptions during upgrade. If a surge node gets preempted, others can continue the upgrade process.

### 2. Mixed pool approach (if not already separated)

**Current state assessment:**
- Are spot and on-demand nodes in the same pool or separate pools?
- If mixed in one pool, consider separating them for better upgrade control

**Recommended topology:**
```bash
# Spot pool - higher surge, more tolerant settings
gcloud container node-pools update spot-pool \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 2

# On-demand pool - conservative settings
gcloud container node-pools update ondemand-pool \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### 3. Workload placement strategy

**Spot-tolerant workloads:**
- Batch processing
- Stateless services with multiple replicas
- Development/testing workloads

**On-demand for critical workloads:**
- Databases and stateful services
- Single-replica services
- Real-time processing

Use node selectors or node affinity to control placement:
```yaml
nodeSelector:
  cloud.google.com/gke-preemptible: "true"  # For spot VMs
```

## Pre-Upgrade Checklist (Spot-Specific)

```markdown
Spot VM Pre-Upgrade Checklist
- [ ] Spot capacity availability confirmed in target zones
- [ ] Surge settings increased: maxSurge=3, maxUnavailable=1-2
- [ ] Workload distribution reviewed (spot-tolerant vs. critical)
- [ ] PDBs configured but not overly restrictive (spot + upgrade = high disruption)
- [ ] Monitoring alert for spot preemption rate during upgrade window
- [ ] Backup on-demand capacity available if spot upgrade stalls
- [ ] terminationGracePeriodSeconds ≤ 30 seconds (spot preemption limit)
```

## Upgrade Commands

### Pre-flight checks
```bash
# Check current node pool composition
kubectl get nodes -l cloud.google.com/gke-preemptible=true -o wide

# Verify workload distribution
kubectl get pods -A -o wide | grep NODE_NAME

# Check recent spot preemption rate
gcloud logging read 'resource.type="k8s_node" AND jsonPayload.reason="Preempted"' \
  --limit=50 --format="table(timestamp, jsonPayload.involvedObject.name)"
```

### Configure surge for spot pools
```bash
gcloud container node-pools update SPOT_NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 2
```

### Upgrade sequence
```bash
# 1. Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32

# 2. Upgrade on-demand pools first (more predictable)
gcloud container node-pools upgrade ONDEMAND_NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# 3. Upgrade spot pools last
gcloud container node-pools upgrade SPOT_NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

## Monitoring During Upgrade

```bash
# Watch node status and preemptions
watch 'kubectl get nodes -l cloud.google.com/gke-preemptible=true'

# Monitor for preemption events
kubectl get events -A --field-selector reason=Preempted --watch

# Check upgrade progress
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --limit=1
```

## Troubleshooting Spot VM Upgrade Issues

**Issue:** Upgrade stalls due to no spot capacity
```bash
# Check for pending nodes
kubectl get nodes | grep NotReady

# Look for capacity-related events
kubectl get events -A --field-selector reason=FailedScheduling
```

**Fix:** Temporarily add an on-demand node pool as surge capacity:
```bash
gcloud container node-pools create temp-ondemand-surge \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --machine-type MACHINE_TYPE \
  --num-nodes 2 \
  --cluster-version 1.32
```

**Issue:** High preemption rate during upgrade
- This is expected behavior
- Monitor that workloads reschedule successfully
- Consider pausing upgrade during high preemption periods if critical

## Post-Upgrade Validation

```bash
# Verify all spot nodes upgraded
kubectl get nodes -l cloud.google.com/gke-preemptible=true \
  -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion

# Check workload health after dual disruption
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded

# Verify no stuck PDBs from preemption events
kubectl get pdb -A -o wide
```

## Key Recommendations

1. **Higher surge is critical** for spot pools — use `maxSurge=3` minimum
2. **Separate spot and on-demand** into different node pools for upgrade control
3. **Upgrade on-demand first** for more predictable baseline capacity
4. **Monitor preemption rates** and pause upgrade if excessive
5. **Keep termination grace periods ≤ 30 seconds** (spot preemption limit)
6. **Have backup on-demand capacity** ready if spot upgrade stalls

The 1.31 → 1.32 upgrade itself has no spot-specific breaking changes, but the upgrade process mechanics require these spot-aware configurations.
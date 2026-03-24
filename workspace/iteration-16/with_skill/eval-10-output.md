# GKE Upgrade Plan: Mixed Spot/On-Demand Node Pool

## Spot VM Upgrade Considerations

Spot instances have unique characteristics that actually make them **safer** to upgrade than on-demand instances:

### Key Advantages for Spot VMs
- **Workloads are already preemption-tolerant** by design — they handle interruption gracefully
- **Lower upgrade risk** — if something goes wrong during upgrade, it's similar to a normal spot preemption
- **Faster recovery** — spot workloads typically have built-in restart/retry logic

## Recommended Upgrade Strategy

### 1. Upgrade Order: Spot First
```bash
# Upgrade spot node pool FIRST, then on-demand
# This validates your upgrade settings with lower-risk workloads
```

**Rationale:** Use spot pools as a "canary" for your upgrade process. If there are issues with PDBs, surge settings, or drain timing, you'll discover them on workloads that already handle disruption well.

### 2. Surge Settings for Mixed Pool

Since you have a **single** node pool with mixed instance types, configure surge settings optimized for spot characteristics:

```bash
# Configure more aggressive surge settings (spot workloads tolerate disruption)
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5 \
  --max-unavailable-upgrade 1
```

**Settings explanation:**
- **maxSurge=5**: Higher than typical (2-3% of pool size) because spot workloads handle restarts well
- **maxUnavailable=1**: Allow some nodes to drain simultaneously since workloads tolerate interruption

### 3. Pre-Upgrade Checklist

```markdown
## Mixed Spot/On-Demand Pre-Upgrade Checklist

Infrastructure
- [ ] Current version: 1.31 | Target: 1.32 | Channel: ___
- [ ] Spot workloads have proper restart/retry logic
- [ ] PDBs configured but not overly restrictive (spot workloads should allow more disruption)
- [ ] On-demand workloads identified for extra protection

Spot-Specific Readiness  
- [ ] Spot workloads use Deployments/ReplicaSets (not StatefulSets)
- [ ] Batch jobs have checkpoint/resume capability
- [ ] No bare pods on spot instances
- [ ] terminationGracePeriodSeconds ≤ 30s for spot workloads (they should shut down quickly)

PDB Strategy
- [ ] Separate PDBs for spot vs on-demand workloads (if possible)
- [ ] Spot workload PDBs allow more disruption: maxUnavailable=50% or higher
- [ ] Critical on-demand workloads have conservative PDBs: minAvailable=1 or 50%
```

### 4. Upgrade Commands

```bash
# 1. Pre-flight check
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].version)"

# 2. Control plane first (standard process)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32

# 3. Configure node pool for mixed workload upgrade
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5 \
  --max-unavailable-upgrade 1

# 4. Upgrade node pool
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# 5. Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-preemptible'
```

### 5. Special Considerations

**PDB Configuration:**
- **Spot workloads**: Use more permissive PDBs — `maxUnavailable: 50%` or `maxUnavailable: 2`
- **On-demand workloads**: Use conservative PDBs — `minAvailable: 1` or `minAvailable: 50%`

**Node Affinity:**
If you have critical workloads that must stay on on-demand instances during upgrade:
```yaml
affinity:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
      - matchExpressions:
        - key: cloud.google.com/gke-preemptible
          operator: DoesNotExist
```

**Monitoring During Upgrade:**
```bash
# Watch for spot preemptions vs upgrade evictions
kubectl get events -A --field-selector reason=Preempted,reason=Killing

# Monitor workload distribution
kubectl get pods -o wide -l app=YOUR_APP | grep -c gke-preemptible
```

## Expected Behavior

During the upgrade:
1. **Spot nodes** will be cordoned, drained, and replaced (similar to preemption)
2. **Workloads** will reschedule to available nodes (spot or on-demand)
3. **Some workloads** may temporarily land on on-demand nodes during upgrade
4. **New spot nodes** will come online and attract workloads back

This is normal and handled automatically by Kubernetes scheduler and your workload tolerations.

## Rollback Plan

If issues arise:
```bash
# Cancel in-progress upgrade
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE

# Spot workloads are resilient to rollback too
# Standard rollback procedures apply
```

The key advantage: **spot workloads make upgrades more forgiving**, not more complex. Your existing preemption-tolerance gives you built-in upgrade resilience.
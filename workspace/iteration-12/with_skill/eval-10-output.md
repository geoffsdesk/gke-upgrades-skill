# GKE Upgrade Plan: Standard Cluster with Spot VMs (1.31→1.32)

## Spot VM Upgrade Considerations

**Key insight:** Spot VMs add eviction unpredictability during upgrades. You'll face both planned eviction (upgrade process) and potential unplanned eviction (spot preemption) simultaneously.

### Primary Considerations

**1. Dual eviction risk**
- Normal upgrade process: controlled drain with `terminationGracePeriodSeconds`
- Spot preemption: 30-second notice, immediate termination
- **Risk:** Pods may be preempted while waiting to drain during upgrade, causing cascading disruption

**2. Replacement node availability**
- Spot VMs may not be available in the same zone during surge upgrades
- If `maxSurge` can't provision spot replacement nodes, upgrade stalls
- **Mitigation:** Configure fallback to on-demand for surge capacity

**3. Workload tolerance**
- Stateless workloads: generally fine with spot
- Stateful workloads: avoid spot entirely or use very conservative upgrade settings

## Recommended Upgrade Strategy

### Option A: Conservative Surge (Recommended)
```bash
# Configure conservative surge settings
gcloud container node-pools update YOUR_SPOT_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# This creates ONE replacement node at a time, waits for successful drain
```

**Pros:** Minimal resource disruption, controlled pace
**Cons:** Slower upgrade (especially for large pools)

### Option B: Mixed Pool Strategy (Best Practice)
If you have both spot and on-demand nodes in the SAME pool, consider splitting them:

```bash
# Create separate on-demand pool
gcloud container node-pools create on-demand-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --machine-type n1-standard-4 \
  --num-nodes 3 \
  --cluster-version 1.32.x-gke.xxx \
  --preemptible=false

# Create separate spot pool  
gcloud container node-pools create spot-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --machine-type n1-standard-4 \
  --num-nodes 5 \
  --cluster-version 1.32.x-gke.xxx \
  --preemptible=true
```

Then upgrade pools separately with different strategies.

### Option C: Blue-Green for Critical Workloads
For workloads that can't tolerate dual eviction risk:

```bash
# Use GKE's blue-green upgrade strategy
gcloud container node-pools update SPOT_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-blue-green-update \
  --blue-green-update-policy-node-pool-soak-duration=600s
```

**Note:** Blue-green requires 2x capacity - may be challenging with spot availability.

## Workload-Specific Guidance

### Stateless Applications (web servers, APIs)
- **Strategy:** Surge upgrade with `maxSurge=1-2, maxUnavailable=0`
- **PDB:** Set `maxUnavailable: 25%` to allow some disruption
- **Recommendation:** These handle spot eviction well during upgrades

### Stateful Applications (databases, caches)
- **Strategy:** Avoid spot VMs entirely for stateful workloads
- **If must use spot:** `maxSurge=0, maxUnavailable=1` with strict PDBs
- **Recommendation:** Move to on-demand node pool before upgrading

### Batch/Job Workloads
- **Strategy:** Drain completely before upgrade
- **Commands:**
```bash
# Scale down batch workloads
kubectl scale deployment batch-processor --replicas=0
# Proceed with upgrade
# Scale back up after completion
```

## Pre-Upgrade Checklist

```markdown
Spot VM Upgrade Checklist
- [ ] Spot instance availability confirmed in target zones
- [ ] Workload tolerance assessed (stateless vs stateful)
- [ ] PDBs configured appropriately for dual eviction risk
- [ ] Node taints/tolerations reviewed (spot vs on-demand scheduling)
- [ ] Cluster autoscaler settings checked (if enabled)
- [ ] Monitoring configured for both spot preemption AND upgrade events
```

## Monitoring During Upgrade

Watch for both upgrade events AND spot preemption:

```bash
# Monitor upgrade progress
kubectl get events -A --field-selector reason=NodeUpgrade -w

# Monitor spot preemption
kubectl get events -A --field-selector reason=Preempted -w

# Track node availability
watch 'kubectl get nodes -l cloud.google.com/gke-preemptible=true'
```

## Troubleshooting Spot-Specific Issues

**Issue:** Surge nodes won't provision (spot unavailable)
```bash
# Check for FailedCreate events
kubectl get events -A --field-selector reason=FailedCreate

# Fallback: increase maxUnavailable instead
gcloud container node-pools update SPOT_POOL \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

**Issue:** Workloads stuck on terminating spot nodes
```bash
# Force delete stuck pods (last resort)
kubectl delete pod POD_NAME --grace-period=0 --force
```

## Recommendation Summary

For a mixed spot/on-demand environment upgrading 1.31→1.32:

1. **Separate node pools** by instance type (spot vs on-demand) if not already done
2. **Upgrade on-demand pools first** using standard surge strategy
3. **Upgrade spot pools second** with conservative settings (`maxSurge=1, maxUnavailable=0`)
4. **Monitor aggressively** for both upgrade stalls and spot preemption cascades
5. **Consider maintenance windows** during low-traffic periods to minimize dual eviction impact

The 1.31→1.32 upgrade itself has no breaking changes affecting spot VMs specifically, but the dual eviction risk makes upgrade strategy more critical than with regular VMs.
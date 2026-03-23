# GKE Upgrade Plan for Long-Running Batch Jobs

## Situation Analysis

Your 8-16 hour batch jobs are exactly the scenario where **maintenance exclusions** are critical. GKE's default pod eviction timeout during upgrades is only 1 hour, which will force-kill your long-running jobs. Here's a comprehensive upgrade strategy:

## Recommended Approach: Maintenance Exclusions + Scheduled Upgrades

### 1. Apply "No Minor or Node Upgrades" Exclusion

This blocks disruptive upgrades while still allowing control plane security patches:

```bash
# Apply exclusion until end of support for 1.30
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "batch-job-protection" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
```

This exclusion:
- ✅ Blocks the 1.30→1.31 minor upgrade and all node pool upgrades
- ✅ Still allows control plane security patches  
- ✅ Automatically tracks the 1.30 End of Support date
- ✅ No need to chain 6-month exclusions

### 2. Plan Manual Upgrades During Batch Job Gaps

**Control Plane Upgrade** (can be done anytime - doesn't disrupt running jobs):
```bash
gcloud container clusters upgrade CLUSTER_NAME \
    --zone ZONE \
    --master \
    --cluster-version 1.31.x-gke.latest
```

**Node Pool Upgrade** (wait for job completion gap):
```bash
# When ready, configure conservative settings for batch workloads
gcloud container node-pools update NODE_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --max-surge-upgrade 1 \
    --max-unavailable-upgrade 0

# Then upgrade
gcloud container node-pools upgrade NODE_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version 1.31.x-gke.latest
```

## Alternative: Dedicated Batch Node Pool Strategy

If you have mixed workloads, isolate batch jobs on a dedicated node pool:

### Setup
```bash
# Create dedicated batch node pool (if not already separated)
gcloud container node-pools create batch-jobs \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --machine-type e2-standard-8 \
    --num-nodes 3 \
    --node-taints=workload=batch:NoSchedule

# Apply per-nodepool exclusion for batch pool only
gcloud container node-pools update batch-jobs \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "batch-protection" \
    --add-maintenance-exclusion-scope no_upgrades \
    --add-maintenance-exclusion-start-time 2024-12-15T00:00:00Z \
    --add-maintenance-exclusion-end-time 2025-06-15T00:00:00Z
```

### Benefits
- Other node pools can auto-upgrade normally
- Batch pool stays frozen until you manually upgrade during job gaps
- Better resource isolation and cost control

## Upgrade Timing Strategy

### Pre-Upgrade Checklist
```
- [ ] All active batch jobs cataloged with expected completion times
- [ ] Job queue monitoring in place to identify natural gaps
- [ ] Batch job checkpointing verified (jobs can resume if needed)
- [ ] PDBs configured on batch workloads (even if conservative)
- [ ] Maintenance exclusion applied and verified
- [ ] Rollback plan documented
```

### Execution Windows
1. **Control plane upgrade**: Can be done immediately (no job disruption)
2. **Node pool upgrade**: Schedule during identified gaps between batch runs
3. **Validation period**: 24-48 hours to ensure stability before removing exclusion

## Monitoring Commands

Track your exclusions and upgrade readiness:
```bash
# Check current exclusions
gcloud container clusters describe CLUSTER_NAME \
    --zone ZONE \
    --format="table(maintenancePolicy.window.maintenanceExclusions[].name,maintenancePolicy.window.maintenanceExclusions[].scope,maintenancePolicy.window.maintenanceExclusions[].endTime)"

# Monitor active batch jobs
kubectl get jobs -A --field-selector status.conditions[0].type=Complete \
    --field-selector status.conditions[0].status!=True

# Check upgrade target
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION
```

## Long-term Recommendations

1. **Job orchestration**: Consider implementing job queuing (Cloud Tasks, Kubernetes Jobs with queues) to better control when long jobs start
2. **Checkpointing**: Ensure all batch jobs save progress checkpoints every 1-2 hours
3. **Node pool strategy**: Keep batch workloads on separate pools with different maintenance policies
4. **Monitoring**: Set up alerts when jobs run longer than expected to avoid upgrade conflicts

## When to Remove the Exclusion

After successful upgrade and validation:
```bash
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --remove-maintenance-exclusion-name "batch-job-protection"
```

This approach gives you complete control over upgrade timing while still getting security patches on the control plane. The exclusion acts as a safety net until you're ready to upgrade during a natural gap in your batch processing schedule.
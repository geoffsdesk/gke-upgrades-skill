# GKE Upgrade Plan for Long-Running Batch Jobs

## Executive Summary

Your batch jobs (8-16 hours) need protection during the upgrade since GKE's default 1-hour pod eviction timeout is far shorter than your job duration. The recommended approach is to use **maintenance exclusions** to block node upgrades during active batch periods, then upgrade during natural job gaps.

## Current State Analysis

- **Cluster**: Standard GKE on Regular channel
- **Upgrade path**: 1.30 → 1.31 (single minor version jump ✓)
- **Challenge**: Batch jobs 8-16 hours vs. GKE 1-hour eviction timeout
- **Risk**: Job termination = lost work + restart from beginning

## Recommended Strategy: Maintenance Exclusion + Scheduled Upgrade Windows

### Phase 1: Immediate Protection (Control Plane Only)
Allow the control plane to upgrade to 1.31 while protecting your batch workloads from node disruption.

```bash
# Let control plane upgrade, block node pool upgrades during batch periods
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "batch-job-protection" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time "2024-XX-XXTHH:MM:SSZ" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

**Why this scope**: "no_minor_or_node_upgrades" blocks disruptive node pool changes but still allows control plane security patches.

### Phase 2: Node Pool Upgrade During Job Gaps

**Pre-flight Commands:**
```bash
# Check current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].version)"

# Verify no long-running batch jobs active
kubectl get pods -A --field-selector=status.phase=Running \
  -o custom-columns="NAMESPACE:.metadata.namespace,NAME:.metadata.name,AGE:.status.startTime"
```

**Configure Conservative Surge Settings:**
```bash
# Set conservative upgrade strategy to minimize disruption
gcloud container node-pools update BATCH_NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**Execute Node Pool Upgrade:**
```bash
# Remove exclusion during maintenance window
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "batch-job-protection"

# Upgrade node pool
gcloud container node-pools upgrade BATCH_NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.X-gke.XXXX

# Monitor progress (should take 30-60 min for modest-sized pools)
watch 'kubectl get nodes -L cloud.google.com/gke-nodepool'
```

## Alternative Strategy: Dedicated Batch Node Pool

For continuous batch processing, consider isolating batch workloads on a dedicated node pool with different upgrade timing:

```bash
# Create dedicated batch pool with auto-upgrade disabled
gcloud container node-pools create batch-workers \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --machine-type n1-standard-8 \
  --num-nodes 3 \
  --enable-autoupgrade=false \
  --node-version 1.30.X-gke.XXXX

# Taint for batch workloads only
kubectl taint nodes -l cloud.google.com/gke-nodepool=batch-workers \
  workload-type=batch:NoSchedule
```

Update your batch Job specs:
```yaml
spec:
  template:
    spec:
      nodeSelector:
        cloud.google.com/gke-nodepool: batch-workers
      tolerations:
      - key: workload-type
        operator: Equal
        value: batch
        effect: NoSchedule
```

**Important**: Disabling auto-upgrade requires manual lifecycle management and security patching responsibility.

## Workload Protection Checklist

```
Batch Job Protection Checklist
- [ ] PodDisruptionBudgets configured for critical batch jobs
      Example: maxUnavailable: 0 (prevents any eviction)
- [ ] Jobs use proper controllers (Job/CronJob) not bare pods
- [ ] terminationGracePeriodSeconds adequate for cleanup (default 30s may be too short)
- [ ] Batch jobs have checkpointing/resumability where possible
- [ ] Non-critical workloads identified for potential scaling down during upgrade
- [ ] Monitoring active to detect job interruptions
```

## Timeline & Execution

**Week 1: Preparation**
- Configure maintenance exclusion for node pools
- Allow control plane upgrade to 1.31 (automatic, non-disruptive)
- Test batch job behavior on 1.31 control plane

**Week 2: Node Upgrade Window**
- Schedule 4-6 hour maintenance window when no batch jobs running
- Remove maintenance exclusion
- Execute node pool upgrade with conservative surge settings
- Validate batch job scheduling post-upgrade

## Validation Commands

```bash
# Confirm versions post-upgrade
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"

gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE

# Verify batch jobs can schedule
kubectl get pods -A | grep -E "batch|job"
kubectl get nodes --show-labels | grep batch-workers

# Test batch job submission
kubectl create job test-batch --image=busybox -- sleep 300
kubectl get job test-batch -w
```

## Troubleshooting

**If batch jobs get evicted during upgrade:**
1. Check PDB configuration: `kubectl get pdb -A`
2. Verify surge settings allow zero unavailable nodes
3. Consider cordoning specific nodes to drain gradually

**If upgrade stalls:**
1. Check for stuck PDBs: `kubectl describe pdb PDB_NAME`
2. Temporarily relax PDB: `kubectl patch pdb PDB_NAME -p '{"spec":{"maxUnavailable":"100%"}}'`
3. Restore original PDB after upgrade completes

This approach gives you maximum control over upgrade timing while maintaining GKE's automated lifecycle benefits for non-critical workloads.
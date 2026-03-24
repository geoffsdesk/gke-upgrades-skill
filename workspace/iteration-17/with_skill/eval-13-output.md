# GKE Upgrade Plan for Long-Running Batch Jobs

## Executive Summary

For 8-16 hour batch jobs, GKE's default surge upgrade strategy will **force-evict jobs after 1 hour**, causing significant data loss. You need either **autoscaled blue-green upgrades** (respects longer termination periods) or **maintenance exclusions** to block upgrades during active batch campaigns.

## Recommended Strategy

### Option 1: Autoscaled Blue-Green Upgrade (Preferred)

Autoscaled blue-green is the **only native GKE strategy** that respects termination periods longer than 1 hour. It creates new nodes, gracefully drains old nodes without force-eviction, and scales down the old pool as jobs complete naturally.

```bash
# Configure autoscaled blue-green for batch node pools
gcloud container node-pools update BATCH_NODE_POOL \
  --cluster CLUSTER_NAME \
  --region REGION \
  --enable-autoscaling \
  --total-min-nodes 0 --total-max-nodes 50 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

**Key advantages:**
- Respects `terminationGracePeriodSeconds` up to your job duration (set to 57600s for 16h jobs)
- Cost-efficient — scales down old nodes as jobs drain to new nodes
- Jobs complete naturally without interruption
- Built-in rollback capability during the drain phase

### Option 2: Maintenance Exclusions During Batch Campaigns

Block node pool upgrades during active batch processing using maintenance exclusions:

```bash
# Block node upgrades during batch campaign (allows CP security patches)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "batch-campaign-jan2024" \
  --add-maintenance-exclusion-start-time "2024-01-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-01-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

Upgrade during scheduled gaps between batch campaigns when nodes are idle.

## Detailed Implementation Plan

### Pre-Upgrade Configuration

#### 1. Configure Batch Job Termination Periods

Ensure your batch jobs have appropriate termination grace periods:

```yaml
# In your batch Job/CronJob spec
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 57600  # 16 hours
      containers:
      - name: batch-processor
        image: your-batch-image
        # Ensure jobs handle SIGTERM gracefully for checkpointing
```

#### 2. Implement Checkpointing

Critical for recovery if interruption occurs:

```bash
# Example checkpoint logic in your batch job
trap 'echo "Received SIGTERM, checkpointing..."; save_checkpoint; exit 0' TERM

# Save progress periodically
save_checkpoint() {
  echo "Progress: $current_item/$total_items" > /data/checkpoint.txt
  # Save processed data, state, etc.
}
```

#### 3. Set Up Dedicated Batch Node Pool (Recommended)

Isolate batch workloads for independent upgrade control:

```bash
# Create dedicated batch node pool with taints
gcloud container node-pools create batch-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --machine-type n1-standard-4 \
  --num-nodes 3 \
  --enable-autoscaling --min-nodes 0 --max-nodes 20 \
  --node-taints batch-workload=true:NoSchedule
```

Schedule batch jobs only on this pool:
```yaml
spec:
  template:
    spec:
      tolerations:
      - key: batch-workload
        operator: Equal
        value: "true"
        effect: NoSchedule
      nodeSelector:
        cloud.google.com/gke-nodepool: batch-pool
```

### Upgrade Execution

#### Step 1: Control Plane Upgrade

Control plane upgrades don't affect running workloads:

```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version 1.31.5-gke.1503000
```

#### Step 2: Upgrade Non-Batch Node Pools First

Use standard surge upgrade for stateless workloads:

```bash
gcloud container node-pools update web-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade web-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.31.5-gke.1503000
```

#### Step 3: Wait for Batch Campaign Completion

Monitor active jobs before upgrading batch pool:

```bash
# Check running batch jobs
kubectl get jobs -n batch-namespace
kubectl get pods -l job-name --field-selector=status.phase=Running

# Wait until no active batch jobs remain
```

#### Step 4: Upgrade Batch Pool with Autoscaled Blue-Green

```bash
# Configure autoscaled blue-green
gcloud container node-pools update batch-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --enable-autoscaling \
  --total-min-nodes 0 --total-max-nodes 20 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.30,blue-green-full-batch-timeout=7200s

# Start the upgrade
gcloud container node-pools upgrade batch-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.31.5-gke.1503000
```

### Alternative: Cordon and Wait Pattern

If you prefer maximum control:

```bash
# Cordon all batch nodes (prevents new job scheduling)
kubectl cordon -l cloud.google.com/gke-nodepool=batch-pool

# Wait for current jobs to complete naturally
watch 'kubectl get pods -l app=batch-job --field-selector=status.phase=Running'

# Once nodes are empty, upgrade the pool
gcloud container node-pools upgrade batch-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.31.5-gke.1503000

# Uncordon after upgrade completes
kubectl uncordon -l cloud.google.com/gke-nodepool=batch-pool
```

## Pre-Upgrade Checklist

```markdown
- [ ] Current version: 1.30 | Target version: 1.31
- [ ] Cluster: Standard | Channel: Regular ✓
- [ ] Batch jobs have checkpointing capability
- [ ] terminationGracePeriodSeconds set to job duration (57600s for 16h)
- [ ] Dedicated batch node pool configured with taints
- [ ] No active batch campaigns during upgrade window
- [ ] Autoscaled blue-green parameters calculated:
  - blue-green-initial-node-percentage: 30%
  - blue-green-full-batch-timeout: 7200s (2 hours for setup)
- [ ] Monitoring configured for job completion tracking
- [ ] Rollback plan documented
```

## Monitoring During Upgrade

```bash
# Monitor autoscaled blue-green progress
kubectl get nodes -l cloud.google.com/gke-nodepool=batch-pool -o wide

# Check if any jobs got rescheduled during drain
kubectl get events --field-selector involvedObject.kind=Pod | grep batch

# Verify no force-evictions occurred
kubectl get events --field-selector reason=Killing
```

## Long-term Recommendations

1. **Regular batch scheduling windows:** Plan batch campaigns around GKE's monthly release cadence
2. **Use Extended release channel:** For maximum upgrade predictability (24-month support)
3. **Implement robust checkpointing:** All batch jobs should save state every 15-30 minutes
4. **Consider batch node pool auto-scaling to zero:** When no jobs running, scale pool to 0 nodes for cost savings

This approach ensures your 8-16 hour batch jobs complete without interruption while keeping your cluster current on security patches.
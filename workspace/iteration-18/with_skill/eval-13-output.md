# GKE Upgrade Plan for Long-Running Batch Jobs

## Key Challenge
Standard surge upgrades force-evict pods after 1 hour, which will kill your 8-16 hour batch jobs. We need a strategy that respects your job duration.

## Recommended Strategy: Autoscaled Blue-Green Upgrade

**Why autoscaled blue-green is ideal for your use case:**
- Respects extended `terminationGracePeriodSeconds` (no 1-hour force-eviction)
- Cost-efficient compared to standard blue-green (scales down old pool as jobs complete)
- Allows jobs to finish naturally while new capacity becomes available
- Only native GKE strategy suitable for jobs exceeding 1 hour runtime

## Pre-Upgrade Configuration

### 1. Configure Long Termination Grace Period
Update your batch job specs to allow extended graceful termination:

```yaml
apiVersion: batch/v1
kind: Job
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 57600  # 16 hours in seconds
      containers:
      - name: batch-job
        # ... your job config
```

### 2. Enable Checkpointing (Critical)
Ensure your batch jobs can checkpoint and resume:
- Save progress every 30-60 minutes
- Store state in persistent storage (Cloud Storage, Filestore, etc.)
- Implement graceful shutdown handling for SIGTERM

## Upgrade Execution Plan

### Phase 1: Control Plane Upgrade
```bash
# Set maintenance exclusion to prevent auto-upgrades during planning
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "batch-upgrade-control" \
  --add-maintenance-exclusion-start $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end $(date -u -d '+7 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades

# Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version 1.31.x-gke.latest

# Verify control plane upgrade
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="value(currentMasterVersion)"
```

### Phase 2: Node Pool Autoscaled Blue-Green Configuration
```bash
# Configure autoscaled blue-green for your batch node pool
gcloud container node-pools update BATCH_NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --enable-autoscaling \
  --total-min-nodes 0 \
  --total-max-nodes MAX_NODES \
  --strategy AUTOSCALED_BLUE_GREEN \
  --autoscaled-rollout-policy blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

### Phase 3: Execute Node Pool Upgrade
```bash
# Start the upgrade - this will:
# 1. Create green pool with 25% of nodes
# 2. Cordon blue pool
# 3. Scale down blue pool as jobs complete naturally
# 4. Scale up green pool based on demand
gcloud container node-pools upgrade BATCH_NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.31.x-gke.latest
```

## Monitoring During Upgrade

### Track Job Progress
```bash
# Monitor running jobs
kubectl get jobs -A --watch

# Check which nodes are running batch jobs
kubectl get pods -o wide --field-selector status.phase=Running | grep batch

# Monitor node pool transition
watch 'kubectl get nodes -L cloud.google.com/gke-nodepool'
```

### Monitor Autoscaling Behavior
```bash
# Watch node pool scaling
kubectl get nodes -L cloud.google.com/gke-nodepool --watch

# Check pod evictions (should be graceful, not forced)
kubectl get events --field-selector reason=Killing --watch
```

## Alternative Strategy: Dedicated Batch Pool with Maintenance Exclusion

If autoscaled blue-green is too complex, use this simpler approach:

### 1. Create Dedicated Batch Node Pool
```bash
# Create a separate node pool for batch jobs only
gcloud container node-pools create batch-dedicated \
  --cluster CLUSTER_NAME \
  --region REGION \
  --machine-type n2-standard-4 \
  --num-nodes 3 \
  --cluster-version 1.30.x-gke.current \
  --node-taints batch=true:NoSchedule
```

### 2. Apply Long-Term Maintenance Exclusion
```bash
# Block all upgrades on the batch pool until jobs complete
gcloud container node-pools update batch-dedicated \
  --cluster CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "batch-job-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

### 3. Schedule Batch Jobs on Dedicated Pool
```yaml
apiVersion: batch/v1
kind: Job
spec:
  template:
    spec:
      nodeSelector:
        cloud.google.com/gke-nodepool: batch-dedicated
      tolerations:
      - key: batch
        operator: Equal
        value: "true"
        effect: NoSchedule
```

### 4. Upgrade During Batch Downtime
When no critical batch jobs are running:
```bash
# Remove maintenance exclusion
gcloud container node-pools update batch-dedicated \
  --cluster CLUSTER_NAME \
  --region REGION \
  --remove-maintenance-exclusion "batch-job-protection"

# Upgrade the pool
gcloud container node-pools upgrade batch-dedicated \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.31.x-gke.latest
```

## Post-Upgrade Validation

```bash
# Verify all nodes at target version
gcloud container node-pools list --cluster CLUSTER_NAME --region REGION

# Test batch job submission
kubectl create job test-batch --image=busybox -- sleep 300
kubectl get jobs test-batch --watch

# Remove temporary maintenance exclusion
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --remove-maintenance-exclusion "batch-upgrade-control"
```

## Recommendations

1. **Use autoscaled blue-green** - It's the only native GKE strategy that respects long termination periods
2. **Test in staging first** - Validate the upgrade process with representative batch workloads
3. **Monitor job checkpointing** - Ensure jobs can actually resume if interrupted
4. **Plan for 24-48 hour upgrade window** - Long-running jobs mean longer upgrade duration
5. **Consider job scheduling coordination** - Pause new job submissions during the upgrade window

This approach ensures your batch jobs complete naturally while transitioning to the new version without the 1-hour force-eviction limitation of standard surge upgrades.
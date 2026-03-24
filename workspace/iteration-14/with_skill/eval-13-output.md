# GKE Upgrade Plan for Long-Running Batch Workloads

## Strategy: Autoscaled Blue-Green with Extended Termination Grace

For 8-16 hour batch jobs, GKE's standard surge upgrade will force-evict your jobs after 1 hour. **Autoscaled blue-green is the optimal strategy** as it respects longer graceful termination periods and doesn't have the 1-hour eviction timeout.

## Pre-Upgrade Configuration

### 1. Enable Autoscaling on Batch Node Pools
```bash
# Configure autoscaling for batch node pools
gcloud container node-pools update BATCH_NODE_POOL \
  --cluster CLUSTER_NAME \
  --region REGION \
  --enable-autoscaling \
  --total-min-nodes 0 \
  --total-max-nodes MAX_NODES
```

### 2. Set Extended Termination Grace Period
Update your batch job pods to allow sufficient time for graceful termination:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: long-running-batch
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 57600  # 16 hours
      containers:
      - name: batch-processor
        image: your-batch-image
        # Ensure your application handles SIGTERM gracefully
```

### 3. Configure Maintenance Exclusion for Active Jobs
```bash
# Block upgrades during critical batch processing periods
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "batch-campaign-dec2024" \
  --add-maintenance-exclusion-start-time 2024-12-01T00:00:00Z \
  --add-maintenance-exclusion-end-time 2024-12-15T23:59:59Z \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

## Upgrade Execution Plan

### Phase 1: Control Plane Upgrade
```bash
# Upgrade control plane first (safe - no job disruption)
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version 1.31.latest
```

### Phase 2: Coordinate Batch Job Window
1. **Monitor active jobs:**
```bash
kubectl get jobs -A -o wide
kubectl get pods -A -l job-name --field-selector=status.phase=Running
```

2. **Pause new job submissions** 30 minutes before upgrade window
3. **Wait for current jobs to complete naturally** (monitor via your batch orchestrator)

### Phase 3: Node Pool Upgrade with Autoscaled Blue-Green
```bash
# Configure autoscaled blue-green upgrade
gcloud container node-pools update BATCH_NODE_POOL \
  --cluster CLUSTER_NAME \
  --region REGION \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=7200s

# Execute upgrade
gcloud container node-pools upgrade BATCH_NODE_POOL \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.31.latest
```

### Phase 4: Monitor and Validate
```bash
# Watch the upgrade progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Monitor batch workload health
kubectl get jobs -A
kubectl get pods -A | grep batch
```

## Alternative Approach: Dedicated Batch Pool Strategy

If you run batch jobs continuously with minimal gaps, consider this architecture:

### 1. Create Dedicated Batch Pool
```bash
gcloud container node-pools create batch-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --machine-type c2-standard-16 \
  --num-nodes 3 \
  --enable-autoscaling \
  --min-nodes 0 \
  --max-nodes 20 \
  --cluster-version 1.30.latest
```

### 2. Apply Long-Term Maintenance Exclusion
```bash
# Block auto-upgrades on the batch pool until scheduled maintenance
gcloud container node-pools update batch-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "batch-pool-hold" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

### 3. Node Taints and Tolerations
```bash
# Taint the batch pool so only batch jobs schedule there
gcloud container node-pools update batch-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --node-taints workload-type=batch:NoSchedule
```

Add tolerations to your batch jobs:
```yaml
apiVersion: batch/v1
kind: Job
spec:
  template:
    spec:
      tolerations:
      - key: "workload-type"
        operator: "Equal"
        value: "batch"
        effect: "NoSchedule"
      nodeSelector:
        cloud.google.com/gke-nodepool: batch-pool
```

## Pre-Upgrade Checklist

```markdown
Pre-Upgrade Checklist - Batch Processing Workloads
- [ ] Cluster: ___ | Mode: Standard | Channel: Regular
- [ ] Current: 1.30.x | Target: 1.31.latest
- [ ] Batch job runtime confirmed: 8-16 hours
- [ ] terminationGracePeriodSeconds set to exceed max job duration (57600s)
- [ ] Batch jobs handle SIGTERM gracefully with checkpointing
- [ ] Autoscaling enabled on batch node pools
- [ ] Autoscaled blue-green rollout policy configured
- [ ] Current batch job status reviewed - no critical jobs running
- [ ] New job submission paused during upgrade window
- [ ] Monitoring in place for job completion status
- [ ] Rollback plan documented (cordon new nodes, reschedule on old)
```

## Key Benefits of This Approach

- **No forced eviction:** Autoscaled blue-green respects your 16-hour termination grace period
- **Cost efficient:** Old pool scales down as workloads migrate to new pool
- **Zero job loss:** Jobs complete naturally before nodes are terminated  
- **Maintains capacity:** Green pool scales up as blue pool drains

## Timeline Expectations

- **Control plane upgrade:** 10-15 minutes
- **Node pool upgrade:** 2-4 hours (depends on job completion timing)
- **Total window:** Plan for 4-6 hours to account for job completion variance

This strategy ensures your long-running batch jobs complete successfully while upgrading your cluster to GKE 1.31.
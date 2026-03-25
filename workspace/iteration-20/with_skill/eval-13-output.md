# GKE Upgrade Plan for Long-Running Batch Jobs

## Current Situation Analysis
- **Cluster**: Standard GKE on Regular release channel
- **Challenge**: 8-16 hour batch jobs cannot tolerate mid-upgrade eviction
- **GKE limitation**: Default surge upgrades force-evict pods after 1 hour, regardless of `terminationGracePeriodSeconds`

## Recommended Strategy: Autoscaled Blue-Green

**Why this strategy**: Autoscaled blue-green is the ONLY native GKE upgrade strategy that respects extended graceful termination periods without force-evicting after 1 hour. It's specifically designed for long-running workloads like yours.

### Configuration Commands

```bash
# 1. Enable autoscaling on your batch node pool
gcloud container node-pools update BATCH_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --enable-autoscaling \
  --total-min-nodes MIN_NODES \
  --total-max-nodes MAX_NODES

# 2. Configure autoscaled blue-green upgrade strategy
gcloud container node-pools update BATCH_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

# 3. Set extended termination grace period on batch workloads
# In your batch job spec:
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 57600  # 16 hours
```

### How Autoscaled Blue-Green Works
1. **Green pool creation**: Creates 25% of nodes with new version initially
2. **Blue pool cordon**: Cordons existing nodes (prevents new pod scheduling)
3. **Gradual migration**: As batch jobs complete naturally, green pool scales up to meet demand
4. **Blue pool scale-down**: Old nodes scale down as workloads drain
5. **Cost efficiency**: Avoids 2x resource cost of standard blue-green

## Alternative Strategy: Batch-Aware Manual Upgrade

If autoscaled blue-green isn't suitable, use this coordinated approach:

### Pre-Upgrade Preparation
```bash
# 1. Apply maintenance exclusion to prevent auto-upgrades
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "batch-campaign-freeze" \
  --add-maintenance-exclusion-start-time "2024-01-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-01-22T00:00:00Z" \
  --add-maintenance-exclusion-scope no_upgrades

# 2. Monitor active batch jobs
kubectl get jobs -A
kubectl get pods -A --field-selector=status.phase=Running | grep batch
```

### Upgrade Execution
```bash
# 3. Wait for natural job completion window
# Monitor until no 8+ hour jobs are running
watch 'kubectl get pods -A -o wide --sort-by=.status.startTime'

# 4. Upgrade control plane first (required order)
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version 1.31.0-gke.VERSION

# 5. Upgrade node pools with conservative settings
gcloud container node-pools update BATCH_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade BATCH_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.31.0-gke.VERSION
```

## Pre-Upgrade Checklist

```markdown
- [ ] **Batch workload inventory**: Identify all jobs with 8+ hour runtime
- [ ] **Job checkpoint capability**: Verify jobs can resume from checkpoint if interrupted
- [ ] **Termination grace period**: Set `terminationGracePeriodSeconds: 57600` (16h) on batch workloads
- [ ] **PDB configuration**: Set PDB with `minAvailable: 1` or appropriate count for batch jobs
- [ ] **Maintenance exclusion**: Apply "no upgrades" exclusion during active batch campaigns
- [ ] **Monitoring setup**: Configure alerts for job completion/failure rates
- [ ] **Staging validation**: Test upgrade strategy on non-production cluster first
- [ ] **Rollback plan**: Document how to cancel/resume upgrade if issues arise
```

## Monitoring During Upgrade

```bash
# Monitor job completion
kubectl get jobs -A --watch

# Check node upgrade progress
kubectl get nodes -o wide --sort-by=.metadata.creationTimestamp

# Verify no force-evictions
kubectl get events -A --field-selector reason=Killing --sort-by='.lastTimestamp'
```

## Key Advantages of This Approach

1. **Zero job interruption**: Jobs complete naturally before nodes drain
2. **Cost efficient**: Autoscaled blue-green avoids 2x resource cost
3. **Native GKE support**: Built-in strategy with full support
4. **Graceful termination**: Respects extended termination periods
5. **Rollback capability**: Can cancel during drain phase if needed

## Important Notes

- **Staging first**: Test this upgrade strategy on a non-production cluster with sample 8+ hour jobs
- **Capacity planning**: Ensure adequate quota for green pool scale-up during transition
- **Job design**: Batch jobs should have checkpointing for best resilience
- **Timing**: Plan upgrades during natural gaps between batch campaigns when possible

This approach ensures your long-running batch jobs complete successfully while keeping your cluster current with security patches and new features.
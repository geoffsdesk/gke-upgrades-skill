# GKE Upgrade Plan for Long-Running Batch Jobs

## Overview
**Cluster:** Standard GKE | **Channel:** Regular  
**Current:** 1.30 → **Target:** 1.31  
**Challenge:** 8-16 hour batch jobs cannot tolerate GKE's default 1-hour eviction timeout during surge upgrades

## Recommended Strategy: Autoscaled Blue-Green Upgrade

For batch jobs exceeding 1 hour, **autoscaled blue-green** is the ONLY native GKE strategy that respects extended graceful termination periods without force-eviction.

### Why Autoscaled Blue-Green?
- **Respects long `terminationGracePeriodSeconds`** (set to 57600s = 16 hours)
- **Cost-efficient**: Scales down old (blue) pool as jobs drain to new (green) pool
- **No force-eviction after 1 hour** unlike surge upgrades
- **Allows jobs to complete naturally** before node replacement

## Pre-Upgrade Configuration

### 1. Configure Batch Workloads
```bash
# Set extended termination grace period on batch jobs
kubectl patch deployment BATCH_JOB_DEPLOYMENT -p '
{
  "spec": {
    "template": {
      "spec": {
        "terminationGracePeriodSeconds": 57600
      }
    }
  }
}'
```

### 2. Enable Autoscaling on Batch Node Pool
```bash
gcloud container node-pools update BATCH_NODE_POOL \
    --cluster CLUSTER_NAME \
    --region REGION \
    --enable-autoscaling \
    --total-min-nodes 0 \
    --total-max-nodes 100
```

### 3. Set Maintenance Window for Batch Pool
```bash
# Schedule during off-peak hours when fewer jobs start
gcloud container clusters update CLUSTER_NAME \
    --region REGION \
    --maintenance-window-start "2024-12-21T02:00:00Z" \
    --maintenance-window-duration 8h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## Upgrade Execution

### Phase 1: Control Plane Upgrade
```bash
gcloud container clusters upgrade CLUSTER_NAME \
    --region REGION \
    --master \
    --cluster-version 1.31
```

### Phase 2: Node Pool Upgrade (Autoscaled Blue-Green)
```bash
gcloud container node-pools update BATCH_NODE_POOL \
    --cluster CLUSTER_NAME \
    --region REGION \
    --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

**Key Parameters:**
- `blue-green-initial-node-percentage=0.25`: Start green pool at 25% capacity
- `blue-green-full-batch-timeout=3600s`: 1-hour timeout for green pool readiness

## Alternative: Maintenance Exclusion Strategy

If autoscaled blue-green isn't suitable, use maintenance exclusions:

### 1. Block Node Upgrades During Batch Campaigns
```bash
gcloud container clusters update CLUSTER_NAME \
    --region REGION \
    --add-maintenance-exclusion-name "batch-campaign-freeze" \
    --add-maintenance-exclusion-start-time "2024-12-20T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2025-01-15T23:59:59Z" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

### 2. Plan Manual Upgrade During Job Gap
```bash
# Wait for current jobs to complete naturally
kubectl get pods -l app=batch-job --field-selector=status.phase=Running

# When jobs finish, trigger manual upgrade
gcloud container node-pools upgrade BATCH_NODE_POOL \
    --cluster CLUSTER_NAME \
    --region REGION \
    --cluster-version 1.31
```

## Pre-Upgrade Checklist

```
Long-Running Batch Job Upgrade Checklist
- [ ] Cluster: ___ | Current: 1.30 | Target: 1.31
- [ ] Batch job runtime: 8-16 hours confirmed

Workload Configuration
- [ ] terminationGracePeriodSeconds set to 57600s (16 hours) on batch jobs
- [ ] Jobs have checkpoint/resume capability verified
- [ ] No bare batch pods - all managed by Deployment/Job controller
- [ ] PDBs configured if running multiple batch replicas

Node Pool Setup (for autoscaled blue-green)
- [ ] Autoscaling enabled on batch node pool
- [ ] min-nodes=0, max-nodes adequate for blue-green scaling
- [ ] Sufficient quota for temporary scaling during upgrade
- [ ] Job scheduling anti-affinity prevents clustering on few nodes

Timing Strategy
- [ ] Maintenance window set for Saturday 2-10 AM (8 hours)
- [ ] Current batch campaign status checked
- [ ] No new batch jobs submitted 1 hour before upgrade window
- [ ] On-call team available during upgrade window

Alternative Exclusion Strategy
- [ ] "No minor or node upgrades" exclusion configured for batch campaign period
- [ ] Manual upgrade scheduled for next job gap
- [ ] Job completion monitoring in place
```

## Monitoring During Upgrade

```bash
# Monitor job completion
kubectl get pods -l app=batch-job --field-selector=status.phase=Running

# Watch node pool transition (autoscaled blue-green)
kubectl get nodes -l cloud.google.com/gke-nodepool=BATCH_NODE_POOL -o wide

# Monitor autoscaler scaling events
kubectl get events --field-selector reason=ScalingReplicaSet
```

## Post-Upgrade Validation

```bash
# Verify all nodes at target version
gcloud container node-pools describe BATCH_NODE_POOL \
    --cluster CLUSTER_NAME \
    --region REGION \
    --format="value(version)"

# Confirm batch jobs can start on new nodes
kubectl run test-batch --image=busybox --restart=Never \
    --overrides='{"spec":{"terminationGracePeriodSeconds":57600}}' \
    -- sleep 300

# Clean up test
kubectl delete pod test-batch
```

## Key Advantages of This Approach

1. **No job interruption**: 16-hour grace period respected
2. **Cost-efficient**: Blue pool scales down as green scales up
3. **Native GKE feature**: Fully supported, no custom scripting
4. **Automatic rollback**: Can revert during blue-green phases

## Important Notes

- **Surge upgrades WILL force-evict after 1 hour** - never use for 8+ hour jobs
- **Standard blue-green requires 2x resources** - autoscaled version is more cost-effective
- **Jobs must have proper signal handling** for graceful termination
- **Plan for 8+ hour upgrade window** to accommodate job completion

This approach ensures your long-running batch jobs complete naturally while still maintaining your cluster on supported versions.
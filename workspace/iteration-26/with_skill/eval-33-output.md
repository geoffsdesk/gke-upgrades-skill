# GKE ML Platform Upgrade Plan: 1.31 → 1.32

## Cluster Overview
- **Type:** Standard cluster with GPU node pools
- **Current:** 1.31 → **Target:** 1.32 (single minor version jump)
- **L4 pool:** 200 nodes (inference workloads)
- **A100 pool:** 100 nodes (inference + 4-8 hour fine-tuning)
- **Key constraint:** Minimal inference latency/availability impact

## Upgrade Strategy

### Recommended Approach: Autoscaled Blue-Green for GPU Pools

**Why autoscaled blue-green is optimal for your use case:**
- **Eliminates inference downtime:** Old pool continues serving while new pool warms up
- **Cost-efficient:** Scales down old pool as workloads migrate (avoids 2x cost of standard blue-green)
- **Respects long jobs:** Fine-tuning jobs get extended graceful termination (no 1-hour force eviction)
- **Handles autoscaling:** Works with cluster autoscaler and traffic-based scaling

**Alternative strategies rejected:**
- **Surge upgrade:** GPU VMs don't support live migration → every pod restart causes inference latency spikes
- **Standard blue-green:** 2x resource cost (600 total GPU nodes during upgrade) likely exceeds quota/budget

## Pre-Upgrade Preparation

### 1. Verify GPU Driver Compatibility
**Critical step:** GKE 1.32 may change CUDA versions silently.

```bash
# Create staging node pool with target version
gcloud container node-pools create staging-l4-132 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxxx \
  --machine-type g2-standard-24 \
  --accelerator type=nvidia-l4,count=2 \
  --num-nodes 2 \
  --enable-autoscaling --min-nodes=0 --max-nodes=5

# Deploy representative inference workloads
kubectl apply -f inference-test-deployment.yaml

# Validate model loading, CUDA calls, throughput
kubectl logs -f deployment/inference-test
```

### 2. Fine-tuning Job Management
```bash
# Check current fine-tuning jobs on A100 pool
kubectl get pods -l workload-type=fine-tuning -o wide

# Schedule upgrade window between training campaigns
# Option A: Wait for jobs to complete naturally
# Option B: Apply temporary "no upgrades" exclusion during active training
```

### 3. Configure Maintenance Controls
```bash
# Set maintenance window (off-peak hours)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-15T02:00:00Z" \
  --maintenance-window-duration 6h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SUN"
```

## Upgrade Execution

### Phase 1: Control Plane Upgrade (5-10 minutes)
```bash
# Upgrade control plane first (required before node pools)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.xxxx

# Verify CP health
kubectl get pods -n kube-system
kubectl get nodes  # Should still show 1.31 on nodes
```

### Phase 2: L4 Inference Pool (Lower Risk First)
```bash
# Configure autoscaled blue-green for L4 pool
gcloud container node-pools update l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-blue-green-upgrade \
  --enable-autoscaling \
  --total-min-nodes 50 --total-max-nodes 250 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

# Start upgrade
gcloud container node-pools upgrade l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxxx
```

**Monitor L4 upgrade progress:**
```bash
# Watch node versions and pod distribution
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=l4-inference-pool -o wide'
watch 'kubectl get pods -l app=inference -o wide'

# Check inference latency metrics in monitoring dashboard
# Validate no traffic drops during blue→green transition
```

### Phase 3: A100 Pool (After L4 Success + Fine-tuning Gap)
**Wait for:** L4 upgrade completion + fine-tuning jobs to finish

```bash
# Verify no active fine-tuning jobs
kubectl get pods -l workload-type=fine-tuning --field-selector=status.phase=Running

# Configure autoscaled blue-green for A100 pool
gcloud container node-pools update a100-training-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-blue-green-upgrade \
  --enable-autoscaling \
  --total-min-nodes 25 --total-max-nodes 125 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.20,blue-green-full-batch-timeout=7200s

# Start upgrade
gcloud container node-pools upgrade a100-training-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxxx
```

## Expected Timeline

| Phase | Duration | Notes |
|-------|----------|-------|
| Control plane | 5-10 min | No workload impact |
| L4 pool (200 nodes) | 2-4 hours | Autoscaled blue-green with gradual migration |
| Soak period | 1-2 hours | Validate L4 inference performance |
| A100 pool (100 nodes) | 1-3 hours | After fine-tuning jobs complete |
| **Total** | **4-9 hours** | Depends on fine-tuning job timing |

## Monitoring & Validation

### Key Metrics to Watch
```bash
# Inference latency (p95, p99)
# Model throughput (requests/sec)
# GPU utilization during transition
# Pod startup time on new nodes
# Autoscaler scaling decisions

# Check for failed pod creations
kubectl get events -A --field-selector type=Warning,reason=Failed
```

### Success Criteria
- [ ] All nodes at 1.32: `kubectl get nodes -o wide`
- [ ] Inference latency within 5% of baseline
- [ ] No inference traffic drops during upgrade
- [ ] Fine-tuning jobs can start on new nodes
- [ ] Autoscaler responding correctly to traffic

## Rollback Plan

If issues arise during blue-green upgrade:
```bash
# Cancel upgrade (before soak completes)
gcloud container operations cancel OPERATION_ID

# Roll back to blue pool
gcloud container node-pools complete-upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --rollback
```

## GPU-Specific Considerations

⚠️ **Critical:** GPU reservations may limit surge capacity. Autoscaled blue-green works within reservation constraints by scaling down the old pool as the new pool scales up.

⚠️ **Driver compatibility:** Test CUDA version changes thoroughly in staging before production.

⚠️ **Fine-tuning protection:** Long jobs (4-8h) benefit from autoscaled blue-green's extended graceful termination vs surge's 1-hour force eviction.

## Post-Upgrade Actions

1. **Remove staging node pool:** `gcloud container node-pools delete staging-l4-132`
2. **Resume fine-tuning job submissions**
3. **Monitor GPU driver stability over 24-48 hours**
4. **Update infrastructure-as-code with new version**

This plan prioritizes inference availability while safely handling your mixed GPU workloads. The autoscaled blue-green strategy eliminates the inference downtime that surge upgrades would cause on GPU nodes.
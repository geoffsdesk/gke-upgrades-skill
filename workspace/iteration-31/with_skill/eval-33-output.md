# GKE ML Platform Upgrade Plan: 1.31 → 1.32

## Cluster Overview
- **Cluster:** Standard GKE
- **Workloads:** GPU inference (L4) + fine-tuning jobs (A100, 4-8 hours)
- **Scale:** 200 L4 nodes + 100 A100 nodes with autoscaling
- **Priority:** Minimize inference latency/availability impact

## Recommended Strategy: Staged GPU Upgrade with Autoscaled Blue-Green

For GPU inference workloads, **autoscaled blue-green** is the optimal strategy. It avoids the inference latency spikes caused by surge drain-and-restart (GPU VMs don't support live migration) by keeping the old pool serving while the new pool warms up.

### Phase 1: Control Plane Upgrade (Low Impact)
**When:** During off-peak traffic
**Duration:** ~10-15 minutes

```bash
# Pre-flight check
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].version)"

# Control plane upgrade
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.latest

# Verify
kubectl get pods -n kube-system
```

### Phase 2: L4 Inference Pool (Autoscaled Blue-Green)
**Priority:** Upgrade L4 pool first - lower cost per node, validates strategy

```bash
# Configure autoscaled blue-green for L4 pool
gcloud container node-pools update l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 10 \
  --total-max-nodes 250 \
  --strategy=BLUE_GREEN \
  --node-pool-soak-duration=1800s \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.20,blue-green-full-batch-timeout=3600s

# Trigger upgrade
gcloud container node-pools upgrade l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**Key parameters:**
- `blue-green-initial-node-percentage=0.20`: Start green pool with 20% of current capacity
- Green pool auto-scales up as inference traffic shifts
- Blue pool scales down as pods drain
- `node-pool-soak-duration=1800s`: 30-min validation period before blue pool deletion
- No 2x resource cost spike (unlike standard blue-green)

### Phase 3: A100 Fine-tuning Pool (Coordinated with Job Schedule)
**Timing:** Schedule during fine-tuning job gap or checkpoint

```bash
# Check for running fine-tuning jobs
kubectl get pods -n ML_NAMESPACE -l workload-type=fine-tuning -o wide

# If jobs are running, either:
# Option A: Wait for natural completion (preferred)
# Option B: Checkpoint and pause new submissions

# Configure for A100 pool (smaller initial percentage due to higher cost)
gcloud container node-pools update a100-training-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 5 \
  --total-max-nodes 120 \
  --strategy=BLUE_GREEN \
  --node-pool-soak-duration=3600s \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.15,blue-green-full-batch-timeout=7200s

# Trigger upgrade
gcloud container node-pools upgrade a100-training-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**A100-specific considerations:**
- `blue-green-full-batch-timeout=7200s`: 2-hour timeout accommodates longer job startup
- Smaller initial green pool (15%) due to A100 cost
- Longer soak period (1 hour) for thorough validation

## Pre-Upgrade Checklist

```markdown
GPU ML Platform Pre-Upgrade Checklist
- [ ] Cluster: ___ | Current: 1.31.x | Target: 1.32.x | Channel: ___

Compatibility & Validation
- [ ] 1.32.x available in release channel
- [ ] GPU driver compatibility confirmed (GKE auto-installs drivers for 1.32)
- [ ] CUDA version compatibility tested with inference models
- [ ] Fine-tuning framework compatibility verified (TensorFlow/PyTorch)
- [ ] No deprecated API usage: `kubectl get --raw /metrics | grep deprecated`

ML Workload Readiness  
- [ ] PDBs configured for inference services (recommend minAvailable=50%)
- [ ] Fine-tuning jobs have checkpointing enabled
- [ ] Inference health checks and readiness probes configured
- [ ] Model serving containers have appropriate terminationGracePeriodSeconds (30-60s)
- [ ] Autoscaler metrics and policies reviewed

Infrastructure
- [ ] GPU quota sufficient for blue-green pools (check reservation headroom)
- [ ] Cluster autoscaler node group settings verified
- [ ] Monitoring baseline captured (inference latency p95/p99, GPU utilization)
- [ ] Load balancer health check thresholds noted

Operational
- [ ] Fine-tuning job schedule reviewed - identify upgrade windows
- [ ] Inference traffic patterns analyzed for optimal timing
- [ ] Rollback plan documented
- [ ] ML platform team on standby
```

## GPU-Specific Monitoring During Upgrade

```bash
# Monitor GPU node versions
kubectl get nodes -l cloud.google.com/gke-accelerator -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,GPU:.metadata.labels.cloud\.google\.com/gke-accelerator

# Check GPU utilization during transition  
kubectl top nodes -l cloud.google.com/gke-accelerator

# Monitor inference pod distribution
kubectl get pods -n ML_NAMESPACE -o wide -l workload-type=inference

# Watch autoscaler decisions
kubectl logs -n kube-system -l app=cluster-autoscaler --follow
```

## Expected Timeline & Behavior

**L4 Pool (200 nodes):**
- Initial green pool: ~40 L4 nodes (20%)
- Auto-scale up as inference traffic arrives
- Blue pool scales down as pods drain
- Total duration: 2-4 hours depending on traffic patterns

**A100 Pool (100 nodes):**
- Initial green pool: ~15 A100 nodes (15%) 
- Gradual expansion based on job submissions
- Total duration: 3-5 hours (longer due to job coordination)

## Key Advantages for ML Inference

1. **Zero inference downtime:** Old pool serves while new pool warms up
2. **Cost efficient:** Avoids 2x resource spike of standard blue-green
3. **Traffic-aware scaling:** Green pool grows with actual demand
4. **Extended job protection:** Respects longer fine-tuning job completion times
5. **Easy rollback:** During soak period, can quickly revert

## Troubleshooting GPU-Specific Issues

**Green pool nodes not registering GPUs:**
```bash
kubectl describe nodes -l cloud.google.com/gke-nodepool=POOL_NAME-green
# Check for GPU driver installation events
```

**Inference pods not scheduling to green pool:**
```bash
kubectl get events -n ML_NAMESPACE --field-selector reason=FailedScheduling
# May indicate GPU resource mismatches or node selector issues
```

**Autoscaler not scaling green pool:**
```bash
kubectl logs -n kube-system -l app=cluster-autoscaler | grep "scale up"
# Check for quota limits or node group configuration issues
```

This strategy minimizes inference disruption while handling your fine-tuning workloads gracefully. The autoscaled blue-green approach is specifically designed for cost-sensitive GPU workloads that can't tolerate the latency spikes of traditional surge upgrades.
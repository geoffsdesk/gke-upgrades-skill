# GKE GPU Inference & Fine-tuning Cluster Upgrade Plan

**Cluster Profile:**
- Mode: Standard | Channel: Not specified (assuming Regular)
- Current: 1.31 | Target: 1.32 (single minor jump)
- Workloads: GPU inference (latency-sensitive) + fine-tuning jobs (4-8h)
- Scale: 200 L4 nodes + 100 A100 nodes with autoscaling

## Executive Summary

For your GPU inference workloads, **autoscaled blue-green upgrade** is the optimal strategy. This avoids the inference latency spikes caused by surge drain-and-restart (GPU VMs don't support live migration). For the A100 fine-tuning workload, coordinate upgrades during job gaps or use maintenance exclusions.

## Pre-Upgrade Validation (Critical for GPU)

**GPU driver compatibility test (mandatory):**
```bash
# Create staging node pool at target version
gcloud container node-pools create staging-l4 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxx \
  --machine-type g2-standard-24 \
  --accelerator type=nvidia-l4,count=2 \
  --num-nodes 1

# Deploy representative inference workload and validate:
# - Model loading works
# - CUDA calls succeed
# - Throughput matches expectations
# Delete staging pool after validation
```

**Check GPU reservation capacity:**
```bash
# Verify reservation headroom for blue-green (needs replacement capacity)
gcloud compute reservations describe RESERVATION_NAME --zone ZONE
```

## Recommended Upgrade Strategy

### L4 Inference Pool (Priority 1)
**Strategy: Autoscaled Blue-Green**
- Cordons old pool while new pool scales up
- No inference downtime during transition
- Pods migrate gradually as traffic shifts

```bash
# Configure L4 pool for autoscaled blue-green
gcloud container node-pools update l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 20 \
  --total-max-nodes 200 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

# Upgrade L4 pool
gcloud container node-pools upgrade l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

### A100 Fine-tuning Pool (Priority 2)
**Strategy: Coordinate with job schedule**

**Option A - Job Gap Upgrade (Recommended):**
```bash
# During scheduled fine-tuning gap:
# 1. Pause new job submissions
# 2. Wait for current jobs to complete (4-8h max)
# 3. Use surge upgrade with maxUnavailable
gcloud container node-pools update a100-training-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 5

gcloud container node-pools upgrade a100-training-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

**Option B - Maintenance Exclusion During Jobs:**
```bash
# Block upgrades during active fine-tuning campaigns
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "finetune-campaign" \
  --add-maintenance-exclusion-start-time 2024-XX-XXTXX:XX:XXZ \
  --add-maintenance-exclusion-end-time 2024-XX-XXTXX:XX:XXZ \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Remove exclusion during job gaps and upgrade manually
```

## Detailed Upgrade Sequence

### Phase 1: Control Plane (5-15 min)
```bash
# Control plane upgrade
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION

# Verify CP health
kubectl get pods -n kube-system
```

### Phase 2: L4 Inference Pool (30-60 min)
```bash
# Monitor blue-green progress
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=l4-inference-pool -o wide'

# Validate inference during transition
curl -X POST INFERENCE_ENDPOINT/health
```

### Phase 3: A100 Fine-tuning Pool (1-4 hours)
```bash
# Confirm no running jobs
kubectl get pods -n ml-training | grep -v Completed

# Upgrade during job gap
gcloud container node-pools upgrade a100-training-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

## GPU-Specific Considerations

**Inference Latency Protection:**
- Autoscaled blue-green keeps old nodes serving while new nodes warm up
- No cold start penalty during transition
- Load balancers naturally shift traffic to ready nodes

**Fine-tuning Job Protection:**
- Configure PDBs: `minAvailable: 1` per fine-tuning StatefulSet
- Extended termination grace period: `terminationGracePeriodSeconds: 3600` (1 hour)
- Checkpointing recommended before any maintenance window

**GPU Driver Changes:**
- 1.31→1.32 may change CUDA version
- Validate model compatibility in staging
- Test both inference and training workloads

## Rollback Plan

**If inference latency degrades post-upgrade:**
```bash
# Blue-green allows quick rollback during soak period
gcloud container node-pools rollback l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE

# Or manual cordon/migration if needed
kubectl cordon -l cloud.google.com/gke-nodepool=l4-inference-pool
```

## Pre-Upgrade Checklist

- [ ] GPU driver compatibility validated in staging (1.31→1.32)
- [ ] Sufficient reservation capacity for blue-green replacement nodes
- [ ] Inference monitoring baseline captured (p95 latency, throughput)
- [ ] Fine-tuning job schedule reviewed - coordinate upgrade during gap
- [ ] PDBs configured: inference pods + training StatefulSets
- [ ] Model checkpointing enabled for fine-tuning jobs
- [ ] Load balancer health checks configured for graceful traffic shift

## Post-Upgrade Validation

```bash
# GPU driver version
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.nodeInfo.kubeletVersion}{"\n"}{end}'

# Inference health
curl -X POST INFERENCE_ENDPOINT/predict -d '{"test": "data"}'

# GPU utilization
kubectl top nodes --selector=node.kubernetes.io/instance-type=g2-standard-24

# No stuck pods
kubectl get pods -A | grep -E "Pending|Terminating"
```

**Expected Timeline:**
- Control plane: 15 minutes
- L4 inference pool: 45 minutes (autoscaled blue-green)
- A100 training pool: 2-4 hours (depending on job schedule)
- Total: 3-5 hours

The autoscaled blue-green strategy minimizes inference impact by avoiding pod restarts during the transition. Coordinate A100 upgrades with your fine-tuning schedule for zero job interruption.
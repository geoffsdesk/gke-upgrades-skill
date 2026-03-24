# GKE AI/ML Platform Upgrade Plan: 1.31 → 1.32

**Cluster Overview:**
- Total: 5,000 nodes
- H100 GPU (training): 2,000 nodes
- A100 GPU (inference): 1,500 nodes  
- T4 GPU (dev): 500 nodes
- CPU (services): 1,000 nodes

**Upgrade Strategy:** Phased approach prioritizing production workloads and training continuity.

## Phase 1: Control Plane + Low-Risk Nodes (Week 1-2)

### Control Plane Upgrade
- **Timing:** Weekend maintenance window (Saturday 2-6 AM UTC)
- **Strategy:** Sequential minor upgrade with two-step process for rollback safety
- **Soak period:** 48 hours between control plane upgrade and first node pool

```bash
# Control plane upgrade with rollback-safe two-step process
gcloud beta container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.latest \
  --control-plane-soak-duration 48h

# Verify control plane health
kubectl get pods -n kube-system
kubectl get nodes --show-labels
```

### Phase 1 Node Pools (Low Risk First)
**Order:** CPU services → T4 dev → Non-critical workloads

1. **CPU service nodes (1,000 nodes)**
   - **Risk:** Low - stateless services, can tolerate restarts
   - **Strategy:** Surge upgrade with moderate parallelism
   - **Settings:** `maxSurge=5%` (50 nodes), `maxUnavailable=0`
   - **Duration:** ~2-3 days with 20-node parallelism

2. **T4 development nodes (500 nodes)**  
   - **Risk:** Low - dev workloads, can be interrupted
   - **Strategy:** Surge upgrade with higher parallelism
   - **Settings:** `maxSurge=10%` (50 nodes), `maxUnavailable=2`
   - **Duration:** ~1-2 days

```bash
# CPU services upgrade
gcloud container node-pools update cpu-services \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 50 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade cpu-services \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest

# T4 dev upgrade  
gcloud container node-pools update t4-dev \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 50 \
  --max-unavailable-upgrade 2

gcloud container node-pools upgrade t4-dev \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

## Phase 2: A100 Inference Nodes (Week 3)

### Pre-upgrade Preparation
- **Capacity check:** Verify GPU reservation headroom for A100 surge capacity
- **Load balancer readiness:** Ensure traffic can shift between upgraded/non-upgraded nodes
- **Monitoring:** Set up inference latency and throughput dashboards

### A100 Inference Strategy (1,500 nodes)
- **Risk:** Medium - production inference, but designed for fault tolerance
- **Strategy:** Autoscaled blue-green OR conservative surge (depends on reservation capacity)
- **Timing:** Tuesday-Thursday (avoid Monday/Friday for production changes)

**Option A - If surge capacity available:**
```bash
gcloud container node-pools update a100-inference \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 15 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade a100-inference \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**Option B - If no surge capacity (most likely for GPU reservations):**
```bash
# Enable autoscaling for blue-green
gcloud container node-pools update a100-inference \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 1000 \
  --total-max-nodes 2000

# Autoscaled blue-green upgrade
gcloud container node-pools update a100-inference \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=7200s
```

**Duration:** 5-7 days for conservative batch processing

### Inference Validation Checklist
```bash
# Monitor inference latency during upgrade
kubectl top nodes -l nodepool=a100-inference
kubectl get pods -l app=inference -o wide --sort-by='.status.startTime'

# Check GPU utilization
kubectl describe nodes -l nodepool=a100-inference | grep nvidia.com/gpu
```

## Phase 3: H100 Training Nodes (Week 4-5)

### Critical Pre-upgrade Steps

1. **Training campaign coordination:**
   - Survey active training jobs and estimated completion times
   - Coordinate with ML teams on job checkpointing
   - Plan upgrade during natural training gaps

2. **Maintenance exclusion setup:**
```bash
# Block auto-upgrades during training campaigns
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "h100-training-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

### H100 Training Strategy (2,000 nodes)
- **Risk:** Highest - multi-day/week training jobs, cannot tolerate mid-job eviction
- **Strategy:** Manual coordination + autoscaled blue-green
- **Prerequisites:** All active training jobs must complete or checkpoint

**Step 1 - Coordinate training pause:**
```bash
# Scale down long-running training workloads
kubectl scale deployment training-job-scheduler --replicas=0 -n ml-platform

# Wait for active jobs to complete or checkpoint
kubectl get pods -l workload-type=training -n ml-jobs --field-selector=status.phase=Running
```

**Step 2 - Upgrade in batches (400 nodes per batch):**
```bash
# Create batch labels for phased upgrade
kubectl label nodes -l nodepool=h100-training upgrade-batch=batch-1 --selector='metadata.name~"worker-[0-3][0-9][0-9]"'

# Autoscaled blue-green per batch
gcloud container node-pools update h100-training-batch-1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 320 \
  --total-max-nodes 800 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.2,blue-green-full-batch-timeout=14400s
```

**Step 3 - Validation between batches:**
- Verify RDMA/GPUDirect connectivity on new nodes
- Test single-node training job on upgraded nodes  
- Confirm compact placement group integrity
- 48-hour soak period between batches

**Duration:** 10-14 days (2-3 days per batch + soak time)

### H100-Specific Validations
```bash
# Verify GPUDirect-TCPX functionality
kubectl run gpu-test --image=nvcr.io/nvidia/pytorch:23.07-py3 \
  --limits nvidia.com/gpu=1 \
  --node-selector nodepool=h100-training \
  -- python -c "import torch; print(torch.cuda.device_count()); print(torch.cuda.get_device_name(0))"

# Check RDMA interface status
kubectl debug node/NODE_NAME -it --image=busybox -- cat /sys/class/infiniband/*/ports/*/state

# Verify compact placement (nodes should be in same placement group)
gcloud compute instances describe INSTANCE_NAME --zone=ZONE --format="value(scheduling.nodeAffinities)"
```

## Multi-Cluster Fleet Coordination

If running multiple clusters, sequence upgrades:

```bash
# Dev cluster first (Rapid channel)
gcloud container clusters update dev-cluster \
  --zone ZONE \
  --release-channel rapid

# Staging cluster second (Regular channel)  
gcloud container clusters update staging-cluster \
  --zone ZONE \
  --release-channel regular

# Production cluster last (Stable channel + exclusions)
gcloud container clusters update prod-cluster \
  --zone ZONE \
  --release-channel stable \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

## Rollback Strategy

### Phase 1-2 Rollback (CPU/T4/A100)
- Node pools can be rolled back by creating new pools at 1.31
- Control plane: Rollback possible during 48h soak period only

### Phase 3 Rollback (H100 Training) 
- **Critical:** Cannot rollback in-progress multi-day training jobs
- Ensure training checkpoints are compatible with both 1.31 and 1.32
- Blue-green strategy allows quick revert to blue pool if issues detected

```bash
# Emergency rollback - uncordon blue pool, scale down green
kubectl uncordon -l nodepool=h100-training-blue
kubectl drain -l nodepool=h100-training-green --ignore-daemonsets --delete-emptydir-data
```

## Monitoring & Alerting

### Critical Metrics to Track
```bash
# GPU utilization during upgrade
kubectl top nodes -l accelerator=nvidia-h100-80gb

# Training job completion rates
kubectl get pods -l workload-type=training --field-selector=status.phase=Succeeded,status.phase=Failed

# Inference request latency (via service mesh or ingress)
kubectl get ing -A -o json | jq '.items[].status.loadBalancer'
```

### Alerting Rules
- H100 node availability < 95% → Page on-call
- A100 inference latency > 200ms P95 → Alert ML platform team  
- Training job failure rate > 10% → Pause upgrade process
- GPU reservation utilization > 90% → Scale coordination needed

## Timeline Summary

| Week | Phase | Nodes | Risk | Strategy |
|------|-------|-------|------|----------|
| 1 | Control plane + CPU | 1,000 | Low | Surge |  
| 2 | T4 dev nodes | 500 | Low | Surge |
| 3 | A100 inference | 1,500 | Medium | Blue-green |
| 4-5 | H100 training | 2,000 | High | Coordinated blue-green |

**Total Duration:** 5 weeks  
**Training Downtime:** <24 hours (controlled, during natural gaps)
**Inference Impact:** Rolling, <5% capacity reduction

This phased approach minimizes risk to production training workloads while maintaining inference availability throughout the upgrade process.
# GKE Upgrade Plan: ML Inference Platform (1.31 → 1.32)

**Cluster:** ML Platform | **Mode:** Standard | **Channel:** _(please specify)_
**Current:** 1.31.x | **Target:** 1.32.x
**Node pools:** L4 inference (200 nodes) + A100 inference/training (100 nodes)

## Executive Summary

**Primary challenge:** GPU VMs don't support live migration — every upgrade causes pod restarts and inference latency spikes. **Recommended strategy:** Autoscaled blue-green for both pools to minimize inference disruption, with careful sequencing around training jobs.

## Upgrade Strategy

### GPU-Specific Considerations
- **No live migration:** All pods restart during GPU node upgrades
- **Driver coupling:** GKE auto-installs GPU drivers matching target version — test in staging first
- **Surge capacity:** Assume fixed GPU reservations with no surge headroom available

### Recommended Approach: Autoscaled Blue-Green

**Why autoscaled blue-green for inference:**
- Keeps old pool serving while new pool warms up
- Avoids inference latency spikes from drain-and-restart
- Cost-efficient: scales down blue pool as green pool scales up
- Better than surge for inference availability

## Pre-Upgrade Actions

### 1. Staging Validation (CRITICAL for GPU)
```bash
# Create staging node pool with target version
gcloud container node-pools create l4-staging \
  --cluster STAGING_CLUSTER \
  --zone ZONE \
  --machine-type g2-standard-24 \
  --accelerator type=nvidia-l4,count=2 \
  --num-nodes 2 \
  --node-version TARGET_VERSION

# Deploy representative inference workloads
kubectl apply -f inference-test-workload.yaml
# Validate model loading, CUDA compatibility, throughput
```

### 2. Training Job Coordination
```bash
# Check active fine-tuning jobs on A100 pool
kubectl get pods -l workload-type=training -o wide

# Wait for completion or apply maintenance exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+2 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

## Upgrade Sequence

### Phase 1: Control Plane (5-10 minutes downtime for API)
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION

# Verify
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

### Phase 2: L4 Inference Pool (Lower Risk First)
```bash
# Configure autoscaled blue-green
gcloud container node-pools update l4-inference \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 50 \
  --total-max-nodes 400 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

# Execute upgrade
gcloud container node-pools upgrade l4-inference \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

**L4 upgrade flow:**
1. Green pool creates 25% capacity (50 nodes) with v1.32
2. L4 pods gradually migrate to green nodes as traffic flows
3. Blue pool scales down as green pool handles load
4. Autoscaler adjusts based on actual demand

### Phase 3: A100 Mixed Pool (After Training Jobs Complete)
```bash
# Remove training protection first
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "training-protection"

# Configure autoscaled blue-green for A100
gcloud container node-pools update a100-mixed \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 25 \
  --total-max-nodes 200 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.30,blue-green-full-batch-timeout=1800s

# Execute upgrade
gcloud container node-pools upgrade a100-mixed \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

## Monitoring During Upgrade

### Inference Health Checks
```bash
# Monitor inference endpoint latency
curl -w "@curl-format.txt" -s -o /dev/null https://your-inference-endpoint/health

# Watch pod distribution across old/new nodes
kubectl get pods -l app=inference -o wide --sort-by='.spec.nodeName'

# Monitor autoscaler behavior
kubectl describe hpa inference-hpa
```

### Blue-Green Progress
```bash
# Track upgrade phases
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=l4-inference -o wide'

# Monitor pod migrations
kubectl get events --field-selector involvedObject.kind=Pod,reason=Scheduled
```

## Inference-Specific Validations

### Post-Upgrade Health Checks
```bash
# Model loading test
kubectl run inference-test \
  --image=your-inference-image \
  --rm -it --restart=Never \
  --limits=nvidia.com/gpu=1 \
  -- python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}'); print(f'GPU count: {torch.cuda.device_count()}')"

# Throughput baseline
# Run load test against inference endpoints
# Compare p95 latency pre/post upgrade
```

### GPU Driver Verification
```bash
# Check driver versions on new nodes
kubectl get nodes -l cloud.google.com/gke-nodepool=l4-inference \
  -o custom-columns=NAME:.metadata.name,DRIVER:.status.nodeInfo.kubeletVersion

# Validate CUDA compatibility
kubectl exec -it POD_ON_NEW_NODE -- nvidia-smi
```

## Rollback Plan

If inference latency degrades significantly:

### During Blue-Green Soak Period
```bash
# Roll back to blue pool
gcloud container node-pools rollback a100-mixed \
  --cluster CLUSTER_NAME \
  --zone ZONE

# Uncordon blue nodes
kubectl uncordon -l cloud.google.com/gke-nodepool=a100-mixed
```

### After Blue-Green Completion
Manual pool recreation required:
```bash
# Create new pool at 1.31
gcloud container node-pools create a100-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --machine-type a2-highgpu-1g \
  --accelerator type=nvidia-tesla-a100,count=1 \
  --node-version PREVIOUS_VERSION \
  --num-nodes 100

# Migrate workloads manually
```

## Training Job Protection

### Before A100 Upgrade
- **Checkpoint active training jobs**
- **Pause new training submissions**  
- **Wait for 4-8h jobs to complete naturally** (don't force-evict)
- Coordinate with ML engineers on training schedule

### Training-Friendly Timing
- Schedule A100 upgrades during training downtime (weekends/nights)
- Consider separate dedicated training pool if upgrade windows don't align

## Timeline Estimate

- **Control plane:** 10 minutes
- **L4 pool (200 nodes):** 2-3 hours with autoscaled blue-green
- **A100 pool (100 nodes):** 1.5-2 hours with autoscaled blue-green
- **Total:** ~4-5 hours end-to-end

**Critical path:** Training job completion before A100 upgrade — this may extend timeline by hours/days depending on active jobs.

## Risk Mitigation

1. **Staging validation prevents CUDA/driver issues**
2. **Autoscaled blue-green minimizes inference downtime**
3. **L4-first sequencing validates strategy on lower-risk pool**
4. **Training job protection prevents 4-8h job loss**
5. **Maintenance exclusions provide emergency brakes**

Would you like me to adapt this plan based on your current release channel or add specific monitoring queries for your inference stack?
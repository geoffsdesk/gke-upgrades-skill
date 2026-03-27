# GKE ML Platform Upgrade Plan: 1.31 → 1.32

## Executive Summary

**Cluster:** ML Platform (Standard)  
**Current:** 1.31 → **Target:** 1.32  
**Workloads:** L4 inference (200 nodes) + A100 inference/fine-tuning (100 nodes)  
**Strategy:** Autoscaled blue-green for inference pools, job-aware scheduling for fine-tuning

## GPU Pool Upgrade Strategy

### L4 Inference Pool (200 nodes) - Autoscaled Blue-Green
**Recommended:** Autoscaled blue-green upgrade to minimize inference latency spikes
- GPU VMs don't support live migration — every upgrade causes pod restarts
- Traditional surge upgrade = inference downtime during drain/restart
- Autoscaled blue-green keeps old pool serving while new pool warms up

```bash
gcloud container node-pools update l4-inference-pool \
    --cluster ML_CLUSTER_NAME \
    --zone ZONE \
    --enable-autoscaling \
    --total-min-nodes 50 --total-max-nodes 250 \
    --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

### A100 Mixed Pool (100 nodes) - Custom Strategy
**Challenge:** Mix of inference (latency-sensitive) + fine-tuning jobs (4-8 hours)  
**Approach:** Two-phase upgrade with job coordination

**Phase 1 - Inference traffic only:**
```bash
# Temporarily disable fine-tuning job submissions
# Drain existing fine-tuning jobs (wait for completion or checkpoint)

# Use autoscaled blue-green for remaining inference workloads
gcloud container node-pools update a100-mixed-pool \
    --cluster ML_CLUSTER_NAME \
    --zone ZONE \
    --enable-autoscaling \
    --total-min-nodes 20 --total-max-nodes 120 \
    --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.20,blue-green-full-batch-timeout=1800s
```

## Pre-Upgrade Checklist

### Compatibility & Version Checks
- [ ] **Target version available in Regular channel:** `gcloud container get-server-config --zone ZONE --format="yaml(channels)"`
- [ ] **GPU driver compatibility:** Test 1.32 + driver combo in staging cluster first
  ```bash
  # Create staging node pool at target version
  gcloud container node-pools create staging-l4-test \
      --cluster STAGING_CLUSTER \
      --node-version 1.32.x-gke.xxx \
      --accelerator type=nvidia-l4,count=1 \
      --num-nodes 1
  
  # Deploy representative inference workload and validate
  kubectl apply -f inference-test-deployment.yaml
  ```
- [ ] **No deprecated API usage:** Check GKE deprecation insights dashboard
- [ ] **ML framework compatibility:** Verify TensorFlow/PyTorch versions support new CUDA drivers
- [ ] **Model loading validation:** Test model artifacts load correctly with new driver stack

### Infrastructure Readiness
- [ ] **GPU reservation headroom confirmed** for autoscaled blue-green (requires capacity for new nodes)
- [ ] **Monitoring baseline captured:** Inference latency (p50/p95/p99), throughput, error rates
- [ ] **Cluster autoscaler:** Pause during upgrade or accept mixed-version state
  ```bash
  # Option A: Pause autoscaling during upgrade
  gcloud container clusters update ML_CLUSTER_NAME \
      --enable-autoprovisioning=false
  
  # Option B: Set min=max temporarily on node pools
  gcloud container node-pools update l4-inference-pool \
      --total-min-nodes 200 --total-max-nodes 200
  ```

### Workload Protection
- [ ] **Fine-tuning job checkpoint:** Ensure jobs can resume from checkpoints
- [ ] **Inference PDBs configured:**
  ```bash
  # Example PDB for inference deployments
  apiVersion: policy/v1
  kind: PodDisruptionBudget
  metadata:
    name: inference-pdb
  spec:
    minAvailable: 80%
    selector:
      matchLabels:
        app: ml-inference
  ```
- [ ] **Model serving health checks:** Validate readiness/liveness probes trigger correctly
- [ ] **Load balancer warmup:** Configure connection draining timeouts

## Upgrade Runbook

### Phase 1: Control Plane (15-20 minutes)
```bash
# Upgrade control plane first
gcloud container clusters upgrade ML_CLUSTER_NAME \
    --zone ZONE \
    --master \
    --cluster-version 1.32.x-gke.xxx

# Verify CP health
kubectl get pods -n kube-system
kubectl get nodes  # Should show Ready, mixed versions OK
```

### Phase 2: A100 Pool - Job Coordination (2-4 hours)
```bash
# Step 1: Pause new fine-tuning job submissions
# (Application-specific - update job scheduler/queue)

# Step 2: Wait for running jobs to complete or checkpoint
kubectl get pods -l workload=fine-tuning -o wide
# Monitor job completion, estimated 4-8 hours

# Step 3: Upgrade A100 pool (inference workloads only remaining)
gcloud container node-pools upgrade a100-mixed-pool \
    --cluster ML_CLUSTER_NAME \
    --zone ZONE \
    --cluster-version 1.32.x-gke.xxx

# Step 4: Re-enable fine-tuning submissions after upgrade completes
```

### Phase 3: L4 Pool - Autoscaled Blue-Green (1-2 hours)
```bash
# Initiate autoscaled blue-green upgrade
gcloud container node-pools upgrade l4-inference-pool \
    --cluster ML_CLUSTER_NAME \
    --zone ZONE \
    --cluster-version 1.32.x-gke.xxx

# Monitor progress - blue pool scales down as green scales up
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=l4-inference-pool -o wide'

# Validate inference traffic shifting to new nodes
kubectl get pods -l app=ml-inference -o wide
```

## Critical Monitoring During Upgrade

### Real-time Metrics
```bash
# Inference latency tracking
kubectl top pods -l app=ml-inference --containers
curl -s INFERENCE_ENDPOINT/health

# Node version distribution
kubectl get nodes -o custom-columns="NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,POOL:.metadata.labels['cloud\.google\.com/gke-nodepool']"

# GPU utilization
kubectl exec -it INFERENCE_POD -- nvidia-smi
```

### Alerts to Configure
- **Inference latency > p95 baseline + 20%**
- **Inference error rate > 1%**  
- **GPU node NotReady**
- **Fine-tuning job failures during transition**
- **Model loading failures (new CUDA driver)**

## Rollback Plan

### If Control Plane Issues
- **Limited rollback options:** Contact GKE support for CP minor downgrade
- **Immediate mitigation:** Scale up old node pools if workloads break

### If Node Pool Issues
```bash
# Cancel in-progress upgrade
gcloud container operations list --cluster ML_CLUSTER_NAME --zone ZONE
# Let current batch complete, then stops

# Create emergency node pool at old version
gcloud container node-pools create l4-rollback-pool \
    --cluster ML_CLUSTER_NAME \
    --zone ZONE \
    --node-version 1.31.x-gke.xxx \
    --accelerator type=nvidia-l4,count=1 \
    --enable-autoscaling \
    --num-nodes 50 --max-nodes 200

# Migrate inference traffic
kubectl cordon -l cloud.google.com/gke-nodepool=l4-inference-pool
# Traffic shifts to rollback pool via autoscaler
```

## Post-Upgrade Validation

### System Health
- [ ] **All nodes at 1.32:** `kubectl get nodes -o wide`
- [ ] **GPU drivers loaded:** `kubectl describe nodes | grep nvidia.com/gpu`
- [ ] **System pods healthy:** `kubectl get pods -n kube-system`

### Workload Validation  
- [ ] **Inference latency within baseline:** Monitor p95 < pre-upgrade + 10%
- [ ] **Model loading successful:** Deploy test model, verify loading time
- [ ] **Fine-tuning jobs resume:** Submit test 30-minute job, verify completion
- [ ] **Autoscaling functional:** Scale test deployment, verify node provisioning
- [ ] **GPU sharing working:** Multiple inference pods per GPU node

### Performance Regression Tests
```bash
# Inference throughput test
kubectl run perf-test --image=INFERENCE_IMAGE --rm -it -- \
    python benchmark.py --model MODEL_NAME --requests 1000

# Memory/GPU utilization
kubectl top nodes --sort-by=memory
kubectl exec INFERENCE_POD -- nvidia-smi --query-gpu=utilization.gpu --format=csv
```

## Risk Mitigation

### L4 Pool Specific Risks
- **Model warmup time:** New nodes need model download/caching — pre-warm during blue-green soak period
- **Connection draining:** Configure ingress timeout > model inference time to avoid request drops

### A100 Pool Specific Risks  
- **Fine-tuning data loss:** Ensure checkpoint frequency < upgrade window
- **Mixed inference/training scheduling:** Use node affinity to prevent training pods landing on inference-optimized nodes post-upgrade

### General GPU Risks
- **Driver version changes:** 1.32 may update CUDA drivers — validate in staging first
- **GPU memory management:** New driver may change memory allocation patterns
- **Multi-GPU topology:** Verify NVLink/GPU interconnect works post-upgrade

**Estimated Total Upgrade Time:** 6-10 hours (including job completion wait)  
**Business Impact:** Minimal for inference (blue-green), planned for fine-tuning jobs
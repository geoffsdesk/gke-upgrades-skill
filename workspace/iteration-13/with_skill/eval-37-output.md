# GKE AI/ML Platform Upgrade Plan: 1.31 → 1.32

## Executive Summary

**Scope:** 5,000-node mixed AI/ML platform upgrade  
**Current:** GKE 1.31 → **Target:** GKE 1.32  
**Priority:** Training continuity first, inference availability second  
**Estimated Duration:** 3-4 weeks total  

## Cluster Assessment

```
Fleet Overview:
- H100 Training: 2,000 nodes (highest priority - zero disruption)
- A100 Inference: 1,500 nodes (high availability required)  
- T4 Development: 500 nodes (flexible timing)
- CPU Services: 1,000 nodes (standard availability)
- Total: 5,000 nodes across 4 specialized pools
```

## Phase Strategy

### Phase 1: Control Plane Upgrades (Week 1)
**Objective:** Upgrade all control planes to 1.32 while maintaining node compatibility

```bash
# Control plane upgrades (low-risk, ~15 minutes each)
# Sequence: Dev → Services → Inference → Training

# 1. T4 Development cluster
gcloud container clusters upgrade dev-t4-cluster \
  --zone us-central1-a \
  --master \
  --cluster-version 1.32.0-gke.1234

# 2. CPU Services cluster  
gcloud container clusters upgrade services-cpu-cluster \
  --zone us-central1-a \
  --master \
  --cluster-version 1.32.0-gke.1234

# 3. A100 Inference cluster
gcloud container clusters upgrade inference-a100-cluster \
  --zone us-central1-a \
  --master \
  --cluster-version 1.32.0-gke.1234

# 4. H100 Training cluster
gcloud container clusters upgrade training-h100-cluster \
  --zone us-central1-a \
  --master \
  --cluster-version 1.32.0-gke.1234
```

**Validation after each:**
```bash
kubectl get nodes -o wide
kubectl get pods -n kube-system
# Verify 2-version skew: CP=1.32, nodes=1.31 (supported)
```

### Phase 2: Development & Services (Week 2)
**Objective:** Upgrade non-critical pools to validate GPU driver compatibility

#### T4 Development Pool (500 nodes)
```bash
# Configure conservative surge for T4 pool
gcloud container node-pools update dev-t4-pool \
  --cluster dev-t4-cluster \
  --zone us-central1-a \
  --max-surge-upgrade 5 \
  --max-unavailable-upgrade 0

# Upgrade T4 development pool
gcloud container node-pools upgrade dev-t4-pool \
  --cluster dev-t4-cluster \
  --zone us-central1-a \
  --cluster-version 1.32.0-gke.1234
```

#### CPU Services Pool (1,000 nodes)
```bash
# Higher parallelism for CPU nodes (no GPU constraints)
gcloud container node-pools update services-cpu-pool \
  --cluster services-cpu-cluster \
  --zone us-central1-a \
  --max-surge-upgrade 50 \
  --max-unavailable-upgrade 0

# Upgrade CPU services
gcloud container node-pools upgrade services-cpu-pool \
  --cluster services-cpu-cluster \
  --zone us-central1-a \
  --cluster-version 1.32.0-gke.1234
```

**Critical Validation:**
```bash
# Verify GPU driver compatibility on T4 nodes
kubectl get nodes -l cloud.google.com/gke-accelerator=nvidia-tesla-t4 -o wide
kubectl describe node T4_NODE_NAME | grep -A 10 "nvidia.com/gpu"

# Test CUDA version compatibility
kubectl run cuda-test --rm -i --tty \
  --image=tensorflow/tensorflow:latest-gpu \
  --overrides='{"spec":{"nodeSelector":{"cloud.google.com/gke-accelerator":"nvidia-tesla-t4"}}}' \
  -- nvidia-smi
```

### Phase 3: A100 Inference Pool (Week 3)
**Objective:** Upgrade inference nodes with zero capacity loss using autoscaled blue-green

**Pre-upgrade Setup:**
```bash
# Enable autoscaling for blue-green upgrade
gcloud container node-pools update inference-a100-pool \
  --cluster inference-a100-cluster \
  --zone us-central1-a \
  --enable-autoscaling \
  --total-min-nodes 1200 \
  --total-max-nodes 1800

# Configure autoscaled blue-green strategy
gcloud container node-pools update inference-a100-pool \
  --cluster inference-a100-cluster \
  --zone us-central1-a \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.20,blue-green-full-batch-timeout=7200s
```

**Execute Upgrade:**
```bash
gcloud container node-pools upgrade inference-a100-pool \
  --cluster inference-a100-cluster \
  --zone us-central1-a \
  --cluster-version 1.32.0-gke.1234
```

**Monitoring During Upgrade:**
```bash
# Monitor serving capacity
watch 'kubectl get nodes -l cloud.google.com/gke-accelerator=nvidia-tesla-a100 | grep Ready | wc -l'

# Monitor inference workloads
kubectl get pods -n inference -o wide --field-selector=status.phase=Running
```

### Phase 4: H100 Training Pool - Maintenance Window (Week 4)
**Objective:** Zero-disruption upgrade during scheduled training gap

**Pre-upgrade Protection:**
```bash
# Apply maintenance exclusion to block auto-upgrades during training
gcloud container clusters update training-h100-cluster \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "training-campaign-protection" \
  --add-maintenance-exclusion-start-time 2024-02-15T00:00:00Z \
  --add-maintenance-exclusion-end-time 2024-03-15T23:59:59Z \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Set up dedicated training node pool with manual upgrade control
gcloud container node-pools update training-h100-pool \
  --cluster training-h100-cluster \
  --zone us-central1-a \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 20
```

**Coordinated Upgrade Window:**
```bash
# Step 1: Coordinate training checkpoint (external to GKE)
# Wait for training jobs to reach checkpoint/completion

# Step 2: Cordon all training nodes
kubectl cordon -l cloud.google.com/gke-accelerator=nvidia-tesla-h100

# Step 3: Scale training workloads to zero
kubectl scale deployment training-job-1 --replicas=0 -n training
kubectl scale deployment training-job-2 --replicas=0 -n training

# Step 4: Execute upgrade with high parallelism
gcloud container node-pools upgrade training-h100-pool \
  --cluster training-h100-cluster \
  --zone us-central1-a \
  --cluster-version 1.32.0-gke.1234

# Step 5: Verify and restart training (after ~6-8 hours)
kubectl get nodes -l cloud.google.com/gke-accelerator=nvidia-tesla-h100
kubectl scale deployment training-job-1 --replicas=8 -n training
```

## GPU-Specific Considerations

### Driver Compatibility Matrix
| GKE Version | CUDA Version | H100 Support | A100 Support | T4 Support |
|-------------|--------------|--------------|--------------|------------|
| 1.31        | 12.1         | ✓            | ✓            | ✓          |
| 1.32        | 12.4         | ✓            | ✓            | ✓          |

**Action:** Verify training frameworks support CUDA 12.4 before H100 upgrade.

### Placement Group Preservation
```bash
# Verify compact placement survives upgrade
gcloud compute resource-policies describe h100-placement-policy \
  --region us-central1

# Check post-upgrade placement
kubectl get nodes -l cloud.google.com/gke-accelerator=nvidia-tesla-h100 \
  -o custom-columns=NAME:.metadata.name,ZONE:.metadata.labels.'topology\.kubernetes\.io/zone'
```

## Timeline & Resources

| Phase | Duration | Nodes | Strategy | Risk | Validation |
|-------|----------|-------|----------|------|------------|
| **Phase 1: Control Planes** | 3 days | 0 | Sequential CP upgrades | Low | Node compatibility |
| **Phase 2: Dev/Services** | 4 days | 1,500 | Surge upgrades | Medium | GPU driver testing |
| **Phase 3: A100 Inference** | 7 days | 1,500 | Autoscaled blue-green | Medium | Serving capacity |
| **Phase 4: H100 Training** | 8 hours | 2,000 | Coordinated maintenance | High | Training resumption |

**Total Duration:** 21-28 days  
**Peak Additional Capacity:** 300 A100 nodes (20% of inference fleet)

## Rollback Strategy

### Immediate Rollback Options
```bash
# Control plane: Contact GKE support for minor version downgrade
# Node pools: Create replacement pool at 1.31

gcloud container node-pools create h100-rollback-pool \
  --cluster training-h100-cluster \
  --zone us-central1-a \
  --cluster-version 1.31.5-gke.5678 \
  --num-nodes 2000 \
  --machine-type a3-highgpu-8g \
  --accelerator type=nvidia-tesla-h100,count=8
```

### Training-Specific Rollback
- Checkpointed training jobs can resume on 1.31 nodes
- GPU reservations protect capacity during rollback
- Estimated rollback time: 4-6 hours for full H100 pool recreation

## Risk Mitigation

### High-Priority Risks
1. **Training Job Loss:** Pre-upgrade checkpointing mandatory
2. **GPU Driver Incompatibility:** Phase 2 validation catches issues early  
3. **Inference SLA Breach:** Blue-green maintains serving capacity
4. **Quota Exhaustion:** Verify A100 surge capacity before Phase 3

### Monitoring & Alerts
```bash
# Training job health
kubectl get pods -n training --field-selector=status.phase!=Running

# Inference serving capacity  
kubectl get nodes -l cloud.google.com/gke-accelerator=nvidia-tesla-a100 | grep Ready | wc -l

# GPU utilization
kubectl top nodes --selector=cloud.google.com/gke-accelerator
```

## Success Metrics

- **Training Continuity:** Zero multi-day job restarts
- **Inference SLA:** ≥95% serving capacity maintained throughout
- **Upgrade Velocity:** Complete fleet upgrade within 4 weeks
- **Rollback Readiness:** <4-hour recovery time if needed

This plan prioritizes training workload protection while maintaining inference availability through the upgrade process. The phased approach allows early validation of GPU driver compatibility and provides multiple rollback points.
# GKE Mixed AI/ML Platform Upgrade Plan: v1.31 → v1.32

## Executive Summary

This plan upgrades a 5,000-node mixed AI/ML platform while prioritizing training continuity and inference availability. The approach uses **phased rollouts with training protection** and **inference-optimized upgrade strategies**.

**Key Assumptions:**
- **Cluster mode:** Standard GKE (required for node pool control)
- **Release channel:** Regular or Stable (auto-upgrades enabled)
- **Training workloads:** Multi-day runs requiring zero interruption
- **GPU reservations:** Fixed capacity (no surge available)

---

## Phase 1: Development & Services (Low Risk)

**Target:** 500 T4 dev nodes + 1,000 CPU service nodes  
**Timeline:** Week 1  
**Strategy:** Fast parallel upgrade to validate the target version

### T4 Development Pools
```bash
# Configure for faster upgrade (dev workloads are interruption-tolerant)
gcloud container node-pools update t4-dev-pool \
  --cluster AI_CLUSTER \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4

# Upgrade (T4 pools likely have limited surge capacity)
gcloud container node-pools upgrade t4-dev-pool \
  --cluster AI_CLUSTER \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

### CPU Service Pools
```bash
# Higher parallelism for stateless services
gcloud container node-pools update cpu-services-pool \
  --cluster AI_CLUSTER \
  --zone ZONE \
  --max-surge-upgrade 5% \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade cpu-services-pool \
  --cluster AI_CLUSTER \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**Validation Criteria:**
- [ ] GPU driver compatibility confirmed on T4 nodes
- [ ] CUDA version changes tested with development workloads
- [ ] Service mesh (if any) functioning on 1.32
- [ ] No API deprecation warnings in dev workloads

---

## Phase 2: A100 Inference (High Availability Required)

**Target:** 1,500 A100 inference nodes  
**Timeline:** Week 2  
**Strategy:** Autoscaled blue-green to minimize inference latency spikes

### Pre-upgrade: Inference Continuity Setup
```bash
# Enable autoscaling if not already configured
gcloud container node-pools update a100-inference-pool \
  --cluster AI_CLUSTER \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 1500 \
  --total-max-nodes 3000

# Configure autoscaled blue-green strategy
gcloud container node-pools update a100-inference-pool \
  --cluster AI_CLUSTER \
  --zone ZONE \
  --enable-blue-green-upgrade \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

**Why autoscaled blue-green for inference:**
- Avoids inference latency spikes from pod restarts (surge upgrade kills all pods)
- Scales up green pool while keeping blue pool serving
- Cost-efficient compared to standard blue-green (scales down blue as green scales up)
- Supports extended graceful termination for model unloading

### Execute Upgrade
```bash
gcloud container node-pools upgrade a100-inference-pool \
  --cluster AI_CLUSTER \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**Monitoring During Upgrade:**
```bash
# Monitor pool scaling and traffic distribution
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=a100-inference-pool -o wide'

# Check inference endpoint latency
curl -w "@curl-format.txt" -s -o /dev/null INFERENCE_ENDPOINT
```

---

## Phase 3: Control Plane Upgrade

**Timeline:** Between Week 2-3 (after inference validation, before H100 training)  
**Strategy:** Two-step upgrade with rollback window for production safety

```bash
# Step 1: Binary upgrade with soak period (rollback-safe)
gcloud beta container clusters upgrade AI_CLUSTER \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.latest \
  --control-plane-soak-duration 2d

# During 2-day soak: validate API compatibility, webhook behavior, admission controllers
```

**Validation During Soak Period:**
- [ ] All admission webhooks functioning (cert-manager, policy controllers)
- [ ] HPA/VPA behavior unchanged
- [ ] API latency within baseline
- [ ] No deprecated API warnings from training/inference workloads
- [ ] kube-system pods healthy

```bash
# Step 2: Complete upgrade (enables 1.32 features, no rollback after this)
gcloud beta container clusters upgrade AI_CLUSTER \
  --zone ZONE \
  --master \
  --complete-upgrade
```

---

## Phase 4: H100 Training (Maximum Protection)

**Target:** 2,000 H100 training nodes  
**Timeline:** Week 3-4  
**Strategy:** Maintenance exclusion + coordinated training gaps

### Pre-upgrade: Training Protection
```bash
# Block auto-upgrades during active training campaigns
gcloud container clusters update AI_CLUSTER \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# This allows CP security patches but blocks disruptive node upgrades
```

### Training Campaign Coordination

**Before Each Training Run:**
1. **Verify cluster state:** All H100 nodes at 1.31, control plane at 1.32
2. **Checkpoint validation:** Ensure training jobs can resume from checkpoints
3. **Set training-run exclusion:** Extend exclusion window to cover the training campaign

**During Scheduled Training Gaps:**
```bash
# Remove exclusion temporarily
gcloud container clusters update AI_CLUSTER \
  --zone ZONE \
  --remove-maintenance-exclusion training-protection

# Configure for training-safe upgrade (fixed reservation, no surge capacity)
gcloud container node-pools update h100-training-pool \
  --cluster AI_CLUSTER \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2

# Parallel host maintenance strategy for faster completion
# Apply maintenance label to ALL H100 nodes simultaneously
kubectl label nodes -l cloud.google.com/gke-nodepool=h100-training-pool \
  cloud.google.com/perform-maintenance=true

# This triggers ~4-hour host maintenance on all nodes in parallel
```

**Alternative: Rolling H100 Upgrade (if parallel not suitable)**
```bash
# Sequential upgrade in small batches
gcloud container node-pools upgrade h100-training-pool \
  --cluster AI_CLUSTER \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest \
  --max-unavailable-upgrade 1
```

**Post-Training Gap:**
```bash
# Re-enable protection for next training campaign
gcloud container clusters update AI_CLUSTER \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

---

## GPU-Specific Considerations

### Driver Compatibility Testing
Before each phase, validate GPU driver changes:
```bash
# Check driver version on target GKE version
kubectl run gpu-test --image=nvidia/cuda:12.0-base-ubuntu22.04 \
  --restart=Never --rm -it -- nvidia-smi

# Test CUDA compatibility with training/inference images
kubectl run model-test --image=YOUR_TRAINING_IMAGE \
  --restart=Never --rm -it -- python -c "import torch; print(torch.cuda.is_available())"
```

### Reservation and Quota Management
```bash
# Verify GPU reservation headroom before upgrade
gcloud compute reservations describe H100_RESERVATION --zone ZONE
gcloud compute reservations describe A100_RESERVATION --zone ZONE

# For inference pools: confirm autoscaler can scale to 2x during blue-green
```

### GPUDirect-TCPX Compatibility
```bash
# Verify high-performance interconnect survives upgrade
# Test RDMA connectivity post-upgrade on training nodes
kubectl run rdma-test --image=nvcr.io/nvidia/pytorch:23.12-py3 \
  --restart=Never --rm -it -- \
  python -c "
import subprocess
result = subprocess.run(['ibstat'], capture_output=True, text=True)
print('RDMA devices:', result.stdout)
"
```

---

## Maintenance Windows & Scheduling

### Recommended Maintenance Windows
```bash
# Configure for off-peak GPU utilization
gcloud container clusters update AI_CLUSTER \
  --zone ZONE \
  --maintenance-window-start "2024-02-10T02:00:00Z" \
  --maintenance-window-duration 6h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### Disruption Intervals for Large Scale
```bash
# Prevent back-to-back disruptions on this large cluster
gcloud container clusters update AI_CLUSTER \
  --zone ZONE \
  --maintenance-minor-version-disruption-interval=2592000s \
  --maintenance-patch-version-disruption-interval=604800s
```

---

## Monitoring & Alerting

### Upgrade Progress Monitoring
```bash
# Track node versions across pools
watch 'kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,POOL:.metadata.labels.cloud\.google\.com/gke-nodepool | sort -k3'

# GPU utilization during upgrades
kubectl top nodes -l accelerator=nvidia-tesla-h100
```

### Training Job Protection
```bash
# Monitor for unexpected evictions
kubectl get events -A --field-selector reason=Evicted | \
  grep -E "training|jupyter|notebook"

# Check PDB violations in large GPU pools
gcloud logging read \
  'resource.type="gke_cluster" 
   jsonPayload.reason="POD_PDB_VIOLATION"' \
  --limit=50
```

---

## Rollback Strategy

### Inference Rollback (Blue-Green)
If issues detected during A100 inference upgrade:
```bash
# Blue-green allows fast rollback during soak period
gcloud container node-pools cancel-upgrade a100-inference-pool \
  --cluster AI_CLUSTER \
  --zone ZONE

# Traffic automatically returns to blue (original) pool
```

### Training Rollback (Limited Options)
H100 training pools have limited rollback options due to no surge capacity:
- **Prevention:** Thorough testing in T4 dev environment first
- **Recovery:** Create new pool at 1.31, migrate training jobs during next gap
- **Data protection:** Ensure persistent volumes survive pool recreation

---

## Success Criteria

### Phase Completion Checklist
```
Phase 1 (Dev/Services):
- [ ] All T4 and CPU nodes at 1.32
- [ ] CUDA driver compatibility confirmed
- [ ] Service mesh functionality validated
- [ ] Development workflows operational

Phase 2 (A100 Inference):
- [ ] All A100 inference nodes at 1.32
- [ ] Inference latency within 10% of baseline
- [ ] Model loading times unchanged
- [ ] Autoscaling behavior normal

Phase 3 (Control Plane):
- [ ] Control plane at 1.32
- [ ] API latency within baseline
- [ ] kube-system pods healthy
- [ ] Admission webhooks functioning

Phase 4 (H100 Training):
- [ ] All H100 nodes at 1.32
- [ ] Training jobs resumable from checkpoints
- [ ] RDMA/GPUDirect connectivity verified
- [ ] Host maintenance completed
```

### Fleet-Wide Validation
```bash
# Final version verification across all 5,000 nodes
kubectl get nodes -o custom-columns=VERSION:.status.nodeInfo.kubeletVersion | sort | uniq -c

# Workload health check
kubectl get pods -A | grep -E "Error|CrashLoopBackOff|Pending" | wc -l
# Should return 0

# GPU utilization resumed
kubectl top nodes -l accelerator | grep -E "h100|a100|t4"
```

---

## Timeline Summary

| Week | Phase | Nodes | Risk | Strategy |
|------|-------|-------|------|----------|
| 1 | Dev/Services | 1,500 | Low | Fast parallel upgrade |
| 2 | A100 Inference | 1,500 | Medium | Autoscaled blue-green |
| 2-3 | Control Plane | N/A | Medium | Two-step with soak |
| 3-4 | H100 Training | 2,000 | High | Maintenance exclusion + training gaps |

**Total Duration:** 3-4 weeks  
**Training Downtime:** Minimized to scheduled gaps only  
**Inference Disruption:** Near-zero with blue-green strategy

This phased approach ensures your AI/ML platform maintains training continuity while upgrading safely to GKE 1.32.
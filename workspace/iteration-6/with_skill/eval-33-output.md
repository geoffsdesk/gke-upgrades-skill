# GKE ML Platform Upgrade Plan: 1.29 → 1.30

## Executive Summary

**Target:** Upgrade Standard cluster from GKE 1.29 → 1.30  
**Workloads:** Inference (auto-scaling) + fine-tuning (4-8hr jobs)  
**GPU Resources:** 200 L4 nodes + 100 A100 nodes (separate pools)  
**Priority:** Minimize inference latency/availability impact

**Key strategy:** Surge upgrades with conservative settings, A100 pool upgrade during fine-tuning job gaps, inference pools upgraded during low-traffic windows.

---

## Version Compatibility Assessment

✅ **GKE 1.29 → 1.30 compatibility:** This is a safe single minor version jump  
✅ **GPU driver compatibility:** GKE 1.30 includes compatible NVIDIA drivers for L4/A100  
⚠️ **Action required:** Test target GKE version in staging first — driver changes can affect CUDA version

### Pre-upgrade validation checklist
```bash
# Confirm 1.30 available in your release channel
gcloud container get-server-config --zone YOUR_ZONE --format="yaml(channels)"

# Check for deprecated API usage (common 1.29→1.30 issue)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Verify no bare inference pods (common with ML workloads)
kubectl get pods -A -o json | jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

---

## Upgrade Strategy: Phased GPU Pool Approach

### Phase 1: Control plane (10-15 minutes)
- Minimal impact to running workloads
- Enables node pool upgrades

### Phase 2: L4 inference pool (lower priority)
- Upgrade during low-traffic period
- Higher `maxSurge` acceptable (inference can handle brief capacity fluctuation)

### Phase 3: A100 pool (high priority protection)
- **Critical:** Coordinate with fine-tuning job schedule
- Conservative settings to protect running jobs
- Option to cordon nodes and wait for job completion

---

## Node Pool Upgrade Settings

### L4 Inference Pool (200 nodes)
```bash
# Strategy: Aggressive surge - inference can handle temporary capacity changes
maxSurge: 10         # ~5% extra capacity for smooth transition
maxUnavailable: 0    # Never reduce available inference capacity
```

**Rationale:** Inference workloads auto-scale and can tolerate brief capacity fluctuations. Higher surge ensures pods reschedule quickly.

### A100 Fine-tuning Pool (100 nodes)  
```bash
# Strategy: Ultra-conservative - protect multi-hour training jobs
maxSurge: 1          # Minimal extra A100 capacity (expensive, potentially scarce)
maxUnavailable: 0    # Never evict running fine-tuning jobs
```

**Rationale:** A100 VMs are expensive and scarce. Fine-tuning jobs can't restart mid-training without losing hours of work.

---

## Maintenance Window & Job Protection

### Recommended timing
- **L4 upgrade:** During lowest inference traffic (typically early morning)
- **A100 upgrade:** During scheduled fine-tuning job gap

### Fine-tuning job protection strategy
**Option A: Maintenance exclusion (recommended)**
```bash
# Block all node upgrades during active fine-tuning campaign
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "fine-tuning-protection" \
  --add-maintenance-exclusion-start-time 2024-XX-XXTXX:XX:XXZ \
  --add-maintenance-exclusion-end-time 2024-XX-XXTXX:XX:XXZ \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

**Option B: Cordon and wait**
```bash
# Cordon A100 nodes with running jobs, wait for natural completion
kubectl cordon -l cloud.google.com/gke-nodepool=a100-pool
# Upgrade only after jobs complete (4-8 hours)
```

---

## Upgrade Runbook

### Phase 1: Control Plane Upgrade
```bash
# 1. Pre-flight checks
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

kubectl get nodes | grep -E "L4|A100" | wc -l  # Confirm node count

# 2. Upgrade control plane
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.30.X-gke.XXXX

# 3. Wait and verify (~10-15 minutes)
watch 'gcloud container clusters describe CLUSTER_NAME --zone ZONE --format="value(currentMasterVersion)"'
kubectl get pods -n kube-system  # System pods healthy
```

### Phase 2: L4 Inference Pool
```bash
# 1. Configure surge settings  
gcloud container node-pools update l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 10 \
  --max-unavailable-upgrade 0

# 2. Capture baseline metrics
kubectl top nodes -l cloud.google.com/gke-nodepool=l4-inference-pool

# 3. Start upgrade
gcloud container node-pools upgrade l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30.X-gke.XXXX

# 4. Monitor progress (~20-30 minutes for 200 nodes with maxSurge=10)
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=l4-inference-pool -o wide'

# 5. Validate inference pods rescheduled
kubectl get pods -A -o wide | grep -E "gpu.*inference"
```

### Phase 3: A100 Fine-tuning Pool  
```bash
# 1. Verify no active fine-tuning jobs (or wait for completion)
kubectl get pods -A | grep -E "fine-tune|training" | grep Running

# 2. Configure conservative surge
gcloud container node-pools update a100-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# 3. Start upgrade
gcloud container node-pools upgrade a100-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30.X-gke.XXXX

# 4. Monitor (~90-120 minutes for 100 nodes with maxSurge=1)
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=a100-pool'
```

---

## GPU-Specific Validation

### Post-upgrade GPU health check
```bash
# Verify GPU driver loaded on new nodes
kubectl describe nodes -l accelerator=nvidia-l4 | grep nvidia.com/gpu
kubectl describe nodes -l accelerator=nvidia-tesla-a100 | grep nvidia.com/gpu

# Test GPU access from pods
kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: gpu-test
spec:
  restartPolicy: Never
  nodeSelector:
    accelerator: nvidia-l4
  containers:
  - name: gpu-test
    image: nvidia/cuda:12.0-runtime-ubuntu20.04
    command: ["nvidia-smi"]
    resources:
      limits:
        nvidia.com/gpu: 1
EOF

kubectl logs gpu-test
kubectl delete pod gpu-test
```

### Inference workload validation
```bash
# Check inference pods running on upgraded nodes
kubectl get pods -A -o wide | grep inference | head -10

# Verify auto-scaling responding to load
kubectl describe hpa INFERENCE_HPA_NAME -n NAMESPACE
```

---

## Troubleshooting: GPU-Specific Issues

### Common GPU upgrade problems

**Issue: Surge A100 nodes fail to provision**
```bash
# Check quota and capacity
gcloud compute project-info describe --format="table(quotas.metric,quotas.usage,quotas.limit)" | grep A100

# If quota/capacity insufficient, switch to drain-first strategy:
gcloud container node-pools update a100-pool \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

**Issue: GPU driver version changed, CUDA compatibility broken**
```bash
# Check driver version on new nodes
kubectl get nodes -l accelerator=nvidia-tesla-a100 -o yaml | grep nvidia-driver-version

# Verify CUDA compatibility with your inference framework
# Test in staging cluster first with target GKE version
```

**Issue: Fine-tuning job evicted during upgrade**
```bash
# Check for PDBs protecting training workloads
kubectl get pdb -A | grep training

# Create protective PDB if missing:
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: fine-tuning-pdb
  namespace: ml-training
spec:
  minAvailable: "100%"  # Protect all training pods
  selector:
    matchLabels:
      workload-type: fine-tuning
```

---

## Success Criteria

### L4 Inference Pool
- [ ] All 200 nodes at GKE 1.30
- [ ] Inference pods redistributed without errors
- [ ] Auto-scaling responding normally
- [ ] P95 inference latency within 5% of baseline
- [ ] No dropped requests during upgrade window

### A100 Fine-tuning Pool  
- [ ] All 100 nodes at GKE 1.30
- [ ] Zero fine-tuning jobs interrupted
- [ ] GPU utilization restored to normal levels
- [ ] CUDA/driver compatibility confirmed

### Overall Platform
- [ ] Cluster autoscaler functioning (scales both pools)
- [ ] GPU quotas not exceeded during surge
- [ ] Monitoring/logging pipeline uninterrupted
- [ ] No performance regression in production inference

---

## Timeline Estimate

- **Control plane:** 15 minutes
- **L4 pool (200 nodes, maxSurge=10):** 30-40 minutes  
- **A100 pool (100 nodes, maxSurge=1):** 90-120 minutes
- **Total:** ~2.5 hours + coordination time for fine-tuning job gaps

**Recommendation:** Plan a 4-hour maintenance window to account for GPU capacity provisioning delays and validation steps.
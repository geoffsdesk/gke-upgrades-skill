# GKE Upgrade Plan: Large-Scale LLM Training Cluster

## Executive Summary
For your 512-node H100 training cluster with active 2-3 week runs, we need a **staged upgrade approach** with maintenance exclusions to protect active training while preserving GPUDirect-TCPXO compatibility.

## Environment Analysis
- **Cluster**: 512 A3 Mega nodes (4,096 H100 GPUs total)
- **Current**: GKE 1.31 → **Target**: GKE 1.32
- **Workload**: Multi-week LLM training with GPUDirect-TCPXO
- **Risk**: Version incompatibility breaking GPU interconnect

## Upgrade Strategy: Maintenance Exclusion + Training Gap Approach

### Phase 1: Immediate Protection (Execute Now)
```bash
# Block all upgrades during active training campaigns
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-campaign-protection" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time "2025-02-15T08:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

**Why "no minor or node upgrades":**
- Allows control plane security patches (critical for multi-week exposure)
- Blocks disruptive node pool upgrades that would restart training
- Tracks to version End of Support automatically

### Phase 2: GPUDirect-TCPXO Compatibility Verification

**Critical**: GKE 1.32 may change GPU drivers affecting TCPXO. Validate first:

```bash
# Create staging node pool with target version
gcloud container node-pools create staging-1-32 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.LATEST \
  --num-nodes 2 \
  --machine-type a3-megagpu-8g \
  --node-locations ZONE \
  --placement-type COMPACT

# Test GPUDirect-TCPXO on staging nodes
kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: tcpxo-test
spec:
  nodeSelector:
    cloud.google.com/gke-nodepool: staging-1-32
  containers:
  - name: test
    image: gcr.io/PROJECT/training-image
    command: ["/bin/bash", "-c"]
    args:
    - |
      # Your TCPXO validation commands here
      nvidia-smi topo -m
      # Test inter-GPU communication patterns
      # Verify RDMA topology preserved
EOF
```

**Validation checklist:**
- [ ] GPUDirect-TCPXO enabled and functional
- [ ] RDMA topology matches production
- [ ] No driver version regressions
- [ ] Training throughput comparable to 1.31 baseline

### Phase 3: Upgrade Execution (During Training Gap)

**Timing**: Execute only during planned gaps between training runs.

#### 3.1 Control Plane Upgrade
```bash
# Upgrade control plane first (minimal disruption)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.LATEST
```

**Impact**: ~10-15 minutes of API unavailability. **Active training pods continue running.**

#### 3.2 Node Pool Upgrade Strategy

**For GPU training clusters, use parallel host maintenance approach:**

```bash
# Option A: Parallel strategy (all nodes at once - fastest)
# Use when you can tolerate full restart
gcloud container node-pools update gpu-training-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 20

# Checkpoint active training first
kubectl scale statefulset/training-job --replicas=0

# Trigger upgrade
gcloud container node-pools upgrade gpu-training-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.LATEST
```

**Key constraints for your scale:**
- **GKE max parallelism**: ~20 nodes simultaneously (increasing to 100 in roadmap)
- **512 nodes = ~26 batches minimum**
- **Estimated duration**: 8-12 hours for full fleet
- **GPU reservation**: Ensure no surge capacity conflicts

#### 3.3 Compact Placement Verification
```bash
# After upgrade, verify nodes remain in same placement group
gcloud compute instances list \
  --filter="name:gke-CLUSTER-NAME" \
  --format="table(name,zone,scheduling.nodeAffinities)"

# Test RDMA topology post-upgrade
kubectl exec -it training-pod-0 -- nvidia-smi topo -m
```

### Phase 4: Post-Upgrade Validation

```bash
# Cluster health
kubectl get nodes | grep -v Ready
kubectl get pods -n kube-system | grep -v Running

# GPU driver verification
kubectl get nodes -o json | \
  jq -r '.items[] | "\(.metadata.name): \(.status.nodeInfo.kubeletVersion)"'

# Training workload compatibility test
kubectl apply -f minimal-training-test.yaml
# Run 1-hour training test to validate throughput
```

## Multi-Week Training Protection Strategy

### Dedicated Training Node Pools
```bash
# Create training-only pool with tight maintenance control
gcloud container node-pools create training-dedicated \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --num-nodes 512 \
  --machine-type a3-megagpu-8g \
  --node-locations ZONE \
  --placement-type COMPACT \
  --preemptible=false
```

### Campaign-Based Maintenance Exclusions
```bash
# Before each training campaign (2-3 week runs)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-run-$(date +%Y%m%d)" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time "CAMPAIGN_END_DATE" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Remove after campaign completes
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "training-run-$(date +%Y%m%d)"
```

## Risk Mitigation

### GPU Interconnect Preservation
- **Compact placement**: Verify post-upgrade with `gcloud compute instances list`
- **RDMA topology**: Test with `nvidia-smi topo -m` 
- **Driver consistency**: GKE 1.32 may change CUDA versions—validate in staging

### Training Job Protection
- **Checkpointing**: Ensure training has robust checkpoint/resume
- **PDB configuration**: Prevent accidental eviction during maintenance
- **Cordon pattern**: Manually cordon training nodes, wait for natural completion

### Rollback Planning
```bash
# If issues detected post-upgrade, rollback requires new node pool creation
gcloud container node-pools create rollback-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.PREVIOUS \
  --num-nodes 512 \
  --machine-type a3-megagpu-8g
```

## Timeline Recommendation

| Week | Action | Risk Level |
|------|--------|------------|
| **Week 1** | Apply maintenance exclusion, create staging pool | Low |
| **Week 2-3** | GPUDirect-TCPXO compatibility validation | Low |
| **Week 4** | Control plane upgrade during training gap | Medium |
| **Week 5** | Node pool upgrade during training gap | High |
| **Week 6** | Post-upgrade validation, resume training | Medium |

## Key Success Factors

1. **Never upgrade during active training** — use exclusions religiously
2. **Staging validation is mandatory** — GPUDirect compatibility can break silently  
3. **Plan 12+ hour maintenance windows** — 512 nodes take significant time
4. **Verify compact placement post-upgrade** — RDMA topology must be preserved
5. **Test checkpoint/resume workflow** — validate training can recover cleanly

Your cluster represents significant compute investment. The conservative approach with maintenance exclusions and staging validation is essential for protecting multi-week training investments while maintaining security posture.
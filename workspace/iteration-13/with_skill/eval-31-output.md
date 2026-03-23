# LLM Training Cluster Upgrade Plan: 512 H100 Nodes (A3 Mega)

## Overview
Large-scale LLM training cluster requiring careful upgrade orchestration to protect multi-week training runs and preserve GPUDirect-TCPXO connectivity.

**Cluster Profile:**
- **Size:** 512 A3 Mega nodes (4,096 H100 GPUs total)
- **Workload:** Multi-week LLM training runs (2-3 weeks)
- **Network:** GPUDirect-TCPXO inter-node communication
- **Current:** GKE 1.31 → **Target:** GKE 1.32
- **Mode:** Standard (node pool upgrade control needed)

## Training-Aware Upgrade Strategy

### Phase 1: Immediate Protection (Apply Now)
```bash
# Block all node upgrades during active training
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-campaign-q1" \
  --add-maintenance-exclusion-start-time "$(date -Iseconds)" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Verify exclusion active
gcloud container clusters describe CLUSTER_NAME --zone ZONE \
  --format="value(maintenancePolicy.window.maintenanceExclusions)"
```

This prevents auto-upgrades while allowing control plane security patches. The `--until-end-of-support` flag makes the exclusion persistent until 1.31 reaches EoS.

### Phase 2: Control Plane Upgrade (Low Risk)
The control plane can be upgraded without affecting running training jobs. Schedule during a low-activity period:

```bash
# Control plane upgrade (no node impact)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.latest

# Verify control plane upgraded
gcloud container clusters describe CLUSTER_NAME --zone ZONE \
  --format="value(currentMasterVersion)"
```

**Timeline:** ~15-20 minutes, no training disruption expected.

### Phase 3: Node Pool Upgrade During Training Gap

#### Pre-Upgrade Checklist for GPU Interconnect
- [ ] **GPUDirect-TCPXO compatibility:** Verify GKE 1.32 maintains TCPXO support for A3 Mega
- [ ] **CUDA driver version:** Check if 1.32 changes CUDA version (could break training framework)
- [ ] **Compact placement preservation:** Confirm new nodes will maintain placement group topology
- [ ] **Checkpoint location:** Verify training checkpoints saved to persistent storage
- [ ] **Training pause capability:** Confirm ability to cleanly pause training jobs

#### GPU Node Pool Upgrade Strategy

**Recommended: Parallel Host Maintenance + Node Upgrade**
For training workloads, use GKE's AI host maintenance feature combined with coordinated training stops:

```bash
# 1. Scale training workload to zero (checkpoint first!)
kubectl scale deployment llm-training-job --replicas=0

# 2. Apply maintenance label to ALL nodes simultaneously (parallel strategy)
kubectl label nodes -l cloud.google.com/gke-nodepool=gpu-training-pool \
  cloud.google.com/perform-maintenance=true

# 3. Upgrade node pool while host maintenance runs
gcloud container node-pools upgrade gpu-training-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**Timeline:** ~4 hours total (host maintenance + node upgrade run concurrently)

**Alternative: Surge Upgrade (if GPU quota available)**
Only if you have confirmed surge capacity for 512+ H100 nodes:
```bash
# Configure surge (requires 2x GPU reservation capacity)
gcloud container node-pools update gpu-training-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 50 \
  --max-unavailable-upgrade 0
```

**NOT Recommended: maxUnavailable strategy** for this size cluster - would take days to complete with GKE's ~20 node batch limit.

### Phase 4: Post-Upgrade Validation

#### GPU Interconnect Verification
```bash
# Verify all nodes ready with correct version
kubectl get nodes -l cloud.google.com/gke-nodepool=gpu-training-pool \
  -o wide

# Check GPU driver version
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.nodeInfo.kubeletVersion}{"\t"}{.metadata.annotations.container\.googleapis\.com/instance_template}{"\n"}{end}'

# Test GPUDirect-TCPXO connectivity (from training pod)
kubectl exec -it training-test-pod -- nvidia-smi nvlink --status
kubectl exec -it training-test-pod -- nvidia-smi topo -m
```

#### Compact Placement Validation
```bash
# Verify nodes are still in same placement group
gcloud compute instances describe NODE_NAME --zone ZONE \
  --format="value(resourcePolicies)"

# Check for placement violations
kubectl get nodes -o json | jq -r '.items[] | select(.metadata.labels["topology.gke.io/zone"]) | {name:.metadata.name, zone:.metadata.labels["topology.gke.io/zone"]}'
```

## Training Restart Procedure

```bash
# 1. Remove maintenance exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "training-campaign-q1"

# 2. Restore training workload from checkpoint
kubectl scale deployment llm-training-job --replicas=1

# 3. Monitor training startup
kubectl logs -f deployment/llm-training-job
```

## Risk Mitigation

### Capacity Protection
- **GPU reservation:** Ensure your H100 reservation covers surge capacity if using surge strategy
- **Placement groups:** Verify replacement nodes land in same placement policy
- **Network bandwidth:** Test high-bandwidth RDMA connectivity post-upgrade

### Training Protection
- **Checkpoint frequency:** Increase checkpoint frequency before upgrade window
- **State validation:** Test checkpoint restore in staging cluster first
- **Framework compatibility:** Validate PyTorch/JAX compatibility with new CUDA driver

### Rollback Plan
If GPU interconnect breaks post-upgrade:
1. **Immediate:** Scale training to zero, preserve checkpoints
2. **Node replacement:** Create new node pool at GKE 1.31, migrate workloads
3. **Support escalation:** Contact Cloud Customer Care with cluster details

## Timing Recommendation

**Optimal upgrade window:** Plan the node upgrade during a natural training pause between epochs or at a scheduled checkpoint. For 2-3 week training runs, this might be:
- End of week checkpoints
- Model evaluation phases
- Hyperparameter tuning breaks

**Duration estimate:** 
- Control plane: 15 minutes
- Node pool (parallel): 4 hours
- Training restart: 30-60 minutes

**Total outage:** ~4-5 hours for GPU workloads

This approach minimizes training disruption while ensuring your cluster stays current and benefits from GKE's automated lifecycle management.
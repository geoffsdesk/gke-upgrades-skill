# LLM Training Cluster Upgrade Plan
**GKE Standard | 512 H100 nodes (A3 Mega) | GPUDirect-TCPXO | Active 2-3 week training runs**

## Critical constraints for your environment

**GPUDirect-TCPXO version compatibility:** Your current setup (GKE 1.31 + A3 Mega + GPUDirect-TCPXO) requires specific GKE versions. Before proceeding, verify that GKE 1.32 supports GPUDirect-TCPXO on A3 Mega machines. Check the [GKE release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes) for GPUDirect compatibility between 1.31→1.32.

**Multi-week training protection:** GKE's default pod eviction timeout during surge upgrades is 1 hour — far shorter than your 2-3 week training runs. Any node upgrade will force-evict training pods after 1 hour, destroying weeks of progress.

## Recommended strategy: Training-aware upgrade with host maintenance

Given your scale and training duration, use this approach:

### Phase 1: Control plane upgrade (low risk)
```bash
# 1. Apply maintenance exclusion to prevent auto-upgrades during training
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+3 weeks' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# 2. Upgrade control plane only (training continues uninterrupted)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.LATEST

# 3. Verify control plane health
kubectl get pods -n kube-system
kubectl get nodes  # All should remain at 1.31
```

**Impact:** Training continues uninterrupted. Control plane upgrades don't affect running workloads.

### Phase 2: Node pool upgrade during training gap

**Wait for natural training completion** — either job finishes successfully or reaches a checkpoint where you can pause.

```bash
# 1. Verify training checkpoint saved
# 2. Scale training workload to zero
kubectl scale deployment training-workload --replicas=0

# 3. Configure GPU pool for parallel host maintenance
# Given your fixed H100 reservation, no surge capacity exists
gcloud container node-pools update gpu-training-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 20

# 4. Remove maintenance exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion training-protection

# 5. Trigger node pool upgrade
gcloud container node-pools upgrade gpu-training-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.LATEST
```

### Phase 3: Post-upgrade validation

Critical tests before resuming training:

```bash
# 1. Verify all nodes upgraded
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE
kubectl get nodes -o wide

# 2. Test GPUDirect-TCPXO functionality
# Deploy a small multi-node training test job
# Verify RDMA topology and inter-node bandwidth

# 3. Validate compact placement preserved
# Check that nodes remain in the same placement group
gcloud compute instances list --filter="zone:ZONE" --format="table(name,zone,resourcePolicies)"

# 4. Test model loading and CUDA compatibility
# New GKE version installs updated GPU drivers
# Verify your training framework works with new CUDA version
```

## Alternative: Dedicated training pool isolation

For future upgrades, consider this architecture:

```bash
# Create dedicated training node pool with strict upgrade control
gcloud container node-pools create training-dedicated \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --machine-type a3-megagpu-8g \
  --accelerator type=nvidia-h100-mega-80gb,count=8 \
  --num-nodes 512 \
  --placement-type COMPACT \
  --cluster-version 1.31.x-gke.CURRENT

# Apply persistent "no minor or node upgrades" exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-pool-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Create separate inference/staging pool for regular upgrades
gcloud container node-pools create inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --machine-type a3-highgpu-8g \
  --num-nodes 32
```

This isolates training from inference workloads and gives you upgrade control per pool.

## Upgrade timeline and considerations

**Expected duration:** With `maxUnavailable=20` and GKE's ~20-node parallelism ceiling, your 512-node pool will take **~26 batches × 15-20 minutes per batch = 6-9 hours** total upgrade time.

**Capacity planning:** During upgrade with `maxSurge=0, maxUnavailable=20`, you'll temporarily lose 20 nodes (160 GPUs) of training capacity. Plan accordingly.

**Host maintenance interaction:** A3 Mega nodes may require host maintenance (firmware/driver updates) that coincides with the GKE upgrade. This extends the upgrade window to ~4 hours per batch of nodes undergoing host maintenance.

## Risk mitigation checklist

```
Pre-Upgrade Checklist (LLM Training)
- [ ] Active training run completed and checkpointed
- [ ] GKE 1.32 GPUDirect-TCPXO compatibility confirmed for A3 Mega
- [ ] Staging cluster created with target version + representative training workload tested
- [ ] GPU driver version change impact validated (CUDA compatibility)
- [ ] Compact placement policy verified to survive upgrade
- [ ] H100 reservation headroom confirmed (or maxUnavailable approach planned)
- [ ] Training framework checkpoint/resume functionality tested
- [ ] Rollback plan documented (requires new pool creation + workload migration)
- [ ] Extended maintenance window scheduled (6-9 hours minimum)
```

## Troubleshooting GPU-specific upgrade issues

**If GPUDirect stops working post-upgrade:**
```bash
# Check RDMA device status
kubectl debug node/NODE_NAME -it --image=ubuntu -- bash
# Inside debug container:
ls /dev/infiniband/
# Should show rdma devices

# Verify network topology
kubectl get nodes -o yaml | grep -A5 -B5 "topology.gke.io"
```

**If compact placement breaks:**
- Nodes may land in different placement groups, breaking RDMA topology
- Check: `gcloud compute instances list --format="table(name,resourcePolicies)"`
- Fix: Create new node pool with explicit placement policy, migrate workloads

This approach protects your active training investment while ensuring you eventually reach GKE 1.32 during a natural training gap. The control plane upgrade (Phase 1) can happen immediately with zero training impact.
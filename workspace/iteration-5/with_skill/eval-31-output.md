# GKE Upgrade Plan for Large-Scale LLM Training Cluster

## Environment Summary
- **Cluster:** GKE Standard, 512 nodes (A3 Mega), 4,096 H100 GPUs total
- **Training duration:** 2-3 weeks (cannot tolerate mid-job eviction)
- **Networking:** GPUDirect-TCPXO (requires specific GKE versions)
- **Current version:** 1.29 → **Target:** 1.30
- **Key constraint:** Protect active training runs from disruption

## Critical Considerations for Your Environment

### GPUDirect-TCPXO Version Requirements
- **GPUDirect-TCPXO requires GKE 1.27.7-gke.1121000+** for A3 Mega machines
- Your current 1.29 → 1.30 upgrade **should maintain compatibility**
- **Risk:** Upgrade may reset network configuration or break compact placement policies
- **Mitigation:** Test GPU interconnect thoroughly in staging before production

### GPU Node Pool Upgrade Constraints
- **H100 VMs do not support live migration** — every upgrade requires pod restart
- **512 H100 nodes means surge capacity of 512 additional H100s** — likely impossible to provision
- **Training jobs running for weeks cannot survive node pool upgrade disruption**

## Recommended Upgrade Strategy

### Phase 1: Immediate Protection (Apply Now)
```bash
# Block node pool upgrades during active training - allows control plane patches only
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+21 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

This exclusion type allows control plane security patches while blocking disruptive node pool upgrades.

### Phase 2: Control Plane Upgrade (Safe to do now)
```bash
# Upgrade control plane only - does not affect running training jobs
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.30.X-gke.LATEST

# Verify control plane upgrade
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"

# Confirm training pods unaffected
kubectl get pods -n TRAINING_NAMESPACE
```

**Impact:** Zero disruption to training workloads. Control plane upgrades are non-disruptive.

### Phase 3: Node Pool Architecture for Future Training Cycles

Create a dedicated node pool strategy to enable seamless upgrades:

```bash
# Create new H100 pool for next training cycle (during current run)
gcloud container node-pools create h100-pool-v2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --machine-type a3-megagpu-8g \
  --num-nodes 512 \
  --cluster-version 1.30.X-gke.LATEST \
  --enable-autoscaling \
  --max-nodes 512 \
  --min-nodes 0 \
  --node-labels=pool-version=v2,workload=training \
  --node-taints=training=true:NoSchedule \
  --enable-ip-alias \
  --enable-gvnic \
  --placement-type COMPACT \
  --placement-policy-name PLACEMENT_GROUP_NAME \
  --disk-size 200 \
  --disk-type pd-ssd \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

**Note:** You'll need sufficient H100 quota for both pools temporarily. Contact Google Cloud support for quota increase if needed.

### Phase 4: Training Cycle Transition

When your current 2-3 week training run completes:

1. **Checkpoint and pause training** (standard between training cycles)

2. **Migrate training workloads to new pool:**
```bash
# Update training job nodeSelector/affinity
spec:
  nodeSelector:
    pool-version: "v2"
  tolerations:
  - key: "training"
    operator: "Equal"
    value: "true"
    effect: "NoSchedule"
```

3. **Scale down old pool after migration:**
```bash
gcloud container node-pools resize h100-pool-v1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --num-nodes 0
```

4. **Delete old pool once confident:**
```bash
gcloud container node-pools delete h100-pool-v1 \
  --cluster CLUSTER_NAME \
  --zone ZONE
```

## Alternative: In-Place Upgrade During Planned Gap

If creating duplicate pools exceeds quota limits:

### Wait for Natural Training Gap
- Most LLM training has planned breaks between runs for evaluation, checkpointing, or model architecture changes
- Schedule node pool upgrade during these natural gaps

### Cordon and Drain Pattern
```bash
# During training gap, cordon all nodes
kubectl cordon -l cloud.google.com/gke-nodepool=h100-pool

# Wait for training pods to complete naturally (don't force-drain)
# Then upgrade empty pool
gcloud container node-pools upgrade h100-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30.X-gke.LATEST
```

## GPU Interconnect Validation

After any node pool upgrade, verify GPUDirect-TCPXO:

```bash
# Check GPU topology
kubectl exec -it TRAINING_POD -- nvidia-smi topo -m

# Verify NCCL can see all GPUs across nodes
kubectl exec -it TRAINING_POD -- python -c "
import torch
torch.distributed.init_process_group(backend='nccl', world_size=4096, rank=0)
print('NCCL initialized successfully across all GPUs')
"

# Test inter-node bandwidth
kubectl exec -it TRAINING_POD -- nccl-tests/build/all_reduce_perf -b 1G -e 8G -f 2
```

## Risk Mitigation Checklist

```
Pre-Upgrade Protection
- [ ] Maintenance exclusion applied (blocks node upgrades, allows CP patches)
- [ ] Training checkpointing verified and functional
- [ ] GPUDirect-TCPXO version compatibility confirmed for 1.30
- [ ] Compact placement policy documented for recreation
- [ ] H100 quota sufficient for temporary dual pools (if using pool strategy)

Control Plane Upgrade
- [ ] CP upgraded to 1.30 during active training (safe)
- [ ] Training jobs confirmed unaffected post-CP upgrade
- [ ] GPU driver version noted (auto-installed with 1.30)

Node Pool Strategy
- [ ] New pool created with 1.30 and compact placement
- [ ] GPU interconnect tested in new pool before migration
- [ ] Training workload migration plan ready
- [ ] Old pool cleanup scheduled post-migration
```

## Emergency Procedures

If upgrade goes wrong during training:
1. **Maintenance exclusion buys time** — extends protection even past version EoS
2. **Training checkpoints enable recovery** — restart from last checkpoint rather than from scratch
3. **GPUDirect issues:** Check node placement, MTU settings, and NCCL configuration

The safest approach for your environment is the dual pool strategy during a natural training gap. This eliminates all risk to active training while ensuring you stay current on security patches via control plane upgrades.
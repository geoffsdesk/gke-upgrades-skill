# LLM Training Cluster Upgrade Plan
## Cluster: 512 H100 GPU nodes (A3 Mega) | 1.31 → 1.32 | GPUDirect-TCPXO

This is a high-stakes upgrade requiring careful orchestration around your multi-week training runs and specialized GPU interconnect.

## Executive Summary

**Primary Strategy:** Use maintenance exclusions to freeze the cluster during active training, then upgrade during planned training gaps. GPUDirect-TCPXO compatibility requires validation and compact placement verification.

**Timeline:** Plan 2-3 day upgrade window between training runs. Control plane upgrade (~1 hour), node pool upgrade (8-12 hours for 512 nodes), plus validation time.

## Pre-Upgrade Validation (Critical)

### GPUDirect-TCPXO Compatibility Check
```bash
# Verify target GKE 1.32 supports GPUDirect-TCPXO for A3 Mega
gcloud container get-server-config --zone ZONE \
  --format="yaml(validNodeVersions)" | grep 1.32

# Check current TCPXO status
kubectl get nodes -o custom-columns=NAME:.metadata.name,TCPXO:.metadata.labels.cloud\.google\.com/gke-accelerator-topology
```

**⚠️ Critical:** GPUDirect-TCPXO has strict GKE version requirements for A3 Mega machines. Before proceeding:

1. **Create a 2-node staging cluster** with A3 Mega at GKE 1.32
2. **Deploy a multi-node NCCL test** to verify TCPXO functionality
3. **Confirm RDMA topology** survives the upgrade and nodes maintain placement group co-location

### Compact Placement Verification
```bash
# Document current placement groups
gcloud compute instances describe INSTANCE_NAME --zone ZONE \
  --format="value(scheduling.locationHint.targetShape)"

# Verify all training nodes are in the same placement group
kubectl get nodes -o json | jq -r '.items[] | .metadata.name' | \
  xargs -I {} gcloud compute instances describe {} --zone ZONE \
    --format="value(name,scheduling.locationHint)"
```

## Training-Aware Upgrade Strategy

### Phase 1: Preparation (Before Training Completion)

**Apply maintenance exclusion to freeze all upgrades:**
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-freeze-$(date +%Y%m%d)" \
  --add-maintenance-exclusion-scope no_upgrades \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ)
```

**Set up monitoring for training completion:**
```bash
# Monitor training job status
kubectl get pods -n TRAINING_NAMESPACE -l app=llm-training --watch

# Set up completion notification (adjust to your training framework)
kubectl logs -f -n TRAINING_NAMESPACE TRAINING_POD_NAME | \
  grep -E "(Training completed|Final loss|Checkpoint saved)"
```

### Phase 2: Upgrade Window (Training Gap)

**Configure GPU-specific upgrade settings:**
```bash
# GPU pools with fixed reservations - maxUnavailable is the primary lever
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4
```

**⚠️ Key:** A3 Mega nodes typically use fixed reservations with NO surge capacity. `maxUnavailable=4` allows 4 nodes to drain simultaneously. With GKE's ~20-node batch parallelism limit and 512 nodes, expect 26-30 batches taking 8-12 hours total.

**Remove maintenance exclusion:**
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "training-freeze-$(date +%Y%m%d)"
```

### Phase 3: Sequential Upgrade Execution

**Step 1: Control Plane Upgrade (~1 hour)**
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.latest

# Monitor control plane upgrade
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE
```

**Step 2: Node Pool Upgrade (8-12 hours)**
```bash
gcloud container node-pools upgrade gpu-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest

# Monitor progress - this will take hours for 512 nodes
watch 'kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,STATUS:.status.conditions[-1].type | grep -E "(NAME|1.31|1.32|NotReady)"'
```

### Phase 4: Post-Upgrade Validation

**Critical GPU interconnect verification:**
```bash
# Verify all nodes upgraded
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion

# Check TCPXO topology preserved
kubectl get nodes -o json | jq -r '.items[] | {name:.metadata.name, tcpxo:.metadata.labels["cloud.google.com/gke-accelerator-topology"]}'

# Verify placement group integrity
for node in $(kubectl get nodes -o name | cut -d/ -f2); do
  gcloud compute instances describe $node --zone ZONE \
    --format="value(name,scheduling.locationHint.targetShape)"
done
```

**NCCL connectivity test (mandatory):**
```bash
# Deploy multi-node NCCL test across upgraded nodes
kubectl apply -f nccl-test-deployment.yaml

# Verify all-to-all communication works
kubectl logs -f nccl-test-pod | grep -E "(NCCL version|Out of bound|Bus bandwidth)"
```

**System component health:**
```bash
kubectl get pods -n kube-system | grep -E "(nvidia|gke-metadata)"
kubectl get daemonsets -n kube-system | grep nvidia-gpu-device-plugin
```

## Risk Mitigation

### If Upgrade Fails Mid-Process

**Mixed-version state is functional** - some nodes at 1.31, others at 1.32. Your cluster remains operational for the next training run.

**Recovery options:**
```bash
# Check upgrade status
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE

# If nodes fail to register after upgrade:
kubectl get nodes | grep NotReady
kubectl describe node FAILED_NODE_NAME

# Force failed nodes to be recreated
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-unavailable-upgrade 8
```

### If GPUDirect-TCPXO Breaks

**Immediate rollback** (requires manual intervention):
```bash
# Create new node pool at 1.31
gcloud container node-pools create gpu-pool-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.previous \
  --machine-type a3-megagpu-8g \
  --num-nodes 512 \
  --accelerator type=nvidia-h100-mega-80gb,count=8

# This will take 30-45 minutes for 512 A3 Mega nodes
# Then migrate training workloads to the rollback pool
```

## Training Campaign Coordination

### Recommended Maintenance Schedule

1. **Week 1-3:** Training runs with upgrade freeze exclusion active
2. **Training completion:** Natural checkpoint/save occurs
3. **Upgrade window:** 48-72 hour gap for upgrade + validation  
4. **Week 4-6:** Next training campaign on upgraded cluster

### Training Job Protection Pattern

For future upgrades, implement this pattern:
```bash
# Before starting any multi-week training
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# This prevents GKE from auto-upgrading during training campaigns
# Only security patches reach the control plane
# Remove exclusion during planned upgrade windows
```

## Expected Timeline

- **Preparation:** 1 day (staging validation, monitoring setup)
- **Control plane upgrade:** 1 hour
- **Node pool upgrade:** 8-12 hours (512 nodes, maxUnavailable=4)
- **Validation and testing:** 4-6 hours (NCCL tests, placement verification)
- **Training restart:** 2-4 hours (model loading, checkpoint recovery)

**Total upgrade window:** 48-72 hours between training campaigns.

## Checklist

```markdown
Pre-Upgrade (Training Active)
- [ ] Maintenance exclusion applied - no upgrades during training
- [ ] GKE 1.32 compatibility confirmed for GPUDirect-TCPXO on A3 Mega
- [ ] Staging cluster tested with target version
- [ ] Current compact placement groups documented
- [ ] Training completion monitoring established

Upgrade Window (Training Complete)
- [ ] Training job confirmed completed and checkpointed
- [ ] Maintenance exclusion removed
- [ ] GPU node pool configured: maxSurge=0, maxUnavailable=4
- [ ] Control plane upgraded and validated
- [ ] Node pool upgrade initiated (expect 8-12 hours)
- [ ] All 512 nodes confirmed at target version

Post-Upgrade Validation
- [ ] GPUDirect-TCPXO topology preserved
- [ ] NCCL all-to-all test passes
- [ ] Compact placement integrity verified
- [ ] System components (nvidia drivers) healthy
- [ ] Training environment restored and ready
```

This plan prioritizes protecting your multi-week training investments while ensuring the specialized GPU interconnect survives the upgrade. The key is timing the upgrade during natural training gaps and thoroughly validating the GPU networking stack before resuming production training workloads.
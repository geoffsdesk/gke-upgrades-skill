# GKE Upgrade Plan: Large-Scale LLM Training Cluster (A3 Mega + GPUDirect-TCPXO)

## Critical Context Analysis

**Your environment:**
- **512 H100 nodes** (4,096 GPUs total) — massive scale requiring careful orchestration
- **A3 Mega + GPUDirect-TCPXO** — high-performance interconnect with strict GKE version requirements
- **2-3 week training runs** — far exceeds GKE's 1-hour eviction timeout during surge upgrades
- **GKE Standard 1.31 → 1.32** — minor version upgrade requiring both control plane and node upgrades

**Key constraints:**
1. **No surge capacity exists** for H100 reservations — GPUs are fully allocated
2. **GPUDirect-TCPXO requires specific GKE versions** — verify 1.32 compatibility before upgrading
3. **Training jobs cannot survive forced eviction** — GKE's 1-hour timeout will kill 2-3 week runs
4. **Interconnect topology sensitivity** — node replacement may break RDMA placement groups

## Recommended Strategy: Scheduled Upgrade with Training Campaign Coordination

### Phase 1: Pre-upgrade Validation (1-2 weeks before)

```bash
# 1. Verify GPUDirect-TCPXO compatibility with GKE 1.32
# Check GKE release notes and contact your Technical Account Manager
# Requirement: Ensure 1.32 supports A3 Mega + TCPXO without breaking changes

# 2. Test upgrade in staging cluster
# Create identical A3 Mega staging cluster at current version
# Upgrade staging cluster to 1.32, verify GPU interconnect works
# Run abbreviated training test to confirm RDMA topology survival

# 3. Check current cluster health
gcloud container clusters describe TRAINING_CLUSTER \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].version)"

kubectl get nodes -o wide -l cloud.google.com/gke-nodepool=gpu-training-pool
kubectl top nodes
```

### Phase 2: Training Campaign Coordination

**Critical timing requirement:** Plan upgrade during a **natural gap** between training runs, not mid-campaign.

```bash
# 1. Set maintenance exclusion to block auto-upgrades during active training
gcloud container clusters update TRAINING_CLUSTER \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-campaign-dec-2024" \
  --add-maintenance-exclusion-start-time "2024-12-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-21T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# 2. Monitor training completion
kubectl get pods -n training-namespace -l job=llm-training
# Wait for current run to complete naturally and checkpoint successfully
```

### Phase 3: Control Plane Upgrade (during training gap)

**Timing:** Schedule during off-peak, between training campaigns.

```bash
# 1. Use two-step minor upgrade for rollback safety (recommended for production)
gcloud beta container clusters upgrade TRAINING_CLUSTER \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.xxxx \
  --control-plane-soak-duration 24h

# This gives you 24h to test the new binary while keeping 1.31 API compatibility
# You can roll back to 1.31 during this period if issues arise

# 2. Validate control plane health
kubectl get pods -n kube-system
kubectl get nodes  # Should still show 1.31 node versions

# 3. Test GPU interconnect on existing nodes
# Run short GPU communication test to verify TCPXO still works

# 4. Complete the minor upgrade (enables 1.32 APIs - no rollback after this)
gcloud beta container clusters upgrade TRAINING_CLUSTER \
  --zone ZONE \
  --master \
  --complete-control-plane-upgrade

# 5. Verify final control plane version
gcloud container clusters describe TRAINING_CLUSTER \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

### Phase 4: GPU Node Pool Upgrade Strategy

**Critical choice:** Given no surge capacity, use **drain-first approach** with careful sequencing.

```bash
# 1. Configure drain-first upgrade (no surge GPUs needed)
gcloud container node-pools update gpu-training-pool \
  --cluster TRAINING_CLUSTER \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4

# maxUnavailable=4 provides reasonable parallelism while respecting placement constraints
# With ~20-node GKE batch limit, this ensures controlled drain batches

# 2. Execute node pool upgrade
gcloud container node-pools upgrade gpu-training-pool \
  --cluster TRAINING_CLUSTER \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxxx

# 3. Monitor progress carefully
watch 'kubectl get nodes -o wide -l cloud.google.com/gke-nodepool=gpu-training-pool | grep -E "VERSION|Ready"'

# 4. Verify GPU interconnect after each batch
# Check that replacement nodes land in correct placement groups
# Test RDMA connectivity between upgraded and existing nodes
```

### Phase 5: Post-Upgrade Validation

```bash
# 1. All nodes at target version
kubectl get nodes -o wide
gcloud container node-pools list --cluster TRAINING_CLUSTER --zone ZONE

# 2. GPU interconnect health
nvidia-smi topo -m  # Run on representative nodes
# Verify TCPXO connectivity matrices

# 3. Placement group integrity
# Confirm nodes remain in compact placement groups for RDMA
# May require coordination with Google Cloud support to verify

# 4. Run abbreviated training test
# Deploy short validation job to confirm full-scale training readiness
# Test checkpointing and multi-node communication

# 5. Remove maintenance exclusion for next campaign
gcloud container clusters update TRAINING_CLUSTER \
  --zone ZONE \
  --remove-maintenance-exclusion-name "training-campaign-dec-2024"
```

## Alternative: AI Host Maintenance Strategy (Advanced)

If you cannot wait for a training gap, consider **AI Host Maintenance** for the node pool:

```bash
# 1. Pause new training job submissions
# Set cluster to maintenance mode in your job scheduler

# 2. Apply host maintenance label to trigger parallel node updates
kubectl label nodes -l cloud.google.com/gke-nodepool=gpu-training-pool \
  cloud.google.com/perform-maintenance=true

# 3. This triggers ~4-hour host maintenance per node
# All 512 nodes updated in parallel rather than sequentially
# Faster than traditional rolling upgrade but requires full training restart
```

**Trade-offs:**
- **Pro:** Minimizes total wall-clock downtime (~4h vs days for rolling)  
- **Con:** Requires checkpointing current training and full restart
- **Risk:** All nodes offline simultaneously — no capacity during maintenance

## Critical Pre-upgrade Checklist

```markdown
Pre-Upgrade Checklist: LLM Training Cluster
- [ ] GPUDirect-TCPXO compatibility with GKE 1.32 confirmed with Google
- [ ] Staging cluster tested identical upgrade path successfully
- [ ] Current training campaign completed and checkpointed
- [ ] Next training campaign scheduled after upgrade window
- [ ] Maintenance exclusion active to prevent auto-upgrades
- [ ] Backup of all training checkpoints and model artifacts
- [ ] A3 Mega placement group mappings documented
- [ ] GPU reservation quota confirmed (no surge capacity expected)
- [ ] Training scheduler configured to pause new job submissions
- [ ] On-call team available during upgrade window
- [ ] Rollback plan documented (may require support ticket for CP rollback)
```

## Rollback Considerations

**Control plane:** Two-step upgrade allows rollback to 1.31 during 24h soak period. After completion, rollback requires Google Cloud support.

**Node pools:** Create new pool at 1.31 if critical issues arise:
```bash
# Emergency rollback pool creation
gcloud container node-pools create gpu-training-pool-rollback \
  --cluster TRAINING_CLUSTER \
  --zone ZONE \
  --machine-type a3-megagpu-8g \
  --accelerator type=nvidia-h100-mega-80gb,count=8 \
  --cluster-version 1.31.x-gke.xxxx \
  --num-nodes 512 \
  --placement-type COMPACT \
  --placement-policy-name YOUR_PLACEMENT_POLICY
```

## Timeline Recommendation

**Week -2:** Staging cluster testing, GPUDirect-TCPXO validation  
**Week -1:** Training campaign completion, maintenance exclusion applied  
**Weekend:** Control plane upgrade (two-step with 24h soak)  
**Week +1:** Node pool upgrade during off-peak hours  
**Week +2:** Full training validation, next campaign launch

**Key success factor:** Coordinate with your training team to align upgrade timing with natural campaign boundaries. Never interrupt an active 2-3 week training run — the checkpoint recovery cost far exceeds waiting for completion.
# GKE Upgrade Plan for Large-Scale AI Training Cluster

**Cluster:** 512 H100 nodes (A3 Mega) | **Current:** GKE 1.31 | **Target:** GKE 1.32 | **Workload:** 2-3 week LLM training runs

## Executive Summary

Your upgrade requires a **phased approach** to protect active training runs while maintaining GPUDirect-TCPXO connectivity. The key is using maintenance exclusions during training and dedicated node pool management.

## Critical Constraints

### GPUDirect-TCPXO Requirements
- Requires specific GKE versions for A3 Mega machines
- Custom high-MTU VPC configuration must survive upgrade
- **GPU VMs do not support live migration** — every upgrade forces pod restart
- Compact placement policies may break during node recreation

### Training Run Protection
- 2-3 week runs cannot tolerate mid-job eviction
- GKE's default pod eviction timeout is 1 hour (far shorter than training duration)
- Checkpointing is essential for recovery

### GPU Resource Constraints
- A3 Mega nodes are scarce — assume **no surge capacity available**
- Must use `maxUnavailable` strategy, not `maxSurge`
- Blue-green requires 2x capacity (likely unavailable)

## Recommended Strategy: Dedicated Training Node Pool with Coordinated Upgrade

### Architecture Setup

Create separate node pools to isolate training from other workloads:

```bash
# Training node pool (your existing 512 nodes)
TRAINING_POOL="training-h100-pool"

# Infrastructure node pool (system pods, monitoring, etc.)
INFRA_POOL="infra-pool"
```

### Phase 1: Control Plane Upgrade (Safe During Training)

Control plane upgrades do not affect running pods and can be done during active training:

```bash
# Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.latest

# Verify control plane version
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

**Timeline:** 10-15 minutes, no workload impact.

### Phase 2: Infrastructure Node Pool Upgrade

Upgrade non-GPU node pools first to validate the target version:

```bash
# Configure conservative surge for infra pools
gcloud container node-pools update $INFRA_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade infra pool
gcloud container node-pools upgrade $INFRA_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

### Phase 3: Training Node Pool Protection During Active Training

Apply maintenance exclusion to prevent forced upgrades of training nodes:

```bash
# Block node upgrades during training campaign
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-campaign-q1" \
  --add-maintenance-exclusion-start-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-end-time "2025-03-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

This allows control plane security patches while blocking disruptive node upgrades.

### Phase 4: Training Node Pool Upgrade (During Training Gap)

**Timing:** Execute only during planned training downtime or between training runs.

#### Pre-upgrade Validation

```bash
# Ensure training checkpoints are saved
kubectl get pods -n training-namespace -o wide

# Verify GPU driver compatibility with 1.32
# Test in a small staging cluster first

# Check compact placement group integrity
kubectl describe nodes -l node.kubernetes.io/instance-type=a3-megagpu-8g
```

#### GPU Node Pool Upgrade Strategy

Since surge capacity is unavailable, use the `maxUnavailable` approach:

```bash
# Configure for GPU constraints (no surge capacity)
gcloud container node-pools update $TRAINING_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4

# Start upgrade during training downtime
gcloud container node-pools upgrade $TRAINING_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**Key setting:** `maxUnavailable=4` upgrades 4 nodes at once. GKE's maximum parallelism is ~20 nodes, so you can increase this if you want faster completion and can tolerate larger capacity dips.

#### Monitor Upgrade Progress

```bash
# Watch node upgrade status
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=training-h100-pool -o wide'

# Verify no pods stuck in termination
kubectl get pods -A | grep Terminating

# Check placement group integrity as nodes come back
kubectl describe nodes | grep -A 3 "topology.gke.io/zone"
```

#### Post-Upgrade Validation

```bash
# Verify all training nodes at target version
gcloud container node-pools describe $TRAINING_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --format="value(version)"

# Test GPUDirect-TCPXO connectivity
# Run a small multi-node connectivity test before resuming full training

# Verify compact placement maintained
kubectl get nodes -l cloud.google.com/gke-nodepool=training-h100-pool \
  -o custom-columns=NAME:.metadata.name,ZONE:.metadata.labels['topology\.kubernetes\.io/zone']
```

## GPU-Specific Considerations

### Driver Version Changes
GKE 1.32 may install a different GPU driver version than 1.31:
- **Test in staging first** with your exact training framework (PyTorch, JAX, etc.)
- Verify CUDA version compatibility
- Check that your training containers work with the new driver

### TCPXO Network Configuration
- Verify high-MTU VPC settings survive the upgrade
- Test inter-node RDMA connectivity post-upgrade
- Ensure replacement nodes land in the same placement group

### Capacity Management
```bash
# If you have a GPU reservation, verify it covers replacement nodes
gcloud compute reservations describe RESERVATION_NAME --zone ZONE

# Monitor quota usage during upgrade
gcloud compute project-info describe --format="table(quotas.metric,quotas.usage,quotas.limit)"
```

## Timeline and Coordination

### Estimated Duration (512 H100 nodes)
- **Control plane:** 10-15 minutes
- **Infrastructure pools:** 1-2 hours  
- **Training pool (512 nodes, maxUnavailable=4):** ~25-30 hours

With GKE's ~20 node maximum parallelism, upgrading 512 nodes requires ~26 batches minimum.

### Training Campaign Coordination

1. **Weeks before upgrade:** Apply maintenance exclusion, test 1.32 in staging
2. **Training run completion:** Save checkpoint, scale training to zero
3. **Upgrade window:** Execute training node pool upgrade (plan 36-hour window)
4. **Post-upgrade:** Validate connectivity, resume training from checkpoint
5. **Remove exclusion:** Allow future auto-upgrades after validating stability

## Risk Mitigation

### Rollback Strategy
- **Control plane:** Minor version rollback requires GKE support
- **Node pools:** Create new pool at 1.31, migrate workloads, delete upgraded pool
- **Training continuity:** Resume from last checkpoint (ensure checkpointing is working)

### Capacity Backup Plan
```bash
# If upgrade stalls due to capacity constraints, force completion
# (Only use if training is already stopped)
kubectl drain --force --delete-emptydir-data --ignore-daemonsets NODE_NAME
```

This approach protects your active training runs while upgrading the cluster systematically. The key is **never upgrading training nodes during active training** and thoroughly validating GPU connectivity before resuming production workloads.
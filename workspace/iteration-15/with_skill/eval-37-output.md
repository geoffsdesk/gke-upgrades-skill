# GKE Upgrade Plan: Mixed AI/ML Platform (1.31 → 1.32)

**Cluster Fleet Overview:**
- **Total nodes:** 5,000 across mixed workload types
- **Current version:** 1.31 → **Target version:** 1.32
- **Critical constraints:** Training continuity (H100), inference availability (A100)

## Executive Summary

This plan uses a **4-phase approach** that prioritizes training continuity and inference availability while reducing overall fleet upgrade time. Key strategies:

1. **Training protection:** H100 pools use maintenance exclusions during active campaigns
2. **Inference resilience:** A100 pools use autoscaled blue-green for zero-downtime upgrades
3. **Accelerated development:** T4 development pools upgrade first as canaries
4. **Skip-level node upgrades:** Where possible within 2-version skew limits

**Estimated timeline:** 3-4 weeks total with proper sequencing and soak periods.

## Phase 1: Development & CPU Services (Week 1)

**Scope:** 1,500 nodes (T4 dev + CPU services)
**Strategy:** Fast upgrade with surge to validate 1.32 behavior

### T4 Development Pools (500 nodes)
```bash
# Configure aggressive surge for fast dev upgrades
gcloud container node-pools update t4-dev-pool \
  --cluster ai-dev-cluster \
  --zone us-central1-a \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2

# Note: T4 pools likely have limited surge capacity - using maxUnavailable as primary lever
# Upgrade with drain-first strategy
gcloud container node-pools upgrade t4-dev-pool \
  --cluster ai-dev-cluster \
  --zone us-central1-a \
  --cluster-version 1.32.0-gke.1200
```

### CPU Services (1,000 nodes)
```bash
# Standard surge upgrade for stateless services
gcloud container node-pools update cpu-services-pool \
  --cluster ai-platform-cluster \
  --zone us-central1-a \
  --max-surge-upgrade 50 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade cpu-services-pool \
  --cluster ai-platform-cluster \
  --zone us-central1-a \
  --cluster-version 1.32.0-gke.1200
```

**Validation criteria:**
- [ ] All development workloads functional on 1.32
- [ ] GPU driver compatibility confirmed (CUDA version check)
- [ ] MLOps pipelines operational
- [ ] API server latency within baseline

## Phase 2: A100 Inference Pools (Week 2)

**Scope:** 1,500 A100 nodes serving production inference
**Strategy:** Autoscaled blue-green for zero-downtime upgrades

### Pre-upgrade: Configure autoscaling
```bash
# Enable autoscaling if not already configured
gcloud container node-pools update a100-inference-pool \
  --cluster ai-inference-cluster \
  --zone us-central1-a \
  --enable-autoscaling \
  --total-min-nodes 1400 \
  --total-max-nodes 1600

# Configure autoscaled blue-green strategy
gcloud container node-pools update a100-inference-pool \
  --cluster ai-inference-cluster \
  --zone us-central1-a \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

### Execute upgrade
```bash
# Control plane first
gcloud container clusters upgrade ai-inference-cluster \
  --zone us-central1-a \
  --master \
  --cluster-version 1.32.0-gke.1200

# Node pools with autoscaled blue-green
gcloud container node-pools upgrade a100-inference-pool \
  --cluster ai-inference-cluster \
  --zone us-central1-a \
  --cluster-version 1.32.0-gke.1200
```

**Key benefits of autoscaled blue-green for inference:**
- Green pool scales up as inference traffic shifts over
- Blue pool scales down as pods drain, minimizing cost spike
- No 2x resource requirement like standard blue-green
- Maintains serving capacity throughout upgrade

**Monitoring during A100 upgrade:**
```bash
# Track serving capacity
kubectl get nodes -l cloud.google.com/gke-nodepool=a100-inference-pool -o wide

# Monitor inference latency/throughput
kubectl top pods -n inference --sort-by=cpu

# Verify GPU utilization remains stable
nvidia-smi
```

## Phase 3: Control Plane Upgrades (Week 3)

**Scope:** All remaining clusters (training clusters)
**Strategy:** Control plane only, nodes remain on 1.31 behind maintenance exclusions

### H100 Training Clusters Protection
```bash
# Apply "no minor or node upgrades" exclusion to protect training campaigns
gcloud container clusters update h100-training-cluster-1 \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-start-time "2024-01-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Upgrade control plane only (nodes stay at 1.31)
gcloud container clusters upgrade h100-training-cluster-1 \
  --zone us-central1-a \
  --master \
  --cluster-version 1.32.0-gke.1200
```

**Repeat for all H100 training clusters.**

**Why control plane first:**
- Gets API server to 1.32 for new features/compatibility
- Allows CP security patches while protecting nodes
- Maintains 2-version skew compatibility (1.32 CP, 1.31 nodes)
- Training workloads continue uninterrupted

## Phase 4: H100 Training Nodes (Week 4 - Coordinated with Training Schedule)

**Scope:** 2,000 H100 nodes across training clusters
**Strategy:** Coordinated with training team, using parallel host maintenance during scheduled gaps

### Pre-upgrade coordination
```bash
# Remove maintenance exclusion when training gap begins
gcloud container clusters update h100-training-cluster-1 \
  --zone us-central1-a \
  --remove-maintenance-exclusion "training-protection"
```

### H100 Node Pool Strategy Selection

**For clusters with fixed GPU reservations (most common):**
```bash
# Use maxUnavailable as primary lever - no surge capacity available
gcloud container node-pools update h100-training-pool \
  --cluster h100-training-cluster-1 \
  --zone us-central1-a \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4

# Higher maxUnavailable = faster upgrade but more capacity loss
# 2,000 nodes ÷ 4 maxUnavailable ÷ 20 parallel = ~25 batches
```

**For clusters with GPU reservation headroom:**
```bash
# Verify reservation capacity first
gcloud compute reservations describe h100-reservation --zone us-central1-a

# If headroom exists, use conservative surge
gcloud container node-pools update h100-training-pool \
  --cluster h100-training-cluster-1 \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### Alternative: Parallel Host Maintenance (Advanced)

For maximum speed during training gaps:
```bash
# Apply maintenance label to all H100 nodes simultaneously
kubectl label nodes -l cloud.google.com/gke-nodepool=h100-training-pool \
  cloud.google.com/perform-maintenance=true

# Wait ~4 hours for host maintenance to complete across all nodes
```

**Parallel maintenance benefits:**
- All nodes updated simultaneously (~4h total)
- Minimizes training downtime window
- Best when full cluster restart is acceptable

## Fleet-Wide Coordination

### Maintenance Windows
```bash
# Stagger maintenance windows across clusters to spread load
# Development: Sundays 02:00-06:00 UTC
gcloud container clusters update ai-dev-cluster \
  --maintenance-window-start "2024-01-14T02:00:00Z" \
  --maintenance-window-end "2024-01-14T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"

# Inference: Sundays 06:00-10:00 UTC (after dev validation)
gcloud container clusters update ai-inference-cluster \
  --maintenance-window-start "2024-01-14T06:00:00Z" \
  --maintenance-window-end "2024-01-14T10:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"

# Training: Negotiated windows during campaign gaps
```

### Version Skew Management

**Control plane vs nodes:**
- Phase 3: CP at 1.32, H100 nodes at 1.31 (valid 1-version skew)
- Phase 4: Converge all nodes to 1.32

**Cross-cluster compatibility:**
- Shared services (monitoring, logging) tested against mixed 1.31/1.32 fleet
- Model registry and artifact storage remain backward-compatible

## Risk Mitigation

### Training Continuity Protection
1. **Checkpoint before upgrade:** Ensure all active training runs have recent checkpoints
2. **Campaign coordination:** Schedule H100 upgrades only during planned training gaps
3. **Rollback capability:** Keep blue-green rollback option available for 48h soak period
4. **Maintenance exclusions:** Block auto-upgrades during active campaigns

### Inference Availability Protection
1. **Autoscaled blue-green:** Zero-downtime strategy for A100 pools
2. **Load balancer health checks:** Verify inference endpoints remain healthy
3. **Gradual traffic shift:** Monitor latency/throughput during green pool ramp-up
4. **Circuit breaker:** Automatic fallback if upgrade degrades serving quality

### GPU-Specific Considerations
1. **Driver compatibility:** CUDA version may change with 1.32 - validated in Phase 1
2. **RDMA/GPUDirect:** High-speed interconnect verified post-upgrade
3. **Compact placement:** Verify replacement nodes maintain topology requirements
4. **Reservation interaction:** Monitor GPU quota consumption during upgrades

## Monitoring & Validation

### Per-phase validation checklist
```bash
# Node version verification
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,POOL:.metadata.labels.cloud\.google\.com/gke-nodepool

# GPU driver verification
kubectl get nodes -l accelerator-type -o json | jq '.items[].status.allocatable."nvidia.com/gpu"'

# Workload health
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded

# Performance baseline
# Compare training throughput, inference latency against pre-upgrade metrics
```

### Rollback triggers
- Training throughput degraded >10%
- Inference p99 latency increased >20%
- Any H100 node showing GPU driver issues
- Control plane API latency >2x baseline

## Timeline Summary

| Phase | Duration | Scope | Strategy | Risk Level |
|-------|----------|--------|----------|------------|
| 1 | Week 1 | 1,500 nodes (T4+CPU) | Surge upgrade | Low - dev/services |
| 2 | Week 2 | 1,500 nodes (A100) | Autoscaled blue-green | Medium - inference SLA |
| 3 | Week 3 | All clusters CP | CP-only upgrade | Low - nodes protected |
| 4 | Week 4 | 2,000 nodes (H100) | Coordinated maintenance | High - training impact |

**Total fleet upgrade:** 3-4 weeks with proper sequencing and validation gates.

This plan maximizes training continuity while ensuring inference availability throughout the upgrade process. The phased approach allows early validation on development workloads and provides multiple rollback points if issues arise.
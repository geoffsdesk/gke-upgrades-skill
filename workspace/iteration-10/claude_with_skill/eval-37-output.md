# GKE Upgrade Plan: AI/ML Platform (1.31 → 1.32)

## Executive Summary

Phased upgrade strategy prioritizing training continuity and inference availability across 5,000-node mixed AI/ML platform. H100 training pools upgraded during scheduled maintenance windows, A100 inference pools use rolling updates to maintain service availability.

**Key Constraints:**
- H100 training jobs cannot tolerate mid-run eviction
- A100 inference must maintain 80%+ capacity throughout
- GPU nodes require special handling (no surge capacity assumed)
- 5,000 total nodes = ~250 upgrade batches minimum (20-node GKE parallelism limit)

---

## Phase 1: Pre-Upgrade Preparation

### Environment Assessment
- **Current:** GKE 1.31.x across all clusters
- **Target:** GKE 1.32.x 
- **GPU Driver Impact:** Verify CUDA version compatibility between 1.31→1.32 node images
- **Fleet Size:** 250+ upgrade batches expected (20 nodes max parallel)

### Critical Dependencies
```bash
# Check GPU driver versions in current vs target
gcloud container get-server-config --zone ZONE \
  --format="yaml(validImageTypes,validMasterVersions)"

# Verify H100/A100 reservation capacity
gcloud compute reservations list --filter="zone:(TRAINING_ZONES)"
```

### Training Campaign Coordination
- [ ] Survey active H100 training jobs - completion timeline
- [ ] Identify 72-hour maintenance windows for H100 pools
- [ ] Ensure all training workloads have checkpointing enabled
- [ ] Configure "no minor or node upgrades" exclusions on H100 pools

### Staging Validation
- [ ] Create test cluster with same GPU node configuration
- [ ] Validate training framework + CUDA driver compatibility
- [ ] Test inference serving latency on 1.32
- [ ] Verify compact placement policies survive upgrade

---

## Phase 2: Control Plane Upgrades (All Clusters)

**Timeline:** Week 1
**Impact:** Minimal - no workload disruption

Upgrade all control planes first (required before node upgrades).

```bash
# Control plane upgrade per cluster
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.XXXX

# Verify each cluster before proceeding
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

**Success Criteria:**
- All control planes at 1.32.x
- API server responding normally
- No deprecated API warnings in training/inference workloads

---

## Phase 3: CPU Services Upgrade

**Timeline:** Week 1-2  
**Impact:** Low - standard web services

CPU node pools upgraded first to validate 1.32 stability without GPU complexity.

### CPU Pool Strategy: Standard Surge
```bash
# Configure aggressive surge for faster completion
gcloud container node-pools update cpu-services-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5 \
  --max-unavailable-upgrade 0

# Execute upgrade
gcloud container node-pools upgrade cpu-services-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.XXXX
```

**Monitoring:**
- Service mesh health (if applicable)
- API gateway latency
- Database connection pools
- Inter-service communication

---

## Phase 4: T4 Development Upgrade

**Timeline:** Week 2
**Impact:** Low - development workloads

T4 pools for development/experimentation - can tolerate disruption.

### T4 Pool Strategy: Surge with Limited Capacity
```bash
# Conservative surge - T4s may have limited availability
gcloud container node-pools update t4-dev-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 1

# Execute upgrade
gcloud container node-pools upgrade t4-dev-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.XXXX
```

**Validation:**
- Jupyter notebooks launching correctly
- Model development pipelines functional
- GPU driver compatibility for development frameworks

---

## Phase 5: A100 Inference Upgrade (Highest Complexity)

**Timeline:** Week 3-4
**Impact:** Critical - must maintain service availability

A100 inference pools require rolling updates while maintaining 80%+ serving capacity.

### A100 Pool Strategy: Autoscaled Blue-Green
Use GKE's autoscaled blue-green upgrade to maintain serving capacity while minimizing resource waste.

```bash
# Configure autoscaled blue-green upgrade
gcloud container node-pools update a100-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --min-nodes 10 \
  --max-nodes 200 \
  --upgrade-strategy blue-green-batch \
  --batch-node-count 50 \
  --batch-soak-duration 1h

# Execute upgrade
gcloud container node-pools upgrade a100-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.XXXX
```

### Staged Rollout by Geographic Region
1. **US-Central zones** (20% of inference capacity)
2. **US-West zones** (30% of inference capacity)  
3. **US-East zones** (50% of inference capacity)

Each region waits 24h soak time before next region begins.

### Critical Monitoring During A100 Upgrade
```bash
# Monitor serving capacity
kubectl get nodes -l nodepool=a100-inference -o wide

# Track inference latency
# (Customer-specific monitoring - Prometheus/Grafana queries)

# Watch for GPU memory fragmentation
nvidia-smi | grep "GPU Memory Usage"
```

**Rollback Trigger:** If inference latency degrades >20% or error rate >0.1%, halt upgrade and investigate.

---

## Phase 6: H100 Training Upgrade (Maximum Protection)

**Timeline:** Week 5-6
**Impact:** Critical - training job continuity essential

H100 training pools require coordinated maintenance windows with training teams.

### H100 Pool Strategy: Coordinated Drain-and-Replace

**Pre-upgrade Coordination:**
- [ ] Training teams checkpoint all active jobs
- [ ] Verify 72-hour maintenance window availability
- [ ] Scale non-critical training workloads to zero
- [ ] Apply maintenance exclusions to prevent auto-upgrades

```bash
# Apply "no minor or node upgrades" exclusion during active training
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-campaign-jan2024" \
  --add-maintenance-exclusion-start-time 2024-01-15T00:00:00Z \
  --add-maintenance-exclusion-end-time 2024-01-17T23:59:59Z \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

### Coordinated Upgrade Process
```bash
# Step 1: Cordon all H100 nodes (prevents new scheduling)
kubectl cordon -l nodepool=h100-training

# Step 2: Wait for active training jobs to checkpoint and drain naturally
# (Customer coordinates with training teams - may take 24-48h)

# Step 3: Force drain remaining pods after coordination
kubectl drain -l nodepool=h100-training \
  --ignore-daemonsets \
  --delete-emptydir-data \
  --grace-period=3600 \
  --timeout=7200s

# Step 4: Upgrade empty node pool
gcloud container node-pools upgrade h100-training-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.XXXX

# Step 5: Verify new nodes join with correct placement
kubectl get nodes -l nodepool=h100-training -o wide
# Confirm nodes land in same compact placement group

# Step 6: Remove maintenance exclusion, restart training workloads
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "training-campaign-jan2024"
```

### Training Workload Validation
- [ ] NCCL/RDMA connectivity between H100 nodes
- [ ] Multi-node training job scaling correctly
- [ ] Checkpoint/restore functionality working
- [ ] GPU memory topology preserved (NVLink)

---

## Phase 7: Post-Upgrade Validation

### Fleet-Wide Health Check
```bash
# All clusters and nodes at target version
for cluster in $(gcloud container clusters list --format="value(name)"); do
  echo "=== $cluster ==="
  gcloud container clusters describe $cluster \
    --format="table(name, currentMasterVersion)" \
    --zone ZONE
  gcloud container node-pools list --cluster $cluster \
    --zone ZONE \
    --format="table(name, version, status)"
done

# No degraded workloads
kubectl get pods -A | grep -E "CrashLoop|Error|Pending" | wc -l
# Should return 0
```

### Service Validation by Tier
- **Training:** Launch test multi-node job on H100 pool
- **Inference:** Load test A100 endpoints, verify latency/throughput
- **Development:** Verify Jupyter/notebook environments functional
- **Services:** API health checks passing

### GPU-Specific Validation
```bash
# GPU driver version consistency
kubectl get nodes -o json | jq -r '.items[] | select(.status.allocatable."nvidia.com/gpu" != null) | {name: .metadata.name, driver: .status.nodeInfo.kubeletVersion, gpu_count: .status.allocatable."nvidia.com/gpu"}'

# CUDA compatibility test
kubectl run cuda-test --image=nvidia/cuda:11.8-runtime-ubuntu20.04 \
  --rm -i --tty --restart=Never -- nvidia-smi
```

---

## Risk Mitigation & Rollback

### Rollback Strategy by Pool Type
- **CPU/T4:** Create new node pool at 1.31, migrate workloads, delete upgraded pool
- **A100 Inference:** Use blue-green rollback - uncordon old pool, drain new pool
- **H100 Training:** Coordinate with training teams for maintenance window rollback

### Emergency Procedures
```bash
# Cancel in-progress node pool upgrade
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE
# Contact GKE support with operation ID for stuck upgrades

# GPU-specific rollback concerns
# - Compact placement may break
# - Training checkpoints must be preserved
# - Inference routing needs manual adjustment
```

### Escalation Contacts
- **GKE Support:** Critical severity ticket for stuck upgrades
- **Training Teams:** 24h advance notice for H100 maintenance
- **SRE On-Call:** Service degradation >15 minutes during A100 upgrade

---

## Timeline Summary

| Week | Phase | Scope | Risk | Duration |
|------|-------|--------|------|----------|
| 1 | Control Planes | All clusters | Low | 2-3 days |
| 1-2 | CPU Services | 1,000 nodes | Low | 3-5 days |
| 2 | T4 Development | 500 nodes | Low | 2-3 days |
| 3-4 | A100 Inference | 1,500 nodes | High | 7-10 days |
| 5-6 | H100 Training | 2,000 nodes | Critical | 5-7 days |
| 6 | Validation | Full fleet | Medium | 2 days |

**Total Duration:** 5-6 weeks  
**Critical Path:** A100 inference availability + H100 training coordination

This plan prioritizes your core business requirements while managing the technical constraints of large-scale GPU cluster upgrades. The phased approach allows for early problem detection and minimizes blast radius for your most critical workloads.
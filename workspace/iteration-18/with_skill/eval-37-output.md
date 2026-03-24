# GKE Upgrade Plan: AI/ML Platform Fleet (1.31 → 1.32)

## Executive Summary

**Scope:** 5,000-node mixed AI/ML platform upgrade from GKE 1.31 to 1.32
- 2,000 H100 GPU nodes (training)
- 1,500 A100 GPU nodes (inference) 
- 500 T4 nodes (development)
- 1,000 CPU nodes (services)

**Strategy:** Phased approach prioritizing training continuity and inference availability
**Timeline:** 3-4 weeks total with built-in soak periods
**Risk Level:** Medium (large GPU fleet, but skip-level node upgrades minimize cycles)

## Phase Structure

### Phase 1: Non-GPU Foundation (Days 1-5)
**Target:** CPU services and T4 dev nodes
**Impact:** Minimal - development workloads tolerant, services designed for rolling updates

### Phase 2: Inference Infrastructure (Days 8-14) 
**Target:** A100 inference nodes
**Impact:** Controlled - autoscaled blue-green maintains serving capacity

### Phase 3: Training Infrastructure (Days 17-23)
**Target:** H100 training nodes during scheduled training gaps
**Impact:** Minimal - coordinated with training calendar

## Detailed Phase Plan

## Phase 1: Foundation Services (Days 1-5)

### Objectives
- Establish stable 1.32 control planes
- Validate GPU driver compatibility (CUDA version changes)
- Upgrade low-risk development and service nodes

### Pre-Phase Requirements
- [ ] Training calendar reviewed - no critical runs starting Days 17-23
- [ ] Inference traffic patterns analyzed for maintenance windows
- [ ] GPU driver compatibility tested: GKE 1.32 + target CUDA version
- [ ] Staging cluster validated with representative workloads
- [ ] PDBs configured for all stateful services

### Control Plane Upgrades (All Clusters)
```bash
# Upgrade all control planes first (sequential minor version required)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.latest

# Validate each control plane before proceeding
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

**Timeline:** 2-3 days across all clusters
**Validation:** API server health, system pod stability, no deprecated API errors

### CPU Services Node Pools
**Strategy:** Surge upgrade with percentage-based sizing
**Settings:** `maxSurge=5%` (50 nodes), `maxUnavailable=0`

```bash
gcloud container node-pools update services-pool \
  --cluster SERVICES_CLUSTER \
  --zone ZONE \
  --max-surge-upgrade 50 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade services-pool \
  --cluster SERVICES_CLUSTER \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**Expected Duration:** 8-12 hours (1,000 nodes ÷ 20 max parallelism = ~50 batches)

### T4 Development Nodes  
**Strategy:** Aggressive surge (development workloads tolerant)
**Settings:** `maxSurge=10%` (50 nodes), `maxUnavailable=0`

```bash
gcloud container node-pools update t4-dev-pool \
  --cluster DEV_CLUSTER \
  --zone ZONE \
  --max-surge-upgrade 50 \
  --max-unavailable-upgrade 0
```

**Expected Duration:** 6-8 hours (500 nodes, higher concurrency acceptable)

### Phase 1 Success Criteria
- [ ] All control planes at 1.32
- [ ] CPU and T4 node pools at 1.32
- [ ] Services responding normally
- [ ] GPU driver version confirmed compatible
- [ ] No deprecated API usage detected

## Phase 2: Inference Infrastructure (Days 8-14)

### Objectives
- Upgrade A100 inference nodes with zero service interruption
- Validate inference latency/throughput post-upgrade
- Establish pattern for GPU pool upgrades

### Pre-Phase Requirements
- [ ] Inference monitoring baselines captured (latency p95, throughput, error rates)
- [ ] Model loading tests completed on 1.32 staging
- [ ] GPU surge capacity confirmed unavailable (fixed reservations)

### A100 Inference Pools
**Strategy:** Autoscaled blue-green (maintains serving capacity, cost-efficient)
**Rationale:** 
- GPU VMs don't support live migration - every upgrade causes pod restart
- Autoscaled blue-green keeps old pool serving while new pool warms up
- Avoids inference latency spikes from surge drain-and-restart

```bash
# Enable autoscaling and configure autoscaled blue-green
gcloud container node-pools update a100-inference-pool \
  --cluster INFERENCE_CLUSTER \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 100 \
  --total-max-nodes 1500 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

gcloud container node-pools upgrade a100-inference-pool \
  --cluster INFERENCE_CLUSTER \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**Expected Duration:** 2-3 days (1,500 nodes, autoscaled transition)
**Key Monitoring:** Model loading time, inference latency, GPU utilization

### Inference Validation Protocol
```bash
# Monitor model serving health
kubectl get pods -l app=inference-server -o wide
kubectl top pods -l app=inference-server --containers

# Validate GPU driver version
kubectl exec -it POD_NAME -- nvidia-smi

# Test representative inference requests
curl -X POST INFERENCE_ENDPOINT/predict -d @test_payload.json
```

### Phase 2 Success Criteria
- [ ] A100 pools fully upgraded to 1.32
- [ ] Inference latency within 5% of baseline
- [ ] Model loading successful on all instances
- [ ] GPU driver version confirmed stable
- [ ] Zero service interruption achieved

## Phase 3: Training Infrastructure (Days 17-23)

### Objectives  
- Upgrade H100 training nodes during scheduled maintenance gaps
- Preserve long-running training jobs
- Validate RDMA/GPUDirect connectivity post-upgrade

### Pre-Phase Requirements
- [ ] Training calendar coordination complete
- [ ] Active jobs checkpointed and pausable
- [ ] RDMA topology validated on 1.32 staging
- [ ] Compact placement policy verified for replacement nodes

### Training Job Coordination
**Critical:** Coordinate with ML teams for training pause windows

```bash
# Apply maintenance exclusion during active training periods
gcloud container clusters update TRAINING_CLUSTER \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-campaign" \
  --add-maintenance-exclusion-start-time 2024-MM-DDTHH:MM:SSZ \
  --add-maintenance-exclusion-end-time 2024-MM-DDTHH:MM:SSZ \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

### H100 Training Pools
**Strategy:** Custom blue-green with AI Host Maintenance
**Rationale:**
- Training workloads are batch - can tolerate coordinated restarts
- AI Host Maintenance (~4h per node) required for accelerator nodes
- Parallel strategy minimizes total wall-clock time

```bash
# Coordinate with training teams to pause active jobs
# Scale training workloads to zero or ensure checkpointed state

# Apply parallel host maintenance to all H100 nodes
kubectl label nodes -l cloud.google.com/gke-nodepool=h100-training \
  cloud.google.com/perform-maintenance=true

# Monitor host maintenance progress (~4 hours)
kubectl get nodes -l cloud.google.com/gke-nodepool=h100-training \
  -o custom-columns=NAME:.metadata.name,STATUS:.status.conditions[-1].type
```

**Expected Duration:** 4-6 hours for host maintenance + 2 days for workload validation
**Key Monitoring:** RDMA connectivity, training job restart success, placement group integrity

### Training Validation Protocol
```bash
# Verify RDMA connectivity between nodes
kubectl exec -it TRAINING_POD -- /opt/google/gpudirect-tcpx/configure.py --check

# Confirm placement group integrity  
kubectl get nodes -l cloud.google.com/gke-nodepool=h100-training \
  -o custom-columns=NAME:.metadata.name,ZONE:.metadata.labels.topology\.gke\.io/zone

# Test training job restart from checkpoint
kubectl apply -f training-job.yaml
# Monitor job recovery and inter-node communication
```

### Phase 3 Success Criteria
- [ ] H100 pools fully upgraded to 1.32  
- [ ] RDMA/GPUDirect connectivity verified
- [ ] Training jobs successfully resumed from checkpoints
- [ ] Compact placement maintained
- [ ] Inter-node bandwidth validated

## Risk Mitigation & Rollback

### High-Risk Scenarios
1. **GPU driver incompatibility** → Staging validation prevents production issues
2. **RDMA connectivity loss** → Pre-validated networking stack changes  
3. **Training job data corruption** → Mandatory checkpointing + backup verification
4. **Inference latency regression** → Autoscaled blue-green allows immediate rollback

### Rollback Procedures
```bash
# Node pool rollback (create new pool at old version)
gcloud container node-pools create POOL_NAME-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.previous \
  --num-nodes NUM_NODES \
  --machine-type MACHINE_TYPE

# Migrate workloads back
kubectl cordon -l cloud.google.com/gke-nodepool=NEW_POOL
kubectl drain -l cloud.google.com/gke-nodepool=NEW_POOL --ignore-daemonsets
```

### Emergency Contacts
- **GKE Support:** Premium support case with cluster details
- **Training Team Lead:** For H100 job coordination  
- **Inference Team Lead:** For A100 service impact
- **Platform SRE:** 24/7 escalation during upgrade windows

## Monitoring & Validation

### Key Metrics Throughout Upgrade
```bash
# Cluster health
kubectl get nodes | grep NotReady | wc -l
kubectl get pods -A | grep -E "Error|CrashLoop" | wc -l

# GPU utilization
kubectl top nodes -l accelerator=nvidia-tesla-h100
kubectl top nodes -l accelerator=nvidia-tesla-a100

# Inference serving
curl -w "@curl-format.txt" INFERENCE_ENDPOINT/health
```

### Success Criteria Dashboard
- [ ] Control plane API latency <100ms p95
- [ ] Node ready ratio >99%
- [ ] GPU utilization restored to pre-upgrade levels
- [ ] Inference latency within baseline +5%
- [ ] Training throughput within baseline +2%
- [ ] Zero data loss incidents

## Timeline Summary

| Phase | Duration | Target | Strategy | Risk |
|-------|----------|---------|----------|------|
| 1 | Days 1-5 | CPU + T4 (1,500 nodes) | Surge upgrade | Low |
| 2 | Days 8-14 | A100 inference (1,500 nodes) | Autoscaled blue-green | Medium |  
| 3 | Days 17-23 | H100 training (2,000 nodes) | Host maintenance | Medium |

**Total Timeline:** 3-4 weeks including soak periods and validation windows

This phased approach ensures training continuity by upgrading training infrastructure last, maintains inference availability through autoscaled blue-green strategy, and validates GPU compatibility early with development nodes.
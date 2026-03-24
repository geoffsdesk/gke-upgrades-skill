# GKE AI/ML Platform Upgrade Plan: 1.31 → 1.32

## Executive Summary

**Cluster:** Mixed AI/ML Platform (5,000 nodes)  
**Current:** GKE 1.31  
**Target:** GKE 1.32  
**Strategy:** Phased approach prioritizing training continuity and inference availability

### Fleet Composition
- 2,000 H100 nodes (training) - **highest priority for continuity**
- 1,500 A100 nodes (inference) - **maintain serving capacity**
- 500 T4 nodes (development) - **upgrade first, lowest risk**
- 1,000 CPU nodes (services) - **support infrastructure**

## Upgrade Strategy Overview

**Phase 1:** Dev/Test (T4 + CPU subset) - validate target version  
**Phase 2:** CPU Services - minimize training/inference impact  
**Phase 3:** A100 Inference - rolling with capacity preservation  
**Phase 4:** H100 Training - coordinated with training schedules

## Pre-Upgrade Prerequisites

### Version Compatibility Check
```bash
# Verify 1.32 available in your release channel
gcloud container get-server-config --zone ZONE --format="yaml(channels)"

# Check deprecated API usage across all clusters
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Verify CUDA/driver compatibility for GPU workloads
# H100: Requires CUDA 12.0+ - confirm target GKE 1.32 node image supports
# A100: CUDA 11.8+ supported - verify inference model compatibility
```

### Critical Staging Validation
**Mandatory before production:** Deploy a staging cluster with GKE 1.32 and test:
- Representative training workload on H100-equivalent hardware
- Inference serving pipeline on A100-equivalent hardware  
- Model loading, CUDA calls, and throughput benchmarks
- GPUDirect-TCPX/RDMA functionality if used

### Maintenance Window Configuration
```bash
# Configure conservative maintenance windows (off-peak for each workload type)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-duration 8h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### Training Job Protection
```bash
# Apply "no minor or node upgrades" exclusion to H100 training clusters
# Allows CP security patches, blocks disruptive upgrades during training campaigns
gcloud container clusters update H100_TRAINING_CLUSTER \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## Phase 1: Development Environment (Week 1)
**Target:** T4 development nodes + 200 CPU service nodes  
**Risk:** Low - development workloads are restart-tolerant

### T4 Development Pool (500 nodes)
**Strategy:** Surge upgrade with higher concurrency
```bash
# Configure aggressive surge for dev workloads
gcloud container node-pools update t4-dev-pool \
  --cluster DEV_CLUSTER \
  --zone ZONE \
  --max-surge-upgrade 25 \
  --max-unavailable-upgrade 0

# Upgrade control plane first
gcloud container clusters upgrade DEV_CLUSTER \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.latest

# Upgrade T4 node pool (skip-level upgrade recommended)
gcloud container node-pools upgrade t4-dev-pool \
  --cluster DEV_CLUSTER \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**Expected Duration:** 4-6 hours  
**Validation:** Dev teams test jupyter notebooks, model training scripts, data pipelines

### Subset of CPU Services (200 nodes)
**Strategy:** Conservative surge to validate services impact
```bash
# Start with smaller surge for services
gcloud container node-pools update cpu-services-subset \
  --cluster SERVICES_CLUSTER \
  --zone ZONE \
  --max-surge-upgrade 10 \
  --max-unavailable-upgrade 0
```

**Validation Criteria:**
- [ ] All development workflows functional
- [ ] No CUDA compatibility issues on T4
- [ ] Service discovery and networking intact
- [ ] Monitoring/logging pipelines healthy

**Go/No-Go Decision:** Phase 1 must complete successfully before proceeding to production workloads.

## Phase 2: CPU Services Infrastructure (Week 2)
**Target:** Remaining 800 CPU nodes supporting platform services  
**Risk:** Medium - services support training/inference workloads

### Service Dependencies Mapping
Critical services to monitor during upgrade:
- Model registry and artifact storage
- Monitoring/observability stack (Prometheus, Grafana)
- CI/CD pipelines and GitOps controllers
- Ingress controllers and load balancers
- Shared databases and caching layers

### CPU Services Upgrade
```bash
# Conservative surge for production services
gcloud container node-pools update cpu-services-prod \
  --cluster SERVICES_CLUSTER \
  --zone ZONE \
  --max-surge-upgrade 40 \
  --max-unavailable-upgrade 0

# Control plane upgrade
gcloud container clusters upgrade SERVICES_CLUSTER \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.latest

# Node pool upgrade (skip-level recommended)
gcloud container node-pools upgrade cpu-services-prod \
  --cluster SERVICES_CLUSTER \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**Expected Duration:** 8-12 hours  
**Critical Monitoring:** Service availability, API latency, artifact access times

## Phase 3: A100 Inference Platform (Week 3)
**Target:** 1,500 A100 nodes serving production inference  
**Risk:** High - customer-facing inference workloads

### A100 Inference Strategy Selection

**Recommended:** Autoscaled Blue-Green Upgrade
- Maintains serving capacity throughout upgrade
- Avoids inference latency spikes from pod restarts
- Scales down old pool as new pool serves traffic
- Requires sufficient A100 capacity for replacement nodes

```bash
# Enable autoscaling on A100 inference pools
gcloud container node-pools update a100-inference-pool \
  --cluster INFERENCE_CLUSTER \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 1200 \
  --total-max-nodes 2000

# Configure autoscaled blue-green
gcloud container node-pools update a100-inference-pool \
  --cluster INFERENCE_CLUSTER \
  --zone ZONE \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.33,blue-green-full-batch-timeout=7200s
```

**Alternative if A100 surge capacity unavailable:**
```bash
# Drain-first approach (causes temporary capacity reduction)
gcloud container node-pools update a100-inference-pool \
  --cluster INFERENCE_CLUSTER \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 20
```

### Inference Workload Protection
```bash
# Configure PDBs for inference services
kubectl apply -f - <<EOF
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: inference-pdb
  namespace: inference
spec:
  minAvailable: 80%
  selector:
    matchLabels:
      workload-type: inference
EOF
```

**Expected Duration:** 12-16 hours  
**Key Metrics:** Inference latency (p95/p99), throughput (requests/sec), error rates

### A100 Upgrade Execution
1. **Control plane upgrade** (inference keeps serving)
2. **Create green A100 pool** with 1.32
3. **Warm up models** on green pool (5-10 minutes per model)
4. **Traffic shift validation** - gradual load balancer migration
5. **Soak period** (2 hours) - monitor latency/error rates
6. **Blue pool cleanup** once green pool proven stable

## Phase 4: H100 Training Platform (Week 4)
**Target:** 2,000 H100 nodes for large-scale training  
**Risk:** Highest - multi-day training jobs cannot be interrupted

### Training Coordination Prerequisites
**Critical:** Coordinate with ML teams for training job schedules
- [ ] Identify training job completion windows (gaps between runs)
- [ ] Verify checkpoint/resume capability for all active training jobs
- [ ] Confirm no critical model deadlines during upgrade window
- [ ] Enable PDBs on training workloads to block premature eviction

### H100 Training Strategy

**Option A: Planned Training Gap (Recommended)**
Coordinate upgrade during planned gap between training campaigns:
```bash
# Remove training protection exclusion during planned gap
gcloud container clusters update H100_TRAINING_CLUSTER \
  --zone ZONE \
  --remove-maintenance-exclusion "training-protection"

# Use parallel host maintenance strategy for speed
# All nodes upgraded simultaneously during the gap
gcloud container node-pools upgrade h100-training-pool \
  --cluster TRAINING_CLUSTER \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**Option B: Rolling Upgrade with Training Protection**
If no suitable gap available:
```bash
# Drain-first upgrade to avoid quota constraints
gcloud container node-pools update h100-training-pool \
  --cluster TRAINING_CLUSTER \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1

# Very conservative - 1 node at a time
# Allows training jobs to complete before node eviction
```

### Training Workload PDB Configuration
```bash
kubectl apply -f - <<EOF
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-pdb
  namespace: training
spec:
  minAvailable: 90%
  selector:
    matchLabels:
      workload-type: training
EOF
```

**Expected Duration:** 
- Option A (planned gap): 6-8 hours
- Option B (rolling): 3-5 days

### Multi-day Job Protection
For training jobs exceeding 8 hours:
```bash
# Extend termination grace period
# Training pods should have terminationGracePeriodSeconds > max job duration
# Example for 48-hour training runs:
terminationGracePeriodSeconds: 172800  # 48 hours
```

## Fleet Coordination & Rollback Plan

### Multi-Cluster Sequencing
```bash
# Optional: Configure rollout sequencing for automated coordination
gcloud container fleet clusterupgrade update \
  --project=PROJECT_ID \
  --upstream-fleet=DEV_FLEET_PROJECT \
  --default-upgrade-soaking=48h
```

### Emergency Rollback Procedures

**Control Plane Rollback (if critical issues in 1.32):**
- Contact Google Cloud Support immediately
- Control plane minor downgrades require support assistance
- Have cluster names, zones, and timeline ready

**Node Pool Rollback:**
```bash
# Create new pool at 1.31 (old version)
gcloud container node-pools create NODE_POOL_NAME-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.previous \
  --machine-type ORIGINAL_MACHINE_TYPE \
  --accelerator type=nvidia-h100-80gb,count=8

# Migrate workloads to rollback pool
kubectl cordon -l cloud.google.com/gke-nodepool=NODE_POOL_NAME
kubectl drain -l cloud.google.com/gke-nodepool=NODE_POOL_NAME --force
```

## Monitoring & Validation

### Pre-Upgrade Baseline Metrics
Capture before each phase:
```bash
# Training metrics
kubectl top nodes -l accelerator=nvidia-h100-80gb
kubectl get pods -n training -o wide

# Inference metrics  
kubectl top nodes -l accelerator=nvidia-a100-80gb
curl -s INFERENCE_ENDPOINT/health | jq

# Service availability
kubectl get pods -n kube-system | grep -v Running
```

### Phase-Specific Success Criteria

**Phase 1 (T4 Dev):**
- [ ] All jupyter notebooks launch successfully
- [ ] Model training scripts execute without CUDA errors
- [ ] Data pipeline ETL jobs complete

**Phase 2 (CPU Services):**
- [ ] All production services healthy (0 restarts)
- [ ] Model registry accessible (API response time <100ms)
- [ ] CI/CD pipelines deploying successfully

**Phase 3 (A100 Inference):**
- [ ] Inference latency within 5% of baseline (p95/p99)
- [ ] No increase in 5xx error rates
- [ ] Model loading times unchanged

**Phase 4 (H100 Training):**
- [ ] Training job checkpoints/resumes working
- [ ] Multi-node training communication intact
- [ ] GPUDirect-TCPX performance maintained (if used)

### Critical Alert Thresholds
```yaml
# Configure monitoring alerts
- alert: GPUNodeUpgradeFailed
  expr: kube_node_status_condition{condition="Ready",status="false"} and on(node) kube_node_info{accelerator!=""}
  for: 10m

- alert: InferenceLatencyDegraded  
  expr: histogram_quantile(0.95, inference_request_duration_seconds) > 1.2 * baseline
  for: 5m

- alert: TrainingJobEvicted
  expr: increase(kube_pod_container_status_restarts_total{namespace="training"}[5m]) > 0
```

## Risk Mitigation

### GPU-Specific Risks
1. **CUDA version incompatibility** - Mandatory staging validation prevents this
2. **GPUDirect connectivity issues** - Test RDMA functionality in staging
3. **Driver loading failures** - Monitor node Ready status closely
4. **Inference serving degradation** - Blue-green strategy maintains capacity

### Training Workload Risks
1. **Multi-day job interruption** - Coordinate with training schedules
2. **Checkpoint corruption** - Verify backup/recovery procedures
3. **Node placement changes** - Use placement policies for locality

### Large-Scale Risks
1. **Quota exhaustion** - Use maxUnavailable=1 for GPU pools (no surge needed)
2. **Upgrade timeouts** - 20-node parallelism limit means H100 takes days if rolling
3. **Partial failures** - Mixed-version state is acceptable, retry failed upgrades

## Timeline Summary

| Week | Phase | Target | Risk | Duration |
|------|--------|---------|------|----------|
| 1 | Dev/Test | T4 (500) + CPU subset (200) | Low | 6 hours |
| 2 | Services | CPU (800) | Medium | 12 hours |  
| 3 | Inference | A100 (1,500) | High | 16 hours |
| 4 | Training | H100 (2,000) | Highest | 8 hours (gap) / 5 days (rolling) |

**Total Fleet Upgrade Time:** 4 weeks (conservative) or 2 weeks (aggressive with training gap)

This phased approach ensures training continuity while maintaining inference availability throughout the upgrade process. The extensive validation and rollback procedures protect against the high-impact risks inherent in upgrading large-scale AI/ML infrastructure.
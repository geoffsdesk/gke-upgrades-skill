# GKE AI/ML Fleet Upgrade Plan: 1.31 → 1.32

## Executive Summary

**Scope:** 5,000-node mixed AI/ML platform upgrade  
**Target:** GKE 1.31 → 1.32 (single minor version jump)  
**Priority:** Training continuity (H100) > Inference availability (A100) > Dev/Services  
**Timeline:** 3-4 weeks with extended soak periods  
**Strategy:** Phased rollout with training-first protection

## Fleet Architecture Analysis

| Pool Type | Count | Usage Pattern | Upgrade Priority | Strategy |
|-----------|-------|---------------|------------------|----------|
| H100 Training | 2,000 | Long-running (days/weeks) | **CRITICAL** - Defer until training gaps | Maintenance exclusion + manual |
| A100 Inference | 1,500 | Latency-sensitive serving | **HIGH** - Autoscaled blue-green | Rolling with capacity preservation |
| T4 Development | 500 | Experimentation, testing | **MEDIUM** - Test bed for validation | Surge upgrade first |
| CPU Services | 1,000 | Platform services, APIs | **LOW** - Standard workloads | Surge upgrade |

## Phase 1: Pre-Upgrade Foundation (Week 1)

### 1.1 Version Compatibility Validation
```bash
# Check target version availability
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels)" | grep -A 10 "1.32"

# Verify no deprecated API usage
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Check GKE deprecation insights
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=LOCATION \
  --project=PROJECT_ID \
  --filter="category.category:RELIABILITY"
```

### 1.2 GPU Driver Compatibility Testing
**Critical:** GKE 1.32 may change CUDA driver versions. Test in staging before production.

```bash
# Create staging T4 pool with target version
gcloud container node-pools create t4-staging-132 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --machine-type g2-standard-4 \
  --accelerator type=nvidia-tesla-t4,count=1 \
  --num-nodes 2 \
  --cluster-version 1.32.X-gke.XXXX

# Deploy representative ML workloads
kubectl apply -f staging-inference-test.yaml
kubectl apply -f staging-training-test.yaml
```

**Validation checklist:**
- [ ] TensorFlow/PyTorch model loading
- [ ] CUDA memory allocation
- [ ] Multi-GPU communication (NCCL)
- [ ] Inference throughput baseline
- [ ] Training convergence validation

### 1.3 Training Campaign Coordination
**H100 Protection Strategy:** Block upgrades during active training runs.

```bash
# Apply "no minor or node upgrades" exclusion to H100 clusters
gcloud container clusters update h100-training-cluster \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Training schedule review:**
- [ ] Identify upcoming training campaign gaps (2-3 day windows)
- [ ] Coordinate with ML teams on checkpoint schedules
- [ ] Plan H100 upgrades only during confirmed training breaks

## Phase 2: Development & Validation (Week 1-2)

### 2.1 T4 Development Pools - Canary Upgrade
**Rationale:** T4 pools are lowest risk and provide real workload validation.

```bash
# Configure conservative surge settings
gcloud container node-pools update t4-dev-pool \
  --cluster dev-cluster \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade control plane first
gcloud container clusters upgrade dev-cluster \
  --zone ZONE \
  --master \
  --cluster-version 1.32.X-gke.XXXX

# Wait 30 minutes, verify system pods
kubectl get pods -n kube-system

# Upgrade T4 node pools
gcloud container node-pools upgrade t4-dev-pool \
  --cluster dev-cluster \
  --zone ZONE \
  --cluster-version 1.32.X-gke.XXXX
```

**Soak period:** 48 hours with intensive validation:
- [ ] Model training job completion rates
- [ ] Jupyter notebook connectivity
- [ ] ML pipeline execution
- [ ] GPU utilization metrics
- [ ] Developer workflow validation

### 2.2 CPU Services Pools
**Strategy:** Standard surge upgrade during off-peak hours.

```bash
# Set maintenance window (weekend early morning)
gcloud container clusters update services-cluster \
  --zone ZONE \
  --maintenance-window-start "2024-01-13T02:00:00Z" \
  --maintenance-window-duration 6h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Configure percentage-based surge for large pools
gcloud container node-pools update cpu-services-pool \
  --cluster services-cluster \
  --zone ZONE \
  --max-surge-upgrade 50 \
  --max-unavailable-upgrade 0
```

**Expected duration:** ~8-12 hours for 1,000 nodes (GKE's ~20 node parallelism limit)

## Phase 3: A100 Inference Pools (Week 2-3)

### 3.1 A100 Upgrade Strategy Selection
**Challenge:** Fixed GPU reservations = no surge capacity available  
**Solution:** Autoscaled blue-green for inference continuity

```bash
# Enable autoscaling on A100 pools
gcloud container node-pools update a100-inference-pool \
  --cluster inference-cluster \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 100 \
  --total-max-nodes 1500

# Configure autoscaled blue-green upgrade
gcloud container node-pools update a100-inference-pool \
  --cluster inference-cluster \
  --zone ZONE \
  --enable-blue-green-upgrade \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.20,blue-green-full-batch-timeout=3600s
```

### 3.2 Inference Capacity Management
**Critical:** Maintain serving capacity throughout upgrade.

**Pre-upgrade preparation:**
```bash
# Scale up inference replicas 20% for redundancy
kubectl scale deployment inference-service --replicas=120

# Configure PDBs for inference pods
kubectl apply -f - <<EOF
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: inference-pdb
spec:
  minAvailable: 80%
  selector:
    matchLabels:
      app: inference-service
EOF
```

**Monitoring during upgrade:**
- [ ] Inference latency (p95 < baseline + 20%)
- [ ] Request success rate (> 99.9%)
- [ ] GPU utilization across pools
- [ ] Model serving capacity

### 3.3 A100 Upgrade Execution
**Timeline:** Stagger across zones/regions for capacity preservation.

```bash
# Upgrade zones sequentially
for zone in us-central1-a us-central1-b us-central1-c; do
  echo "Upgrading A100 pool in $zone"
  
  # Control plane first
  gcloud container clusters upgrade inference-cluster-$zone \
    --zone $zone \
    --master \
    --cluster-version 1.32.X-gke.XXXX
  
  # Wait for CP upgrade completion
  sleep 900
  
  # Node pool with autoscaled blue-green
  gcloud container node-pools upgrade a100-inference-pool \
    --cluster inference-cluster-$zone \
    --zone $zone \
    --cluster-version 1.32.X-gke.XXXX
  
  # 24h soak between zones
  echo "Soaking zone $zone for 24 hours"
  sleep 86400
done
```

## Phase 4: H100 Training Pools (Week 3-4)

### 4.1 Training Campaign Coordination
**Prerequisites:** 
- [ ] Active training runs completed or checkpointed
- [ ] 72-hour training gap confirmed with ML teams
- [ ] Emergency rollback plan validated

### 4.2 H100 Upgrade Strategy
**Challenge:** No GPU surge capacity + multi-day training sensitivity  
**Solution:** Controlled manual blue-green with extended validation

```bash
# Remove training protection exclusion
gcloud container clusters update h100-training-cluster \
  --zone ZONE \
  --remove-maintenance-exclusion-name "training-protection"

# Set extended maintenance window (3-day weekend)
gcloud container clusters update h100-training-cluster \
  --zone ZONE \
  --maintenance-window-start "2024-01-26T18:00:00Z" \
  --maintenance-window-duration 72h \
  --maintenance-window-recurrence "FREQ=MONTHLY"
```

### 4.3 H100 Manual Blue-Green Process
**Rationale:** Maximum control for highest-value workloads.

```bash
# Create new H100 pool at target version (requires significant quota)
gcloud container node-pools create h100-training-v132 \
  --cluster h100-training-cluster \
  --zone ZONE \
  --machine-type a3-highgpu-8g \
  --num-nodes 500 \
  --cluster-version 1.32.X-gke.XXXX \
  --placement-type COMPACT \
  --placement-group-name training-placement-group

# Cordon old pool
kubectl cordon -l cloud.google.com/gke-nodepool=h100-training-v131

# Verify new nodes in same placement group (critical for RDMA)
kubectl get nodes -l cloud.google.com/gke-nodepool=h100-training-v132 \
  -o custom-columns=NAME:.metadata.name,ZONE:.metadata.labels.topology\.kubernetes\.io/zone

# Test training job on new pool
kubectl apply -f test-training-job-h100.yaml

# Monitor for 48 hours before proceeding with full migration
```

### 4.4 Training Workload Migration
**Process:** Conservative, one training team at a time.

```bash
# Migrate training namespaces incrementally
for ns in team-1 team-2 team-3; do
  echo "Migrating training workloads for $ns"
  
  # Add node affinity for new pool
  kubectl patch deployment -n $ns training-job \
    -p '{"spec":{"template":{"spec":{"nodeSelector":{"cloud.google.com/gke-nodepool":"h100-training-v132"}}}}}'
  
  # Wait for pods to reschedule and validate
  kubectl rollout status deployment/training-job -n $ns
  
  # 24h validation per team
  sleep 86400
done

# Delete old pool only after all teams validated
gcloud container node-pools delete h100-training-v131 \
  --cluster h100-training-cluster \
  --zone ZONE
```

## Monitoring & Validation Framework

### Critical Metrics Dashboard
```bash
# GPU utilization across all pools
kubectl top nodes --selector="accelerator=nvidia-tesla-h100"
kubectl top nodes --selector="accelerator=nvidia-tesla-a100"

# Training job completion rates
kubectl get jobs -A --field-selector=status.phase=Failed

# Inference latency monitoring
curl -s http://monitoring-endpoint/metrics | grep inference_latency_p95

# Resource allocation efficiency
kubectl describe nodes | grep -A5 "Allocated resources" | grep -E "gpu|memory|cpu"
```

### Upgrade Status Tracking
```bash
# Fleet-wide version inventory
for cluster in dev-cluster inference-cluster-* h100-training-cluster; do
  echo "=== $cluster ==="
  gcloud container clusters describe $cluster --zone ZONE \
    --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"
done

# Node pool upgrade progress
gcloud container operations list \
  --filter="operationType=UPGRADE_NODES AND status=RUNNING" \
  --format="table(name, operationType, status, startTime)"
```

## Rollback & Emergency Procedures

### Immediate Rollback Triggers
- [ ] Training convergence failure (>10% degradation)
- [ ] Inference latency spike (>50% increase)
- [ ] GPU driver incompatibility
- [ ] RDMA connectivity loss in training clusters
- [ ] Critical model serving outage

### H100 Emergency Rollback
```bash
# Re-enable training protection immediately
gcloud container clusters update h100-training-cluster \
  --zone ZONE \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Create emergency rollback pool
gcloud container node-pools create h100-emergency-rollback \
  --cluster h100-training-cluster \
  --zone ZONE \
  --machine-type a3-highgpu-8g \
  --cluster-version 1.31.X-gke.XXXX \
  --num-nodes 100 \
  --placement-type COMPACT
```

### A100 Inference Rollback
```bash
# Scale up old pool if still exists
kubectl uncordon -l cloud.google.com/gke-nodepool=a100-inference-v131

# Route traffic back to old pool
kubectl patch service inference-service \
  -p '{"spec":{"selector":{"pool-version":"v131"}}}'
```

## Timeline Summary

| Phase | Duration | Scope | Risk Level |
|-------|----------|-------|------------|
| **Week 1** | Setup & T4 Dev | 500 nodes | Low |
| **Week 2** | CPU Services & A100 Prep | 1,000 nodes | Medium |
| **Week 3** | A100 Inference | 1,500 nodes | High |
| **Week 4** | H100 Training | 2,000 nodes | **Critical** |

## Success Criteria

### Phase Gates
- [ ] **T4 Dev:** 48h soak with no ML pipeline failures
- [ ] **CPU Services:** Platform APIs maintain 99.9% availability
- [ ] **A100 Inference:** Serving latency within 10% of baseline
- [ ] **H100 Training:** First validation job completes successfully

### Final Validation
- [ ] All 5,000 nodes running GKE 1.32
- [ ] Training throughput matches pre-upgrade baseline
- [ ] Inference services meet SLA requirements
- [ ] No GPU driver compatibility issues
- [ ] RDMA topology preserved in training clusters
- [ ] Cost impact within 5% of baseline (accounting for temporary blue-green overhead)

**Estimated Total Duration:** 3-4 weeks  
**Expected Training Downtime:** <72 hours (only during H100 upgrade window)  
**Expected Inference Impact:** Minimal (<5% latency increase during transitions)

This plan prioritizes your most critical workloads while providing comprehensive validation at each stage. The extended timeline accounts for the massive scale and ensures training continuity throughout the upgrade process.
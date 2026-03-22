# GKE Mixed AI/ML Platform Upgrade Plan: 1.31 → 1.32

**Fleet Overview:** 5,000 nodes across 4 workload types  
**Current Version:** 1.31 → **Target:** 1.32  
**Priority:** Training continuity (H100) > Inference availability (A100) > Dev/Services

---

## Executive Summary

This is a **large-scale GPU cluster upgrade** requiring careful sequencing to protect multi-day training runs and maintain inference SLA. The plan uses GKE's native upgrade strategies with maintenance exclusions for training protection and autoscaled blue-green for GPU pools where capacity allows.

**Total Timeline:** 3-4 weeks  
**Key Risk:** H100 training job interruption  
**Mitigation:** Dedicated training protection with maintenance exclusions

---

## Phase 1: Foundation (Week 1)
*Upgrade non-GPU infrastructure with minimal business impact*

### Phase 1A: Control Plane Upgrades
- **Target:** All cluster control planes
- **Strategy:** Sequential, 24-hour soak between clusters
- **Maintenance Window:** Weekends, 2 AM - 6 AM PST

```bash
# Per cluster
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.latest
```

### Phase 1B: CPU Service Nodes (1,000 nodes)
- **Target:** General services, monitoring, logging
- **Strategy:** Surge upgrade with high parallelism
- **Settings:** `maxSurge=10, maxUnavailable=0`
- **Timeline:** 2-3 days

```bash
gcloud container node-pools update cpu-services \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 10 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade cpu-services \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**Phase 1 Success Criteria:**
- [ ] All control planes at 1.32
- [ ] CPU services healthy and serving
- [ ] No impact on GPU workloads

---

## Phase 2: Development Environment (Week 2)
*Validate GPU upgrade process with T4 dev nodes*

### Phase 2: T4 Development Nodes (500 nodes)
- **Purpose:** GPU upgrade validation and driver testing
- **Strategy:** Surge with moderate parallelism
- **Settings:** `maxSurge=0, maxUnavailable=2` (assumes limited T4 surge capacity)

```bash
# Test GPU driver compatibility first
gcloud container node-pools update t4-dev \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2

gcloud container node-pools upgrade t4-dev \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**Critical Validation:**
- [ ] GPU driver version compatibility (GKE auto-installs drivers for 1.32)
- [ ] CUDA toolkit compatibility with ML frameworks
- [ ] PyTorch/TensorFlow container compatibility
- [ ] Development workflows functional

**If T4 validation fails:** STOP. Debug driver/framework issues before proceeding to production GPU pools.

---

## Phase 3: Inference Infrastructure (Week 3)
*Upgrade A100 inference with availability protection*

### Phase 3: A100 Inference Nodes (1,500 nodes)
- **Business Impact:** Customer-facing inference APIs
- **Strategy:** Autoscaled blue-green upgrade (maintains serving capacity)
- **Requires:** 2x A100 capacity temporarily OR rolling drain approach

**Option A: Autoscaled Blue-Green (if A100 capacity available)**
```bash
gcloud container node-pools update a100-inference \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaled-blue-green-upgrade

gcloud container node-pools upgrade a100-inference \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**Option B: Conservative Rolling (if capacity constrained)**
```bash
gcloud container node-pools update a100-inference \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1

gcloud container node-pools upgrade a100-inference \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**Monitoring During A100 Upgrade:**
- Inference latency (p95 < SLA threshold)
- Error rates (< 0.1% spike allowed)
- GPU utilization on remaining nodes
- Customer-facing API health checks

---

## Phase 4: Training Infrastructure (Week 4)
*H100 training nodes with maximum protection*

### Phase 4: H100 Training Nodes (2,000 nodes)
- **Business Impact:** Multi-day/week training campaigns
- **Strategy:** Maintenance exclusion + coordinated checkpoint approach
- **Critical:** No mid-training interruptions

**Step 1: Apply Training Protection**
```bash
# Block all upgrades during active training
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+7 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

**Step 2: Coordinate with Training Teams**
- Identify active training jobs and estimated completion
- Plan checkpoint saves before upgrade window
- Schedule upgrade during natural training gaps

**Step 3: Execute H100 Upgrade (during training downtime)**
```bash
# Remove exclusion when ready
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion "training-protection"

# Upgrade with minimal disruption settings
gcloud container node-pools update h100-training \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1

gcloud container node-pools upgrade h100-training \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**H100 Upgrade Duration:** ~10-14 days for 2,000 nodes at 1 node per batch

---

## GPU-Specific Considerations

### Driver Version Impact
GKE 1.32 will auto-install updated GPU drivers. **Critical validation needed:**

```bash
# Check current driver version
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.nodeInfo.kubeletVersion}{"\t"}{.metadata.labels.cloud\.google\.com/gke-accelerator}{"\n"}{end}'

# After upgrade, verify CUDA compatibility
kubectl run gpu-test --image=nvidia/cuda:12.0-runtime-ubuntu20.04 \
  --rm -it --restart=Never \
  --limits nvidia.com/gpu=1 \
  -- nvidia-smi
```

### Reservation and Quota Interaction
- **H100/A100 reservations:** Surge upgrades consume reservation slots
- **Recommendation:** Use `maxUnavailable` strategy for GPU pools to avoid reservation conflicts
- **Capacity planning:** Verify sufficient unused quota for surge nodes if using `maxSurge`

### RDMA and GPUDirect Networking
If using high-performance GPU interconnect:
- **Compact placement policies:** Verify replacement nodes land in same placement group
- **GPUDirect-TCPX:** GKE 1.32 maintains compatibility (requires 1.27.7-gke.1121000+)
- **Multi-NIC configurations:** Test network topology preservation post-upgrade

---

## Monitoring and Alerting

### Phase-Specific Metrics

**CPU Services (Phase 1):**
- API server latency
- Ingress controller availability
- Monitoring pipeline health

**T4 Development (Phase 2):**
- Jupyter notebook startup times
- Model training job success rate
- GPU driver initialization errors

**A100 Inference (Phase 3):**
- Inference API latency (p50, p95, p99)
- Model serving error rates
- GPU memory utilization
- Customer-facing SLA compliance

**H100 Training (Phase 4):**
- Training job checkpoint frequency
- GPU interconnect (RDMA) performance
- Multi-node training synchronization
- CUDA memory allocation failures

### Early Warning Indicators
```bash
# Monitor upgrade progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep -E "(Ready|NotReady|SchedulingDisabled)"'

# GPU-specific health checks
kubectl get pods -A -o jsonpath='{range .items[?(@.spec.containers[*].resources.limits.nvidia\.com/gpu)]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.status.phase}{"\n"}{end}' | grep -v Running

# Check for GPU driver issues
kubectl get events -A --field-selector reason=FailedMount | grep nvidia
```

---

## Rollback Strategy

### Immediate Response (if upgrade causes issues)
1. **Training Jobs:** Checkpoint immediately, cordon affected nodes
2. **Inference:** Shift traffic to non-upgraded pools
3. **Cancel in-progress upgrade:**
```bash
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE
# Stop current upgrade operation if needed
```

### Node Pool Recreation (if necessary)
```bash
# Create new pool at previous version
gcloud container node-pools create NODEPOOL-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.previous \
  --accelerator type=nvidia-h100-80gb,count=8 \
  --num-nodes 100

# Migrate workloads and delete failed pool
kubectl cordon -l cloud.google.com/gke-nodepool=ORIGINAL_POOL
```

---

## Success Criteria and Sign-Off

### Phase Completion Requirements

**Phase 1 (Foundation):** ✅
- [ ] All control planes upgraded to 1.32
- [ ] CPU services fully operational
- [ ] Monitoring/logging pipelines healthy
- [ ] No GPU workload impact

**Phase 2 (T4 Dev):** ✅
- [ ] GPU driver compatibility confirmed
- [ ] CUDA/framework integration validated
- [ ] Development workflows functional
- [ ] Performance benchmarks within 5% of baseline

**Phase 3 (A100 Inference):** ✅
- [ ] Inference APIs meeting SLA (p95 latency)
- [ ] Error rates < 0.1% spike
- [ ] Customer impact < 5 minutes total
- [ ] GPU utilization patterns normal

**Phase 4 (H100 Training):** ✅
- [ ] All training nodes upgraded
- [ ] Multi-node training synchronization verified
- [ ] GPU interconnect performance validated
- [ ] Training jobs resumed successfully post-upgrade

### Fleet-Wide Validation
```bash
# Final cluster health check
gcloud container clusters describe CLUSTER_NAME --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].version, status)"

# Comprehensive workload health
kubectl get pods -A | grep -E "(CrashLoop|Error|Pending)" | wc -l
# Should return 0

# GPU resources available
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.allocatable.nvidia\.com/gpu}{"\n"}{end}' | grep -v "<none>" | awk '{sum += $2} END {print "Total GPUs:", sum}'
```

---

## Risk Mitigation Summary

| Risk | Impact | Mitigation |
|------|--------|------------|
| Training job interruption | Very High | Maintenance exclusions + checkpoint coordination |
| Inference downtime | High | Autoscaled blue-green OR conservative rolling |
| Driver incompatibility | High | T4 validation phase + rollback plan |
| Capacity exhaustion | Medium | `maxUnavailable` strategy for GPU pools |
| Upgrade duration (2k H100 nodes) | Medium | Extended timeline (10-14 days) + staged approach |

**Timeline flexibility:** Build in 1-2 week buffer for Phase 4 (H100) based on training campaign schedules.
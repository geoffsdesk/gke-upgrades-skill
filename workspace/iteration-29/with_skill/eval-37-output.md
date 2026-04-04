# GKE AI/ML Fleet Upgrade Plan: 1.31 → 1.32

## Executive Summary

5,000-node mixed AI/ML cluster upgrade with training continuity as the primary constraint. This plan sequences upgrades to minimize disruption to revenue-generating workloads while maintaining inference SLAs.

**Key Strategy:**
- **Training-first sequencing:** Upgrade during planned training gaps to avoid mid-job eviction
- **Inference blue-green:** Use autoscaled blue-green for inference pools to maintain serving capacity
- **Development as canary:** T4 dev nodes validate the upgrade path before production
- **CPU services last:** Stateless services are most tolerant of disruption

---

## Environment Assessment

- **Current:** GKE 1.31 | **Target:** GKE 1.32
- **Cluster Mode:** Standard (assumption - large GPU clusters typically use Standard)
- **Release Channel:** Regular (assumption - production AI workloads need stability)
- **GPU Reservations:** Assumed fixed with minimal surge capacity
- **Training Jobs:** Multi-day/week runs requiring checkpoint protection

---

## Phase Structure

### Phase 0: Pre-Upgrade Foundation (Week -2)

**Critical prep work before any node upgrades begin.**

```bash
# 1. Control plane upgrade (regional - maintains API availability)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.latest

# 2. Apply training protection exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# 3. Validate control plane health
kubectl get pods -n kube-system
kubectl get nodes # All should remain Ready
```

**GPU Driver Compatibility Validation:**
- Deploy test workloads on a single T4 dev node with 1.32 to validate CUDA compatibility
- Confirm inference model loading and training checkpoint compatibility
- Verify PyTorch/TensorFlow/JAX compatibility with new node image

**Training Campaign Coordination:**
- Identify active multi-day training runs and their expected completion dates
- Schedule upgrade phases during planned training gaps (typically weekends/maintenance windows)
- Ensure all training jobs have recent checkpoints and can resume post-upgrade

---

### Phase 1: Development Validation (Week 1 - Canary)

**T4 development nodes as upgrade canary** - 500 nodes, lowest risk workload.

```bash
# Configure aggressive upgrade settings for dev (faster validation)
gcloud container node-pools update t4-dev-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 10
  # 10 nodes at once - dev workloads can tolerate higher disruption

# Execute upgrade
gcloud container node-pools upgrade t4-dev-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**Validation Checklist:**
- [ ] All T4 nodes reach Ready state within 2 hours
- [ ] Development inference workloads start successfully 
- [ ] Jupyter notebooks and training experiments run normally
- [ ] GPU driver version and CUDA compatibility confirmed
- [ ] No unexpected pod evictions or scheduling issues

**Success Criteria:** 48-hour soak period with no GPU-related issues before proceeding to Phase 2.

---

### Phase 2: CPU Services (Week 2)

**CPU service nodes** - 1,000 nodes, stateless workloads with fastest recovery.

**Strategy:** Aggressive surge upgrade - services are stateless and can tolerate brief interruptions.

```bash
# Configure for speed - stateless services tolerate higher churn
gcloud container node-pools update cpu-services-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 50 \
  --max-unavailable-upgrade 0
  # 50 surge nodes (~5% of pool size, within GKE's ~20 node parallelism limit)

gcloud container node-pools upgrade cpu-services-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**Expected Duration:** 4-6 hours (1,000 nodes ÷ 20 nodes/batch = 50 batches)

**Monitoring:**
```bash
# Track service health during upgrade
kubectl get svc -A
kubectl get pods -A -l tier=service | grep -v Running
watch 'kubectl get nodes -l nodepool=cpu-services -o wide'
```

---

### Phase 3: Inference Fleet (Week 3-4) - **CRITICAL**

**A100 inference nodes** - 1,500 nodes, revenue-critical with SLA requirements.

**Strategy:** Autoscaled blue-green to maintain serving capacity throughout upgrade.

```bash
# Enable autoscaling (required for autoscaled blue-green)
gcloud container node-pools update a100-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 1400 \
  --total-max-nodes 1600

# Configure autoscaled blue-green upgrade
gcloud container node-pools update a100-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

# Execute upgrade
gcloud container node-pools upgrade a100-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**Critical Monitoring:**
- **Inference latency:** P95 should remain < baseline + 20%
- **Throughput:** QPS should not drop below 80% of baseline during transition
- **Model availability:** No inference endpoints should return 5xx errors
- **Cost impact:** Autoscaling will temporarily increase costs during transition

**Rollback Plan:** 
- Green pool scales up while blue pool serves traffic
- If latency degrades, cancel upgrade and drain green pool
- Blue pool remains available for immediate rollback

**Expected Duration:** 2-3 days with gradual blue→green transition

---

### Phase 4: Training Infrastructure (Week 5-6) - **HIGHEST COORDINATION**

**H100 training nodes** - 2,000 nodes, most disruptive but protected by training gaps.

**Pre-Phase Requirements:**
- [ ] All active training jobs completed or checkpointed
- [ ] No new training jobs submitted (coordination with ML teams)
- [ ] 48-hour training freeze window confirmed
- [ ] Backup checkpoints verified and accessible

**Strategy:** Drain-first upgrade to avoid GPU surge quota issues.

```bash
# Remove training protection exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion "training-protection"

# Configure for GPU constraints (fixed reservation, no surge capacity)
gcloud container node-pools update h100-training-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4
  # 4 nodes at once - balance between speed and training restart risk

# Cordon entire training pool first
kubectl cordon -l cloud.google.com/gke-nodepool=h100-training-pool

# Wait for graceful training job completion (24-48h window)
# Monitor: kubectl get pods -A -l workload=training

# Execute upgrade once training pool is drained
gcloud container node-pools upgrade h100-training-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**Training Restart Coordination:**
```bash
# Verify all H100 nodes ready before resuming training
kubectl get nodes -l nodepool=h100-training | grep Ready | wc -l
# Should equal 2,000

# Test training job on 1 node first
kubectl run training-test --image=training-image --restart=Never --overrides='{
  "spec": {
    "containers": [{
      "name": "training-test",
      "image": "training-image",
      "resources": {"limits": {"nvidia.com/gpu": 8}},
      "nodeSelector": {"cloud.google.com/gke-nodepool": "h100-training-pool"}
    }]
  }
}'

# Resume full training pipeline only after successful test
```

**Expected Duration:** 5-7 days including coordination windows

---

## Monitoring & Validation

### Real-time Monitoring Dashboard

```bash
# Node upgrade progress
watch 'echo "=== Upgrade Progress ===" && kubectl get nodes -o custom-columns="NODE:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,POOL:.metadata.labels.cloud\.google\.com/gke-nodepool" | sort -k3'

# Training workload status
kubectl get pods -A -l workload=training -o custom-columns="NAME:.metadata.name,STATUS:.status.phase,NODE:.spec.nodeName"

# Inference latency check
kubectl exec -it monitoring-pod -- curl -w "%{time_total}" inference-service.default.svc.cluster.local/health
```

### Success Metrics

| Phase | Key Metric | Success Threshold |
|-------|------------|------------------|
| Dev (T4) | Pod restart success rate | >95% |
| CPU Services | Service availability | >99.5% |
| Inference (A100) | P95 latency increase | <20% during transition |
| Training (H100) | Job restart success | 100% (zero tolerance) |

### Alerting Rules

```yaml
# Training job disruption alert
- alert: TrainingJobEvicted
  expr: increase(kube_pod_container_status_terminated_reason{reason="Evicted",container=~"training.*"}[5m]) > 0
  labels:
    severity: critical
  annotations:
    description: "Training job evicted during upgrade - immediate intervention required"

# Inference latency degradation
- alert: InferenceLatencyHigh
  expr: histogram_quantile(0.95, inference_latency_seconds) > 1.2 * baseline_latency
  for: 5m
  labels:
    severity: warning
  annotations:
    description: "Inference P95 latency 20% above baseline during A100 upgrade"
```

---

## Risk Mitigation

### High-Risk Scenarios & Contingencies

**1. Training Job Mid-Upgrade Eviction**
- **Detection:** Monitor Cloud Logging for PDB violations on training workloads
- **Mitigation:** Immediately apply "no upgrades" exclusion, allow job to complete
- **Prevention:** Coordinate with ML teams on training schedules

**2. Inference SLA Breach During A100 Upgrade**
- **Detection:** P95 latency >baseline + 50% or availability <99%
- **Mitigation:** Cancel autoscaled blue-green, keep blue pool serving
- **Prevention:** Load test green pool before traffic migration

**3. GPU Driver Incompatibility**
- **Detection:** CUDA errors, model loading failures in Phase 1
- **Mitigation:** Rollback T4 pool, escalate to GKE support
- **Prevention:** Staging validation with identical workloads

**4. Quota Exhaustion During Autoscaled Blue-Green**
- **Detection:** Green pool nodes stuck in Pending state
- **Mitigation:** Temporarily scale down non-critical workloads
- **Prevention:** Verify A100 reservation has 10-20% headroom

---

## Communications Plan

### Stakeholder Notifications

**Week -2 (Planning):**
- ML Engineering: Training schedule coordination
- Platform SRE: Monitoring and alerting setup
- Business: Potential inference latency impact during Week 3-4

**Phase Start Notifications:**
- Slack alerts to #ml-platform and #sre channels
- Email to stakeholders with upgrade status and expected duration
- Dashboard links for real-time monitoring

**Issue Escalation:**
- Severity 1: Training job eviction → Immediate ML eng + on-call
- Severity 2: Inference SLA breach → Platform lead + business stakeholders
- Severity 3: Upgrade delays → Daily email updates

---

## Rollback Strategy

### Per-Phase Rollback Plans

**Development (T4):** Simple rollback - create new pool at 1.31, migrate dev workloads
**CPU Services:** Rollback via new pool creation - stateless services migrate easily  
**Inference (A100):** Blue-green advantage - uncordon blue pool, drain green pool
**Training (H100):** **No rollback during active training** - only between training campaigns

### Emergency Rollback Commands

```bash
# Create rollback node pool (use for T4, CPU services)
gcloud container node-pools create POOL_NAME-rollback-1-31 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.previous \
  --machine-type MACHINE_TYPE \
  --num-nodes TARGET_SIZE

# Blue-green rollback (inference pools only)
# Uncordon blue pool, drain green pool
kubectl uncordon -l cloud.google.com/gke-nodepool=a100-inference-pool-blue
```

---

## Timeline Summary

| Week | Phase | Nodes | Downtime Risk | Key Activities |
|------|-------|-------|---------------|----------------|
| -2 | Prep | 0 | None | CP upgrade, staging validation |
| 1 | Dev | 500 T4 | Low | Canary validation |
| 2 | Services | 1,000 CPU | Medium | Surge upgrade |
| 3-4 | Inference | 1,500 A100 | **High** | Blue-green, SLA monitoring |
| 5-6 | Training | 2,000 H100 | **Critical** | Coordinated training gaps |

**Total Duration:** 6 weeks with built-in coordination windows
**Point of No Return:** Week 5 (H100 training upgrade)
**Business Impact Window:** Week 3-4 (potential inference latency)

---

This phased approach prioritizes your revenue-generating workloads while using development nodes as a validation path. The training-first sequencing ensures minimal disruption to your most expensive computational resources.
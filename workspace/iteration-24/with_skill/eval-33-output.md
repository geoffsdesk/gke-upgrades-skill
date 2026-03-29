# GKE ML Platform Upgrade Plan: 1.31 → 1.32

## Executive Summary

**Recommended Strategy**: Autoscaled blue-green upgrades for both GPU pools to minimize inference latency spikes. L4 inference pool upgraded first (lower risk), then A100 pool during a fine-tuning gap.

**Key Considerations**:
- GPU VMs don't support live migration — every upgrade requires pod restart
- Surge upgrades cause immediate inference downtime during drain
- Autoscaled blue-green keeps old pool serving while new pool warms up
- Fine-tuning jobs (4-8h) need protection from force-eviction

---

## Environment Assessment

- **Cluster**: GKE Standard
- **Current version**: 1.31 → **Target**: 1.32
- **Node pools**: 
  - L4 inference pool: 200 nodes (auto-scaling)
  - A100 mixed pool: 100 nodes (inference + 4-8h fine-tuning)
- **Workload sensitivity**: Inference latency-critical, fine-tuning interruption-sensitive

---

## Upgrade Strategy

### Phase 1: Control Plane Upgrade
**Timing**: During low-traffic period (regional cluster maintains availability)
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version 1.32.0-gke.LATEST
```

### Phase 2: L4 Inference Pool (Lower Risk First)
**Strategy**: Autoscaled blue-green
**Rationale**: Keeps old pool serving while new pool provisions and warms up

```bash
gcloud container node-pools update l4-inference-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --enable-autoscaling \
  --total-min-nodes 0 --total-max-nodes 400 \
  --strategy BLUE_GREEN \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.20,blue-green-full-batch-timeout=3600s
```

**Configuration details**:
- Initial green pool: 20% of current traffic demand (40 nodes initially)
- Green pool auto-scales up based on incoming inference requests  
- Blue pool scales down as traffic shifts to green
- 1-hour timeout for green pool readiness

### Phase 3: A100 Mixed Pool (Fine-tuning + Inference)
**Strategy**: Autoscaled blue-green during fine-tuning gap
**Critical timing**: Schedule during period when no 4-8h jobs are running

**Pre-upgrade steps**:
```bash
# 1. Pause new fine-tuning job submissions
# 2. Wait for current jobs to complete (check every 30 minutes)
kubectl get pods -l workload-type=fine-tuning -o wide

# 3. Verify no long-running jobs active
kubectl get pods -l workload-type=fine-tuning --field-selector=status.phase=Running
```

**Upgrade execution**:
```bash
gcloud container node-pools update a100-mixed-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --enable-autoscaling \
  --total-min-nodes 0 --total-max-nodes 200 \
  --strategy BLUE_GREEN \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.15,blue-green-full-batch-timeout=3600s
```

---

## Pre-Flight Checklist

```markdown
Pre-Flight Checklist - ML Platform Upgrade

Compatibility & Versions
- [ ] GKE 1.32 available in current release channel
- [ ] GPU driver compatibility confirmed (1.32 → driver version)
- [ ] Inference framework compatibility (TensorRT, vLLM, etc.) with new CUDA version
- [ ] Fine-tuning framework compatibility verified in staging
- [ ] No deprecated API usage: `kubectl get --raw /metrics | grep deprecated`

Infrastructure Readiness  
- [ ] L4 autoscaling limits appropriate: min=0, max=400
- [ ] A100 autoscaling limits appropriate: min=0, max=200
- [ ] GPU reservations checked for available capacity during blue-green
- [ ] Cluster autoscaler settings reviewed (won't interfere with blue-green)

Workload Protection
- [ ] PDBs configured for inference services (not overly restrictive)
- [ ] Fine-tuning jobs have checkpointing enabled
- [ ] Inference health checks and readiness probes configured
- [ ] Load balancer health check thresholds appropriate for pool transition

Operational Readiness
- [ ] Staging cluster upgraded and tested with representative workloads
- [ ] Monitoring baselines captured (inference latency p99, throughput)
- [ ] Fine-tuning job schedule reviewed - upgrade window identified
- [ ] On-call team available during upgrade
- [ ] Rollback plan documented
```

---

## Maintenance Window Configuration

```bash
# Set upgrade window during lowest inference traffic
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-window-start "2024-01-15T03:00:00Z" \
  --maintenance-window-duration 6h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"

# Optional: Add fine-tuning job protection exclusion
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "protect-training-jobs" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

---

## Step-by-Step Runbook

### Phase 1: Control Plane (15-20 minutes)
```bash
# Upgrade control plane
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version 1.32.0-gke.LATEST

# Verify
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="value(currentMasterVersion)"

kubectl get pods -n kube-system | grep -v Running
```

### Phase 2: L4 Inference Pool (60-90 minutes)
```bash
# Configure autoscaled blue-green
gcloud container node-pools update l4-inference-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --strategy BLUE_GREEN \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.20,blue-green-full-batch-timeout=3600s

# Trigger upgrade
gcloud container node-pools upgrade l4-inference-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.32.0-gke.LATEST

# Monitor progress
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=l4-inference-pool -o wide'

# Check inference latency during transition
# Monitor your inference service metrics dashboard
```

### Phase 3: A100 Mixed Pool (90-120 minutes)
```bash
# Ensure no fine-tuning jobs running
kubectl get pods -l workload-type=fine-tuning --field-selector=status.phase=Running

# Configure and upgrade
gcloud container node-pools update a100-mixed-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --strategy BLUE_GREEN \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.15,blue-green-full-batch-timeout=3600s

gcloud container node-pools upgrade a100-mixed-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.32.0-gke.LATEST

# Monitor both inference and prepare for fine-tuning resume
```

---

## Monitoring & Validation

**During Upgrade**:
```bash
# Node transition progress
kubectl get nodes -o custom-columns="NAME:.metadata.name,POOL:.metadata.labels.cloud\.google\.com/gke-nodepool,VERSION:.status.nodeInfo.kubeletVersion,STATUS:.status.conditions[?(@.type=='Ready')].status"

# Pod health
kubectl get pods -A | grep -E "Pending|Terminating|CrashLoop"

# GPU availability
kubectl get nodes -o json | jq -r '.items[] | select(.status.allocatable."nvidia.com/gpu") | "\(.metadata.name): \(.status.allocatable."nvidia.com/gpu")"'
```

**Post-Upgrade Validation**:
```bash
# All nodes at 1.32
gcloud container node-pools list --cluster CLUSTER_NAME --region REGION

# Inference service health
kubectl get deployments -l workload-type=inference
kubectl get pods -l workload-type=inference -o wide

# GPU driver version
kubectl get nodes -o jsonpath='{.items[*].status.nodeInfo.kubeletVersion}' | grep 1.32
```

---

## Troubleshooting Guide

### Issue: Green pool nodes not provisioning (GPU capacity)
**Symptom**: Blue-green upgrade stalls, green pool stuck at 0 nodes
**Diagnosis**: 
```bash
kubectl get events -A --field-selector reason=FailedScheduling
gcloud compute zones describe ZONE --format="yaml(availableCpuPlatforms)"
```
**Fix**: Check GPU quota and reservations. Consider upgrading during lower-demand period.

### Issue: Inference pods not moving to green pool
**Symptom**: New nodes ready but pods stay on blue pool
**Diagnosis**:
```bash
kubectl describe pods -l workload-type=inference | grep Events -A 10
kubectl get pods -l workload-type=inference -o wide
```
**Fix**: Check node affinity, taints, and resource requests. Verify HPA scaling to green pool.

### Issue: Fine-tuning job interrupted during A100 upgrade
**Symptom**: 4-8h jobs terminated during blue-green transition
**Fix**: 
```bash
# Jobs should have checkpointing - verify resume capability
kubectl get pods -l workload-type=fine-tuning -o yaml | grep checkpoint

# If no checkpointing, restore from backup and revert upgrade timing
```

---

## Rollback Plan

**L4 Pool Rollback** (if issues detected):
```bash
# Cancel blue-green upgrade during soak period
gcloud container operations cancel OPERATION_ID --region REGION

# Manual rollback: create new pool at 1.31
gcloud container node-pools create l4-inference-pool-rollback \
  --cluster CLUSTER_NAME \
  --region REGION \
  --node-version 1.31.0-gke.PREVIOUS \
  --machine-type g2-standard-24 \
  --accelerator type=nvidia-l4,count=1 \
  --enable-autoscaling --min-nodes 0 --max-nodes 200 \
  --zones us-central1-a,us-central1-b,us-central1-c
```

---

## Success Metrics

**Upgrade Success Criteria**:
- [ ] All nodes at GKE 1.32
- [ ] Inference latency p99 within 10% of baseline
- [ ] No increase in inference error rates
- [ ] GPU utilization returns to pre-upgrade levels
- [ ] Fine-tuning job submission resumed successfully
- [ ] Autoscaling behavior normal (up/down scaling)

**Timeline**: Total upgrade window ~4-5 hours including validation.

---

## Key Recommendations

1. **Stage in non-production first**: Test this exact upgrade strategy on a staging cluster with representative inference and fine-tuning workloads
2. **GPU driver validation**: Verify TensorRT, CUDA, and ML framework compatibility with the new node image before production
3. **Coordinate with ML teams**: Ensure fine-tuning job submissions are paused during A100 pool upgrade
4. **Monitor throughout**: Watch inference latency closely during blue-green transitions - autoscaled blue-green minimizes but doesn't eliminate brief latency spikes
5. **Consider Extended channel**: For future upgrades, Extended release channel gives you more control over minor version timing while still receiving security patches

This approach prioritizes inference availability while protecting long-running fine-tuning jobs from interruption.
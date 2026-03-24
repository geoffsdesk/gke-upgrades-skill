# GKE ML Platform Upgrade Plan: 1.31 → 1.32

## Cluster Overview
- **Cluster mode:** Standard
- **Current version:** 1.31 → **Target version:** 1.32
- **GPU pools:** 200 L4 nodes (inference), 100 A100 nodes (inference + 4-8h fine-tuning)
- **Workload type:** Latency-sensitive inference + medium-duration training

## Recommended Upgrade Strategy

### GPU Pool Strategy: Autoscaled Blue-Green
For GPU inference workloads, **autoscaled blue-green** is the optimal strategy because:
- **Zero inference latency spikes** — old pool keeps serving while new pool warms up
- **Cost-efficient** — scales down blue pool as green pool takes traffic (no 2x resource cost)
- **Respects longer graceful termination** — critical for 4-8h fine-tuning jobs
- **GPU-optimized** — doesn't require surge capacity that may be unavailable

### Upgrade Sequence
1. **Control plane first** (required order)
2. **L4 pool** (inference-only, lower risk)
3. **A100 pool** (inference + training, higher value workloads)

---

## Pre-Upgrade Checklist

```markdown
Pre-Upgrade Checklist - ML Platform
- [ ] Cluster: ML_CLUSTER | Mode: Standard | Channel: ___
- [ ] Current version: 1.31 | Target version: 1.32

GPU-Specific Compatibility
- [ ] Target version 1.32 available in release channel
- [ ] GPU driver compatibility confirmed (1.32 may change CUDA version)
- [ ] **CRITICAL:** Test 1.32 + driver in staging with representative inference models
- [ ] Model loading, CUDA calls, throughput validated on 1.32
- [ ] TensorRT/inference framework compatibility verified

Workload Readiness
- [ ] PDBs configured for inference deployments (not overly restrictive)
- [ ] terminationGracePeriodSeconds ≥ 8 hours (28800s) for fine-tuning jobs
- [ ] All pods managed by Deployments/StatefulSets (no bare pods)
- [ ] Autoscaler pause plan for upgrade window
- [ ] Fine-tuning job checkpointing enabled

Infrastructure
- [ ] Autoscaled blue-green strategy selected for both GPU pools
- [ ] Node pool autoscaling enabled: `--enable-autoscaling`
- [ ] Maintenance window: off-peak hours (nights/weekends)
- [ ] Monitoring active: GPU utilization, inference latency, job completion rates
```

---

## Upgrade Runbook

### Phase 1: Control Plane Upgrade

```bash
# Apply temporary "no upgrades" exclusion to control node timing
gcloud container clusters update ML_CLUSTER \
  --zone ZONE \
  --add-maintenance-exclusion-name "planned-upgrade" \
  --add-maintenance-exclusion-start-time "2024-01-15T02:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-01-15T06:00:00Z" \
  --add-maintenance-exclusion-scope no_upgrades

# Upgrade control plane
gcloud container clusters upgrade ML_CLUSTER \
  --zone ZONE \
  --master \
  --cluster-version 1.32.X-gke.XXXX

# Verify (wait ~10-15 min)
gcloud container clusters describe ML_CLUSTER \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

### Phase 2: L4 Pool (Inference) - Autoscaled Blue-Green

```bash
# Configure autoscaled blue-green for L4 pool
gcloud container node-pools update l4-inference-pool \
  --cluster ML_CLUSTER \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 50 \
  --total-max-nodes 250 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

# Start upgrade
gcloud container node-pools upgrade l4-inference-pool \
  --cluster ML_CLUSTER \
  --zone ZONE \
  --cluster-version 1.32.X-gke.XXXX

# Monitor progress
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=l4-inference-pool -o wide'
watch 'kubectl get pods -l gpu-type=l4 -o wide'
```

**L4 upgrade phases:** Create green pool (25% initial size) → Cordon blue pool → Auto-scale green up as traffic shifts → Blue pool scales down → Complete

### Phase 3: A100 Pool (Inference + Fine-tuning) - Autoscaled Blue-Green

```bash
# BEFORE upgrading A100: pause new fine-tuning job submissions
# Let running 4-8h jobs complete naturally

# Configure autoscaled blue-green for A100 pool
gcloud container node-pools update a100-mixed-pool \
  --cluster ML_CLUSTER \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 20 \
  --total-max-nodes 120 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.30,blue-green-full-batch-timeout=7200s

# Start upgrade (respects long graceful termination for fine-tuning jobs)
gcloud container node-pools upgrade a100-mixed-pool \
  --cluster ML_CLUSTER \
  --zone ZONE \
  --cluster-version 1.32.X-gke.XXXX

# Monitor A100 upgrade (will take longer due to fine-tuning jobs)
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=a100-mixed-pool -o wide'
watch 'kubectl get pods -l gpu-type=a100 -o wide'

# Resume fine-tuning job submissions after upgrade completes
```

---

## Key Advantages of This Strategy

### Why Autoscaled Blue-Green for GPU Inference
- **Latency protection:** Old pool serves traffic while new pool warms up — zero inference downtime
- **Cost efficiency:** Scales down old pool as new pool takes load (vs 2x cost of standard blue-green)
- **GPU reservation friendly:** Doesn't require surge capacity that may be unavailable for L4/A100
- **Training job protection:** Respects 8-hour `terminationGracePeriodSeconds` for fine-tuning jobs

### Why NOT Surge for GPU Inference
- **Inference latency spikes:** Surge drains nodes immediately, causing pod restarts and latency spikes
- **GPU capacity constraints:** L4/A100 surge capacity is often unavailable
- **1-hour eviction limit:** Surge force-evicts after 1 hour — kills 4-8h fine-tuning jobs

---

## Fine-Tuning Job Protection

```bash
# Verify long graceful termination is set
kubectl get deployments -l workload-type=fine-tuning -o json | \
  jq '.items[].spec.template.spec.terminationGracePeriodSeconds'

# Should show 28800 (8 hours) or longer

# Configure PDB for training jobs
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: fine-tuning-pdb
spec:
  minAvailable: 1
  selector:
    matchLabels:
      workload-type: fine-tuning
```

---

## Monitoring During Upgrade

```bash
# GPU node status
kubectl get nodes -l accelerator=nvidia-l4 -o wide
kubectl get nodes -l accelerator=nvidia-tesla-a100 -o wide

# Inference pod health
kubectl get pods -l workload-type=inference -o wide

# Fine-tuning job status
kubectl get pods -l workload-type=fine-tuning -o wide

# GPU utilization
kubectl top nodes --selector=accelerator=nvidia-l4
kubectl top nodes --selector=accelerator=nvidia-tesla-a100
```

---

## Post-Upgrade Validation

```markdown
Post-Upgrade Checklist - ML Platform
- [ ] All nodes at 1.32: `kubectl get nodes -o wide`
- [ ] GPU driver version confirmed: `kubectl describe nodes | grep nvidia`
- [ ] Inference latency within baseline (p95/p99)
- [ ] Model loading successful on new nodes
- [ ] Autoscaler responding to traffic
- [ ] Fine-tuning job checkpoints working
- [ ] No GPU memory leaks or CUDA errors
- [ ] Remove temporary maintenance exclusions
```

---

## Expected Timeline

- **Control plane:** 10-15 minutes
- **L4 pool (200 nodes):** 2-3 hours with autoscaled blue-green
- **A100 pool (100 nodes):** 3-4 hours (longer due to fine-tuning job graceful termination)
- **Total:** 5-7 hours end-to-end

Schedule during your lowest-traffic period. The autoscaled blue-green strategy ensures inference availability throughout the upgrade.
# GKE Upgrade Plan: ML Inference Platform (1.31 → 1.32)

## Environment Summary
- **Cluster:** Standard GKE, GPU inference + fine-tuning workloads
- **Current version:** 1.31 → **Target:** 1.32
- **Node pools:** 200 L4 nodes (inference), 100 A100 nodes (inference + fine-tuning)
- **Key constraints:** Minimize inference latency impact, protect 4-8h fine-tuning jobs

## Recommended Upgrade Strategy

### Control Plane: Two-step upgrade (1.31 → 1.32)
Use GKE's rollback-safe two-step control plane upgrade:
- **Step 1:** Binary upgrade with 24h soak period for validation
- **Step 2:** Enable 1.32 APIs after confirming stability
- **Advantage:** Can rollback to 1.31 during soak period if issues arise

### Node Pools: Autoscaled Blue-Green
**Why autoscaled blue-green for GPU inference:**
- Keeps old nodes serving while new nodes warm up → **zero inference downtime**
- GPU VMs don't support live migration, so surge upgrades cause pod restarts and latency spikes
- More cost-efficient than standard blue-green (scales down old pool as new pool scales up)
- Respects longer graceful termination periods for fine-tuning jobs

## Pre-Upgrade Checklist

```markdown
Pre-Upgrade Checklist: ML Platform 1.31 → 1.32
- [ ] Cluster: ML-PLATFORM | Mode: Standard | Channel: ___
- [ ] Current version: 1.31 | Target version: 1.32

GPU-Specific Compatibility
- [ ] CUDA/driver compatibility confirmed with GKE 1.32 node image
- [ ] GPU inference models tested on 1.32 staging cluster
- [ ] Fine-tuning framework compatibility verified (TensorFlow/PyTorch versions)
- [ ] GPU reservation headroom checked: `gcloud compute reservations describe RESERVATION --zone ZONE`
- [ ] Inference serving latency baseline captured (p50/p95/p99)

Workload Readiness
- [ ] PDBs configured for inference deployments (recommend minAvailable: 80% for L4, 70% for A100)
- [ ] Fine-tuning jobs have checkpointing enabled
- [ ] terminationGracePeriodSeconds ≥ 600s for fine-tuning pods
- [ ] Resource requests/limits set on all GPU containers
- [ ] HPA/autoscaler settings documented for rollback

Infrastructure
- [ ] Autoscaling enabled on both GPU pools with sufficient max limits
- [ ] Maintenance window: weekday 2-6 AM PST (low inference traffic)
- [ ] Node pool upgrade order: L4 first (lower risk), then A100
- [ ] Fine-tuning campaign schedule checked - defer if multi-day jobs in progress
```

## Step-by-Step Runbook

### Phase 1: Control Plane Upgrade (Two-step)

```bash
# Step 1: Binary upgrade with soak period
gcloud beta container clusters upgrade ML-PLATFORM-CLUSTER \
  --zone ZONE \
  --master \
  --cluster-version 1.32.X-gke.Y \
  --control-plane-soak-duration 86400s

# Validate control plane health (24h soak period)
kubectl get pods -n kube-system
kubectl get --raw /healthz
# Run inference load tests to validate API stability

# Step 2: Complete upgrade after validation
gcloud beta container clusters upgrade ML-PLATFORM-CLUSTER \
  --zone ZONE \
  --master \
  --complete-control-plane-upgrade
```

### Phase 2: L4 Inference Pool (Lower Risk First)

```bash
# Configure autoscaled blue-green
gcloud container node-pools update l4-inference-pool \
  --cluster ML-PLATFORM-CLUSTER \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 50 --total-max-nodes 300 \
  --strategy AUTOSCALED_BLUE_GREEN \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

# Start upgrade
gcloud container node-pools upgrade l4-inference-pool \
  --cluster ML-PLATFORM-CLUSTER \
  --zone ZONE \
  --cluster-version 1.32.X-gke.Y

# Monitor during upgrade
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=l4-inference-pool -o wide'
kubectl top nodes | grep l4
# Watch inference latency metrics in monitoring dashboard
```

### Phase 3: A100 Mixed Pool (After L4 Success)

```bash
# Check for active fine-tuning jobs
kubectl get pods -l workload-type=fine-tuning -o wide
# If 4-8h jobs running, wait for completion or apply maintenance exclusion

# Configure autoscaled blue-green for A100
gcloud container node-pools update a100-mixed-pool \
  --cluster ML-PLATFORM-CLUSTER \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 25 --total-max-nodes 150 \
  --strategy AUTOSCALED_BLUE_GREEN \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.20,blue-green-full-batch-timeout=7200s

# Start upgrade
gcloud container node-pools upgrade a100-mixed-pool \
  --cluster ML-PLATFORM-CLUSTER \
  --zone ZONE \
  --cluster-version 1.32.X-gke.Y
```

## Fine-Tuning Job Protection

Since fine-tuning jobs run 4-8 hours, standard surge upgrades would force-evict them after 1 hour:

### Option A: Maintenance Exclusion (Recommended)
```bash
# Block node upgrades during active fine-tuning campaign
gcloud container clusters update ML-PLATFORM-CLUSTER \
  --zone ZONE \
  --add-maintenance-exclusion-name "fine-tuning-campaign" \
  --add-maintenance-exclusion-start-time "2024-XX-XXTHH:MM:SSZ" \
  --add-maintenance-exclusion-end-time "2024-XX-XXTHH:MM:SSZ" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

### Option B: Graceful Job Handling
```bash
# Extended termination grace period for fine-tuning pods
# In your fine-tuning pod spec:
spec:
  terminationGracePeriodSeconds: 28800  # 8 hours
  containers:
  - name: fine-tuning
    # Ensure checkpointing on SIGTERM
```

## Monitoring During Upgrade

### Critical Metrics to Watch
```bash
# Inference latency (should remain stable during blue-green)
kubectl top pods -l app=inference-server
# GPU utilization
kubectl get --raw /api/v1/nodes/NODE_NAME/proxy/stats/summary | jq '.node.runtime.imageFs'
# Fine-tuning job status
kubectl get pods -l workload-type=fine-tuning --field-selector=status.phase=Running
```

### Expected Upgrade Timeline
- **Control plane:** 15-20 minutes per step (30-40 min total + soak time)
- **L4 pool (200 nodes):** 2-3 hours with autoscaled blue-green
- **A100 pool (100 nodes):** 1.5-2 hours with autoscaled blue-green
- **Total window:** 4-6 hours (plan 8h maintenance window)

## Rollback Plan

### Control Plane Rollback (During Soak Period)
```bash
# Only possible during 24h soak period of two-step upgrade
gcloud beta container clusters upgrade ML-PLATFORM-CLUSTER \
  --zone ZONE \
  --master \
  --rollback-control-plane-upgrade
```

### Node Pool Rollback
```bash
# Create new pool at 1.31 and migrate workloads
gcloud container node-pools create l4-inference-rollback \
  --cluster ML-PLATFORM-CLUSTER \
  --zone ZONE \
  --cluster-version 1.31.X-gke.Y \
  --accelerator type=nvidia-l4,count=1 \
  --machine-type g2-standard-4 \
  --enable-autoscaling \
  --min-nodes 50 --max-nodes 300
```

## Post-Upgrade Validation

```markdown
Post-Upgrade Validation: ML Platform
- [ ] Control plane version: `gcloud container clusters describe ML-PLATFORM-CLUSTER --zone ZONE --format="value(currentMasterVersion)"`
- [ ] All GPU nodes at 1.32: `kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion`
- [ ] GPU device plugins healthy: `kubectl get pods -n kube-system -l name=nvidia-device-plugin-daemonset`
- [ ] Inference endpoints responding with normal latency
- [ ] HPA scaling behavior normal
- [ ] Fine-tuning job submission/execution working
- [ ] GPU utilization metrics flowing to monitoring
- [ ] No CrashLoopBackOff pods: `kubectl get pods -A | grep -v Running | grep -v Completed`
```

## Why This Strategy Works for ML Workloads

1. **Zero inference downtime:** Autoscaled blue-green keeps old nodes serving while new nodes provision
2. **Cost-efficient:** Old pool scales down as new pool scales up (unlike standard blue-green's 2x cost)
3. **Respects long jobs:** Fine-tuning jobs get extended graceful termination periods
4. **GPU-optimized:** Works with fixed GPU reservations, no surge capacity needed
5. **Risk mitigation:** Two-step CP upgrade allows rollback, L4-first reduces blast radius

**Estimated total downtime:** 0 minutes for inference, brief restart for fine-tuning jobs during their pool upgrade.
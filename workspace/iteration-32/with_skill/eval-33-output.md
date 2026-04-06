# GKE GPU Inference Cluster Upgrade Plan
**1.31 → 1.32 | Standard cluster | ML inference + fine-tuning**

## Executive Summary

For your GPU inference workloads, **autoscaled blue-green** is the optimal strategy. It avoids the inference latency spikes caused by surge drain-and-restart while providing controlled capacity scaling. For the A100 fine-tuning pool, we'll use **maintenance exclusions** to block upgrades during active training periods.

## Cluster Assessment

- **Cluster mode:** Standard (confirmed)
- **Current → Target:** 1.31 → 1.32 (single minor jump)
- **GPU pools:** L4 (inference) + A100 (inference + fine-tuning)
- **Key constraint:** GPU VMs don't support live migration — every upgrade requires pod restart

## Recommended Strategy

### L4 Inference Pool (200 nodes) — Autoscaled Blue-Green
**Why this strategy:**
- Avoids inference downtime — old pool serves while new pool warms up
- Cost-efficient scaling — blue pool scales down as green scales up
- Handles traffic-based autoscaling during upgrade

**Configuration:**
```bash
# Configure autoscaled blue-green for L4 pool
gcloud container node-pools update l4-inference-pool \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --enable-autoscaling \
    --total-min-nodes 50 --total-max-nodes 250 \
    --strategy AUTOSCALED_BLUE_GREEN \
    --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

### A100 Mixed Pool (100 nodes) — Surge with Fine-tuning Protection
**Maintenance exclusion approach:**
```bash
# Block node upgrades during fine-tuning campaigns
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "a100-training-protection" \
    --add-maintenance-exclusion-start-time YYYY-MM-DDTHH:MM:SSZ \
    --add-maintenance-exclusion-end-time YYYY-MM-DDTHH:MM:SSZ \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

**When fine-tuning gaps allow, use conservative surge:**
```bash
# Conservative settings for mixed workload
gcloud container node-pools update a100-mixed-pool \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --max-surge-upgrade 1 \
    --max-unavailable-upgrade 0
```

## Pre-Upgrade Checklist

```markdown
GPU ML Platform Pre-Upgrade Checklist

Version Compatibility
- [ ] Verify 1.32 available in your release channel
- [ ] Check GKE 1.32 release notes for GPU driver changes
- [ ] **Critical:** Test GPU driver compatibility (1.31→1.32 may change CUDA version)
- [ ] Validate inference model loading on 1.32 staging cluster
- [ ] Confirm fine-tuning framework compatibility with 1.32

GPU-Specific Readiness  
- [ ] Verify GPU reservation headroom for blue-green capacity
- [ ] Check if GPUDirect/RDMA features remain compatible
- [ ] Confirm autoscaler won't create new nodes at old version during upgrade
- [ ] Document current CUDA version and test target version

Workload Protection
- [ ] PDBs configured for inference deployments
- [ ] No bare pods in GPU pools
- [ ] Fine-tuning jobs have checkpointing enabled
- [ ] terminationGracePeriodSeconds adequate for model cleanup

Operations
- [ ] Maintenance window during low-traffic period
- [ ] Monitoring baseline captured (inference latency, GPU utilization)
- [ ] Rollback plan documented
- [ ] Fine-tuning schedule reviewed — identify upgrade windows
```

## Upgrade Runbook

### Phase 1: Control Plane Upgrade
```bash
# Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
    --zone ZONE \
    --master \
    --cluster-version 1.32.X-gke.XXX

# Verify control plane health (wait 10-15 min)
kubectl get pods -n kube-system
gcloud container clusters describe CLUSTER_NAME --zone ZONE \
    --format="value(currentMasterVersion)"
```

### Phase 2: L4 Inference Pool (Autoscaled Blue-Green)
```bash
# Start autoscaled blue-green upgrade
gcloud container node-pools upgrade l4-inference-pool \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version 1.32.X-gke.XXX

# Monitor progress - green pool scaling up, blue scaling down
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=l4-inference-pool -o wide'

# Monitor inference pods migrating
kubectl get pods -A -l app=inference -o wide --sort-by='.spec.nodeName'
```

**Blue-green phases:**
1. **Create green pool** (25% initial capacity)
2. **Cordon blue pool** (stops new scheduling)
3. **Auto-scale transition** (green up, blue down as pods migrate)
4. **Soak period** (validate inference health)
5. **Delete blue pool** (automatic cleanup)

### Phase 3: A100 Pool (During Fine-tuning Gap)
```bash
# Remove maintenance exclusion during planned gap
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --remove-maintenance-exclusion a100-training-protection

# Conservative surge upgrade
gcloud container node-pools upgrade a100-mixed-pool \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version 1.32.X-gke.XXX

# Monitor - should be slow and steady
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=a100-mixed-pool'
```

## GPU-Specific Monitoring

```bash
# GPU driver version verification
kubectl get nodes -o jsonpath='{.items[*].status.nodeInfo.kernelVersion}'

# CUDA version check on upgraded nodes
kubectl debug node/NODE_NAME -it --image=nvidia/cuda:11.8-base-ubuntu20.04 \
    -- nvidia-smi

# Inference latency validation
# Your monitoring system - watch P95 inference latency during blue-green transition

# Fine-tuning job impact
kubectl get pods -l workload=training -o wide
```

## Rollback Strategy

**L4 Pool:** Blue-green allows fast rollback during soak period
```bash
# Rollback during soak (if inference issues detected)
gcloud container node-pools rollback l4-inference-pool \
    --cluster CLUSTER_NAME \
    --zone ZONE
```

**A100 Pool:** Standard node pool rollback
```bash
# Create new pool at 1.31, migrate workloads, delete upgraded pool
gcloud container node-pools create a100-rollback \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version 1.31.X-gke.XXX \
    --num-nodes 100 \
    --machine-type a2-highgpu-1g
```

## Timeline Estimate

- **Control plane:** 10-15 minutes
- **L4 autoscaled blue-green:** 2-4 hours (depends on traffic patterns)
- **A100 surge:** 4-6 hours (conservative, 100 nodes at maxSurge=1)
- **Total:** 6-10 hours end-to-end

## Risk Mitigation

1. **GPU driver compatibility:** Test in staging cluster first — MANDATORY
2. **Inference availability:** Blue-green keeps old pods serving during transition
3. **Fine-tuning protection:** Exclusion prevents mid-job eviction
4. **Capacity constraints:** Autoscaled blue-green minimizes 2x resource spike
5. **Traffic spikes:** Autoscaler works normally during blue-green transition

## Post-Upgrade Validation

```markdown
GPU ML Platform Post-Upgrade Validation

Cluster Health
- [ ] All nodes at 1.32: `kubectl get nodes -o wide`
- [ ] GPU drivers loaded: `kubectl get nodes -o jsonpath='{.items[*].status.allocatable.nvidia\.com/gpu}'`
- [ ] System pods healthy: `kubectl get pods -n kube-system`

Inference Workload Health
- [ ] All inference deployments at target replicas
- [ ] P95 inference latency within baseline (+/- 10%)
- [ ] GPU utilization normal
- [ ] Model loading successful on all upgraded nodes
- [ ] Autoscaler responding to traffic normally

Fine-tuning Readiness
- [ ] Test fine-tuning job on upgraded A100 nodes
- [ ] CUDA operations functional
- [ ] Checkpoint/resume cycle working
- [ ] Re-enable training queue when validation passes
```

This plan balances inference availability with upgrade necessity while protecting your fine-tuning workloads. The autoscaled blue-green strategy for L4 nodes should provide the smoothest inference experience during the upgrade.
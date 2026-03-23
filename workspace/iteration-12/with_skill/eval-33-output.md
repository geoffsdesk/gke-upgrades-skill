# GKE Upgrade Plan: ML Inference Platform (1.31 → 1.32)

## Environment Summary
- **Cluster**: Standard mode with auto-scaling GPU pools
- **Node pools**: L4 inference (200 nodes) + A100 inference/fine-tuning (100 nodes)
- **Current**: 1.31 → **Target**: 1.32
- **Workload types**: Latency-sensitive inference + 4-8h fine-tuning jobs
- **Priority**: Minimize inference impact, protect fine-tuning jobs

## Recommended Upgrade Strategy

### Control Plane
- **Timing**: Off-peak hours when inference traffic is lowest
- **Duration**: ~10-15 minutes, minimal inference impact

### Node Pool Strategy: Autoscaled Blue-Green
Given your inference workloads and capacity constraints, **autoscaled blue-green** is optimal:
- Maintains serving capacity throughout the upgrade
- No surge quota needed (GPU capacity is typically constrained)
- Allows fine-tuning jobs to complete naturally
- Auto-scales replacement nodes based on demand

## Upgrade Plan

### Phase 1: Pre-Upgrade (Day -7 to -1)

#### Version Compatibility Check
```bash
# Verify 1.32 availability in your channel
gcloud container get-server-config --zone YOUR_ZONE \
  --format="yaml(channels)" | grep -A 20 "REGULAR\|STABLE"

# Check for deprecated API usage
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
```

#### GPU Driver Compatibility
**Critical**: GKE 1.32 may update CUDA drivers. Test in staging:
- Verify your inference frameworks (TensorFlow, PyTorch, etc.) work with 1.32's CUDA version
- Check fine-tuning job compatibility

#### Workload Assessment
```bash
# Verify PDBs for inference services
kubectl get pdb -A -o wide

# Check for bare pods (won't reschedule)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# Confirm resource requests on all pods (required for auto-scaling)
kubectl get pods -A -o json | \
  jq '.items[] | select(.spec.containers[].resources.requests == null) | {ns:.metadata.namespace, name:.metadata.name}'
```

### Phase 2: Control Plane Upgrade

#### Configure Maintenance Window
```bash
gcloud container clusters update YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --maintenance-window-start 2024-XX-XXTXX:XX:XXZ \
  --maintenance-window-end 2024-XX-XXTXX:XX:XXZ \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"
```

#### Upgrade Control Plane
```bash
gcloud container clusters upgrade YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --master \
  --cluster-version 1.32.X-gke.XXXX
```

**Validation** (~15 minutes later):
```bash
gcloud container clusters describe YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --format="value(currentMasterVersion)"

kubectl get pods -n kube-system | grep -v Running
```

### Phase 3: Node Pool Upgrades

#### Configure Autoscaled Blue-Green for Both Pools

**L4 Inference Pool** (upgrade first - less critical than A100):
```bash
gcloud container node-pools update l4-inference-pool \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --enable-autoscaling \
  --total-min-nodes 50 \
  --total-max-nodes 250 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=7200s \
  --node-version 1.32.X-gke.XXXX
```

**A100 Fine-tuning/Inference Pool** (upgrade during low fine-tuning activity):
```bash
gcloud container node-pools update a100-pool \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --enable-autoscaling \
  --total-min-nodes 20 \
  --total-max-nodes 120 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.20,blue-green-full-batch-timeout=10800s \
  --node-version 1.32.X-gke.XXXX
```

#### Monitor Progress
```bash
# Watch node pool status
watch 'gcloud container node-pools list --cluster YOUR_CLUSTER_NAME --zone YOUR_ZONE'

# Monitor fine-tuning jobs
kubectl get pods -A -l workload-type=fine-tuning --field-selector=status.phase=Running

# Check inference latency (replace with your metrics)
# Monitor your inference service SLOs during the upgrade
```

### Phase 4: Fine-tuning Job Protection

For the A100 pool upgrade, coordinate with your ML team:

#### Option A: Natural Completion (Recommended)
```bash
# Check running fine-tuning jobs before starting A100 upgrade
kubectl get pods -A -l workload-type=fine-tuning -o wide

# Wait for jobs to complete naturally (4-8 hours)
# The blue-green strategy will cordon old nodes but let jobs finish
```

#### Option B: Checkpoint and Resume
If you can't wait:
```bash
# Trigger checkpointing in your fine-tuning framework
# Jobs will resume on new nodes after upgrade
```

## Timeline

| Phase | Duration | Impact |
|-------|----------|---------|
| Control plane | 10-15 min | Minimal - inference continues |
| L4 pool upgrade | 2-4 hours | Low - auto-scaling maintains capacity |
| A100 pool upgrade | 4-8 hours | Medium - coordinate with fine-tuning schedule |

## Rollback Plan

If issues arise:
```bash
# Blue-green allows fast rollback - uncordon the blue (old) pool
kubectl uncordon -l cloud.google.com/gke-nodepool=POOL_NAME

# Scale down green pool if needed
gcloud container clusters resize YOUR_CLUSTER_NAME \
  --node-pool green-pool-name \
  --num-nodes 0 \
  --zone YOUR_ZONE
```

## Post-Upgrade Validation Checklist

```markdown
- [ ] Control plane at 1.32: `gcloud container clusters describe CLUSTER --format="value(currentMasterVersion)"`
- [ ] Both node pools at 1.32: `gcloud container node-pools list --cluster CLUSTER`
- [ ] All nodes Ready: `kubectl get nodes | grep -v Ready`
- [ ] Inference services responding with normal latency
- [ ] Auto-scaling working: trigger scale-up test
- [ ] GPU driver version confirmed: `kubectl debug node/NODE_NAME -it -- nvidia-smi`
- [ ] Fine-tuning jobs can start successfully on new nodes
- [ ] No stuck pods: `kubectl get pods -A | grep -E "Pending|CrashLoopBackOff"`
```

## Risk Mitigation

1. **GPU Driver Changes**: Test 1.32 in staging first to catch CUDA compatibility issues
2. **Fine-tuning Jobs**: Schedule A100 upgrade during natural job gaps
3. **Inference Latency**: Monitor SLOs during L4 pool upgrade; rollback if degraded
4. **Auto-scaling**: Verify HPA/VPA configs work with new node versions
5. **Capacity**: Blue-green temporarily doubles resource usage - confirm quota headroom

## Key Commands Summary

```bash
# Pre-flight
gcloud container get-server-config --zone ZONE --format="yaml(channels)"
kubectl get pdb -A -o wide

# Control plane
gcloud container clusters upgrade CLUSTER --master --cluster-version 1.32.X-gke.XXXX

# Node pools (autoscaled blue-green)
gcloud container node-pools update POOL_NAME \
  --enable-autoscaling \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=7200s \
  --node-version 1.32.X-gke.XXXX

# Validation
kubectl get nodes -o wide -L cloud.google.com/gke-nodepool
```

This plan prioritizes your inference availability while protecting fine-tuning workloads. The autoscaled blue-green strategy is ideal for your GPU-constrained environment and auto-scaling requirements.
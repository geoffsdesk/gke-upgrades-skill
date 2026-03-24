# TPU Multislice Maintenance Impact & Preparation

## What Will Actually Happen

Your TPU multislice training job will experience **complete interruption** during the maintenance event. Here's the specific behavior:

### TPU Multislice Maintenance Characteristics
- **Atomic recreation**: Each TPU slice (your 4x 256-chip slices) is recreated entirely in a single step — not rolling
- **Cascading restart**: A maintenance event on ANY slice in your multislice environment triggers restart of **ALL 4 slices simultaneously**
- **All pods restart**: Every pod across all slices restarts at the same time
- **Capacity dependency**: If insufficient TPU v5e resources exist during recreation, slices block until hardware becomes available (potentially extended downtime)

**Timeline**: Expect 15-30 minutes of downtime minimum for slice recreation, potentially hours if TPU capacity is constrained in your zone.

## Preparation Checklist

### Critical Actions (Do These First)

```
□ Checkpoint your model state IMMEDIATELY
  - Save optimizer state, learning rate schedule, step count
  - Verify checkpoint integrity before the maintenance window
  
□ Set maintenance exclusion to control timing (if you need to delay):
  gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "tpu-training-protection" \
    --add-maintenance-exclusion-start CURRENT_TIME \
    --add-maintenance-exclusion-end DESIRED_END_TIME \
    --add-maintenance-exclusion-scope no_upgrades
  # Max 30 days deferral

□ Verify TPU capacity availability for recreation:
  gcloud compute tpus list --zone ZONE --filter="acceleratorType:v5litepod-256"
```

### Training Job Protection

**Option A: Controlled Checkpoint & Resume (Recommended)**
```bash
# 1. Trigger immediate checkpoint in your training code
# 2. Gracefully stop training job
kubectl scale deployment/statefulset TRAINING_JOB --replicas=0

# 3. Wait for maintenance to complete
# 4. Resume from checkpoint
kubectl scale deployment/statefulset TRAINING_JOB --replicas=ORIGINAL_COUNT
```

**Option B: Let It Crash & Resume**
- Ensure your training framework (JAX/Flax, PyTorch/XLA) has robust checkpoint/resume
- Verify checkpoint frequency is adequate (recommend every 100-500 steps for large models)
- Test recovery path in advance — don't discover checkpoint corruption during an outage

### Multislice Configuration Verification

```bash
# Verify current slice topology
kubectl get nodes -l cloud.google.com/gke-accelerator=tpu-v5-lite-256
kubectl describe tpu-topology # or equivalent for your setup

# Check placement policies are configured to recreate slices in same topology
kubectl get pods -o wide -l tpu-slice=SLICE_NAME
```

## Timeline Planning

### Before Maintenance
- **T-24h**: Save checkpoint, verify integrity
- **T-2h**: Stop new training iterations, let current batch complete
- **T-30m**: Scale training job to zero, confirm clean shutdown

### During Maintenance (15-30+ minutes)
- Monitor slice recreation: `watch 'kubectl get nodes -l cloud.google.com/gke-accelerator=tpu-v5-lite-256'`
- All 4 slices will show "NotReady" then recreate simultaneously
- Pods will remain in "Pending" state until slices are ready

### After Maintenance
- **T+0**: Verify all slices online, pods running
- **T+5m**: Resume training from checkpoint
- **T+30m**: Confirm training metrics recovered to pre-maintenance levels

## Monitoring Commands

```bash
# Track slice recreation progress
watch 'kubectl get nodes -l cloud.google.com/gke-accelerator=tpu-v5-lite-256 -o wide'

# Monitor pod status across slices
kubectl get pods -o wide --sort-by='.spec.nodeName'

# Check for TPU capacity issues
kubectl get events --field-selector reason=FailedScheduling
```

## Cost Considerations

**TPU billing continues during maintenance** — you're charged for reserved capacity even when slices are recreating. The interruption cost is primarily:
- Lost training progress (if checkpointing isn't recent)
- Researcher/engineer time managing the restart
- Potential delays if TPU capacity is unavailable

## Key Warnings

1. **No graceful migration**: Unlike GPU nodes that can drain gracefully, TPU slices are recreated atomically
2. **Topology preservation**: Verify your placement policies ensure slices recreate in the optimal network topology for multislice communication
3. **Checkpoint corruption risk**: Extended outages increase the chance of discovering stale/corrupt checkpoints — test your recovery procedure in advance
4. **Capacity constraints**: If Google's TPU capacity is tight in your zone, recreation could take hours rather than minutes

## Bottom Line

**Plan for complete training interruption.** TPU multislice maintenance is fundamentally different from standard GKE node maintenance — it's more like a controlled data center migration than a rolling update. Your 4-slice, 1024-chip training job will stop completely, then restart from your most recent checkpoint.

The key to minimizing impact is having a robust, tested checkpoint/resume workflow and triggering a final checkpoint before the maintenance window begins.
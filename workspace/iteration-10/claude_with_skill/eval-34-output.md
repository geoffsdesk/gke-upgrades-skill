# TPU Multislice Maintenance Impact & Preparation

## What Will Actually Happen

**Catastrophic restart scenario:** Your TPU multislice environment will experience a complete training restart during the maintenance event. Here's the specific impact:

### 1. Atomic Recreation of All Slices
- **All 4 slices (1,024 TPU chips total) will be recreated simultaneously** — not rolling
- This is fundamentally different from CPU/GPU node upgrades which can be rolling
- Every pod across all slices restarts at the same time

### 2. Cascading Restart Behavior
- A maintenance event on **ANY single slice triggers restart of ALL slices** in your multislice environment
- Even if only 1 of your 4 slices needs maintenance, all 4 will restart
- This is due to the interconnected nature of multislice training topology

### 3. Training Job Impact
- **Complete training interruption** — your LLM training will stop immediately
- **No graceful checkpoint trigger** — the job won't get a shutdown signal to save state
- **Full restart required** — you'll resume from your last saved checkpoint, losing any progress since then

## Capacity Risk During Recreation

**Critical concern:** If insufficient TPU v5e resources exist in your zone during the recreation window:
- Slices will block until hardware becomes available
- **Extended downtime possible** — potentially hours or days if capacity is constrained
- Your reservation helps but doesn't guarantee instant recreation during high-demand periods

## Preparation Checklist

### Immediate Actions (Before Maintenance)

```markdown
- [ ] **Force checkpoint save NOW** — don't wait for the next automatic checkpoint
- [ ] Verify checkpoint integrity and can be loaded successfully
- [ ] Document current training step/epoch for restart planning
- [ ] Confirm you have sufficient TPU v5e reservation capacity for all 4 slices
- [ ] Check GCP status page for any known TPU capacity issues in your zone
- [ ] Notify your team of the planned training interruption window
```

### Checkpoint Strategy Commands

```bash
# If using JAX/Flax training
# Trigger immediate checkpoint (implementation depends on your training framework)
kubectl exec -it trainer-pod -- python save_checkpoint.py --force

# Verify checkpoint files
kubectl exec -it trainer-pod -- ls -la /checkpoints/
kubectl exec -it trainer-pod -- python validate_checkpoint.py --latest

# Document current state
kubectl logs trainer-pod | grep "Step\|Epoch" | tail -10
```

### During Maintenance Window

```bash
# Monitor slice recreation status
kubectl get pods -l tpu-slice=all -w

# Check for capacity-related delays
kubectl get events --field-selector reason=FailedScheduling
kubectl describe pods | grep -A5 "scheduling"

# Once slices are ready, verify topology
kubectl exec -it trainer-pod -- python -c "
import jax
print(f'Devices: {jax.device_count()}')
print(f'Local devices: {jax.local_device_count()}')  
print(f'Process count: {jax.process_count()}')
"
```

### Post-Maintenance Recovery

```bash
# Verify all 4 slices are healthy before restarting training
kubectl get pods -l component=tpu-slice --no-headers | wc -l  # Should be 4

# Confirm TPU topology is intact
kubectl exec -it trainer-pod -- python check_tpu_topology.py

# Resume training from checkpoint
kubectl exec -it trainer-pod -- python train.py \
  --resume_from_checkpoint=/checkpoints/latest \
  --verify_checkpoint_before_start=true
```

## Expected Timeline

- **Maintenance notification:** Typically 7-14 days advance notice
- **Slice recreation time:** ~10-30 minutes per slice (can be longer if capacity constrained)
- **Training restart:** 5-15 minutes depending on checkpoint size and model initialization
- **Total downtime:** Plan for 1-2 hours minimum, potentially longer

## Key Recommendations

1. **Increase checkpoint frequency** leading up to the maintenance window — minimize lost progress
2. **Don't schedule long training runs** that would cross the maintenance window
3. **Have a capacity backup plan** — consider alternative zones if your primary zone might be capacity-constrained
4. **Monitor GCP TPU capacity dashboards** in your region for early warnings

## Alternative: Proactive Migration

If the maintenance timing conflicts with critical training milestones, consider **proactively migrating to a fresh multislice environment** before the forced maintenance:

```bash
# Create new 4-slice environment in different zone/region
# Checkpoint current training
# Start new training job in fresh environment
# Delete old environment before maintenance window
```

This gives you controlled timing rather than waiting for the forced maintenance event.

**Bottom line:** Plan for complete training restart with 1-2 hour downtime minimum. Your most recent checkpoint is your lifeline.
# TPU Multislice Maintenance Impact & Preparation Guide

## What Will Actually Happen

**Complete training interruption is guaranteed.** TPU multislice environments have fundamentally different upgrade behavior than regular GPU clusters:

### Atomic Recreation Behavior
- **All 4 slices will be recreated simultaneously** - this is not a rolling upgrade
- **Every pod across all slices restarts at once** - there's no graceful migration
- **Total downtime:** Expect 10-30 minutes for slice recreation + your model reload time
- **Cascading restart:** The maintenance event on ANY slice triggers restart of ALL slices in your multislice environment

### Capacity Dependency Risk
- If insufficient TPU v5e resources exist during recreation, your slices will block until hardware becomes available
- This can extend downtime from minutes to hours or longer depending on TPU availability
- Your job won't resume until ALL 4 slices can be provisioned simultaneously

## Preparation Checklist

```
TPU Multislice Maintenance Preparation
- [ ] Training checkpoint saved at latest possible moment before maintenance window
- [ ] Checkpoint location verified accessible from recreated pods
- [ ] Model loading time estimated (add to expected downtime)
- [ ] Downstream systems notified of planned interruption
- [ ] Monitoring alerts configured for slice recreation events
- [ ] Backup compute plan ready if TPU capacity is unavailable post-maintenance
```

## Recommended Actions

### Before Maintenance (Critical)
1. **Force a checkpoint save immediately before the maintenance window**
   ```bash
   # Trigger immediate checkpoint in your training script
   # Verify checkpoint completed successfully
   ```

2. **Validate checkpoint integrity**
   - Confirm latest checkpoint can be loaded
   - Test restore process in advance
   - Document exact checkpoint path/format

3. **Estimate total recovery time**
   - Slice recreation: 10-30 minutes
   - Your model reload time: ___
   - Total expected downtime: ___

### During Maintenance
- **Monitor slice status:**
  ```bash
  kubectl get nodes -l cloud.google.com/gke-accelerator=tpu-v5-litepod-256
  watch 'kubectl get pods -n YOUR_NAMESPACE'
  ```

### After Maintenance
1. **Verify all slices are healthy before restarting training**
2. **Restart from latest checkpoint** - don't assume any in-memory state survived
3. **Monitor for capacity issues** - if slices don't provision promptly, you may need to wait for TPU availability

## Alternative: Proactive Checkpoint & Reschedule

Given the guaranteed interruption, consider:
- **Pause training proactively** 30 minutes before maintenance
- **Take final checkpoint** 
- **Resume after maintenance completes**

This gives you control over the checkpoint timing rather than relying on an emergency checkpoint during the maintenance event.

## Key Differences from GPU Upgrades

| Aspect | GPU Clusters | TPU Multislice |
|--------|-------------|----------------|
| Upgrade style | Rolling, node-by-node | Atomic recreation |
| Graceful shutdown | PDB respected for 1 hour | All pods restart immediately |
| Capacity planning | Can use surge/blue-green | Must provision full slice set |
| Recovery strategy | Workload-by-workload | All-or-nothing |

**Bottom line:** Plan for a complete restart of your training job. The maintenance is not optional and cannot be gracefully handled - your 4-slice training environment will go down completely and come back up fresh.
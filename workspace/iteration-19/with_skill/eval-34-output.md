# TPU Multislice Maintenance Impact & Preparation

## What will actually happen to your training job

**Critical understanding: TPU multislice maintenance is fundamentally different from regular GPU/CPU node upgrades.**

### Maintenance behavior for your 4-slice environment:

1. **Atomic recreation of ALL slices**: When maintenance triggers, all 4 TPU v5e slices (1,024 total chips) will be recreated simultaneously in a single step. This is NOT a rolling upgrade.

2. **Cascading restart**: A maintenance event on ANY single slice triggers restart of ALL slices in your multislice environment. Even if only one slice needs maintenance, your entire 4-slice training job will restart.

3. **Complete training interruption**: Your LLM training job will be forcibly terminated and must restart from the last checkpoint. There is no graceful migration or live upgrade path for TPU multislice.

4. **Capacity dependency risk**: If insufficient TPU v5e capacity exists during recreation (high demand, reservation issues, hardware failures), your slices may be blocked until hardware becomes available. This could extend downtime from minutes to hours or longer.

## Preparation checklist

```
TPU Multislice Maintenance Preparation
- [ ] Checkpoint strategy verified and tested
- [ ] Checkpoint frequency increased to minimize loss
- [ ] Training resumption procedure documented
- [ ] Capacity/reservation status confirmed
- [ ] Monitoring and alerting configured
- [ ] Rollback plan documented

Checkpointing
- [ ] Recent checkpoint completed and verified loadable
- [ ] Checkpoint interval reduced (e.g., every 15-30 minutes instead of hourly)
- [ ] Checkpoint storage (GCS bucket) accessible and has sufficient quota
- [ ] Training script handles checkpoint resumption gracefully
- [ ] Checkpoint metadata includes step count, model state, optimizer state
- [ ] Test checkpoint restore in dev environment

Capacity Planning
- [ ] TPU reservation status verified: `gcloud compute tpus list --zone=ZONE`
- [ ] No competing TPU reservations during expected maintenance window
- [ ] Sufficient GCS bandwidth for checkpoint I/O during restart
- [ ] Network connectivity to TPU slices confirmed

Operational Readiness
- [ ] Training team notified of expected interruption
- [ ] Monitoring configured for slice health: `kubectl get pods -n NAMESPACE -l tpu-slice`
- [ ] Restart procedure tested and documented
- [ ] Alternative compute reserved (if available) for time-critical deadlines
```

## Recommended actions

### Before maintenance (24-48 hours prior):

1. **Increase checkpoint frequency**:
   ```python
   # In your training script
   CHECKPOINT_INTERVAL = 900  # Every 15 minutes instead of hourly
   ```

2. **Force a fresh checkpoint**:
   ```bash
   # Trigger immediate checkpoint via your training framework
   # e.g., for JAX/Flax training:
   python training_script.py --force_checkpoint
   ```

3. **Verify checkpoint integrity**:
   ```bash
   # Test loading the latest checkpoint
   python verify_checkpoint.py --checkpoint_path=gs://YOUR_BUCKET/checkpoints/latest
   ```

### During maintenance:

4. **Monitor slice recreation**:
   ```bash
   # Watch for slice recreation
   watch 'kubectl get pods -n NAMESPACE -l tpu-slice'
   
   # Monitor TPU status
   gcloud compute tpus list --zone=ZONE
   ```

5. **Expect 15-30 minute downtime minimum** for slice recreation, assuming capacity is available.

### After maintenance:

6. **Restart training from checkpoint**:
   ```bash
   # Resume training job
   kubectl apply -f training-job.yaml
   
   # Verify all slices are healthy
   kubectl get pods -n NAMESPACE -l tpu-slice -o wide
   ```

## Key differences from GPU maintenance

| Aspect | GPU/CPU nodes | TPU multislice |
|--------|---------------|----------------|
| **Upgrade method** | Rolling, one node at a time | Atomic recreation of all slices |
| **Training continuity** | Possible with checkpointing | Always interrupted |
| **Scope** | Per-node | All slices simultaneously |
| **Downtime** | Minimized by rolling | Full restart required |
| **Capacity risk** | Lower (individual nodes) | Higher (entire slice set) |

## Expected timeline

- **Preparation phase**: 24-48 hours when maintenance is announced
- **Maintenance execution**: 15-30 minutes minimum (longer if capacity constrained)
- **Training restart**: 5-15 minutes to reload checkpoint and resume

**Total expected interruption: 30-60 minutes minimum**, assuming:
- Sufficient TPU capacity available
- Recent checkpoint exists
- No hardware failures during recreation

## Risk mitigation

- **Never rely on graceful shutdown** — TPU multislice maintenance is always disruptive
- **Checkpoint more frequently** leading up to maintenance windows
- **Test your checkpoint/resume pipeline** before maintenance occurs
- **Have alternative compute reserved** if your training has hard deadlines
- **Monitor GCP Status Page** for any related TPU service issues that could extend downtime

The key insight: treat TPU multislice maintenance as a planned restart, not an upgrade. Your preparation should focus entirely on minimizing training progress loss through frequent checkpointing, not on keeping the job running during maintenance.
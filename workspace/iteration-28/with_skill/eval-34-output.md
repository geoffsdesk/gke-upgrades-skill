# TPU Multislice Maintenance Event Impact & Preparation

## What Will Actually Happen

**Critical understanding: TPU multislice maintenance is atomic and cascading.**

When the maintenance event triggers:

1. **All 4 slices will restart simultaneously** — TPU multislice environments don't support rolling updates. The entire multislice topology (all 1,024 TPU chips across your 4 slices) will be recreated in a single atomic operation.

2. **Your training job will terminate immediately** — There's no graceful drain period like with GPU nodes. TPU slices are destroyed and recreated, causing an immediate stop of all running workloads.

3. **Cascading restart behavior** — Even if maintenance technically only affects 1 slice, GKE will restart ALL slices in the multislice environment to maintain the required interconnect topology.

4. **Recreation dependency** — The slices will only come back online if sufficient TPU v5e capacity is available in your zone. If hardware is constrained, you could face extended downtime waiting for TPU resources to become available.

## Preparation Checklist

### Training Job Protection
- [ ] **Checkpoint immediately** — Save your model state, optimizer state, and training metadata to persistent storage (Cloud Storage/GCS) right now
- [ ] **Verify checkpoint integrity** — Test that your checkpoints can successfully restore the model and resume training
- [ ] **Document exact training state** — Record current step/epoch, learning rate schedule position, and any other training metadata needed for seamless resume
- [ ] **Test restore procedure** — Actually test loading from checkpoint in your training environment to confirm the restore path works

### Capacity Planning
- [ ] **Verify TPU quota** — Confirm you have sufficient TPU v5e quota to recreate all 4 slices (1,024 chips total)
- [ ] **Check regional capacity** — TPU capacity can be constrained. If possible, test creating a small TPU slice in your zone to verify availability
- [ ] **Prepare for potential delays** — TPU slice recreation can take 15-30 minutes under normal conditions, longer if capacity is limited

### Operational Preparation
- [ ] **Schedule during training breaks** — If you have natural checkpointing intervals, try to align the maintenance window with one of those
- [ ] **Monitor maintenance notifications** — Check GKE cluster notifications in Cloud Logging for specific timing: `resource.type="gke_cluster" jsonPayload.operationType="MAINTENANCE"`
- [ ] **Have the team available** — Ensure someone can monitor the restart and resume training manually if needed

## Recovery Procedure

1. **Wait for all slices to become Ready** — Don't start training until all 4 slices show Ready status:
   ```bash
   kubectl get nodes -l cloud.google.com/gke-accelerator=tpu-v5e
   ```

2. **Verify TPU topology** — Confirm the multislice interconnect is properly established before resuming training

3. **Resume from checkpoint** — Load your most recent checkpoint and continue training from the saved state

4. **Monitor for cascading issues** — TPU multislice environments can have subtle interconnect issues post-maintenance. Watch for training performance degradation or communication timeouts

## Key Differences from GPU Maintenance

Unlike GPU clusters where you might get rolling updates or partial capacity:
- **No rolling updates** — It's all-or-nothing restart
- **No surge capacity** — You can't provision extra TPUs during the maintenance window
- **Topology dependency** — All slices must come up together for the multislice to function
- **Longer recovery** — TPU slice provisioning takes significantly longer than GPU node replacement

## Timeline Expectations

- **Downtime duration:** 15-30+ minutes minimum, potentially hours if TPU capacity is constrained
- **No partial restoration** — You'll have zero TPU capacity until all slices are recreated successfully

The maintenance event will definitely interrupt your training. The key is having robust checkpointing so you can resume seamlessly once the TPU resources are restored.
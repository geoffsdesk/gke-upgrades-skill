# TPU Multislice Maintenance Impact & Preparation Plan

## What Will Actually Happen

Your training job will experience **complete interruption** due to TPU multislice's atomic upgrade behavior:

### Multislice Maintenance Behavior
- **Atomic recreation:** Each 256-chip TPU slice is recreated entirely in a single step — not rolling
- **Cascading restart:** A maintenance event on ANY slice triggers restart of ALL 4 slices simultaneously
- **All pods restart:** Every pod across all 1,024 TPU chips will terminate and restart
- **Capacity dependency:** If insufficient TPU v5e resources exist during recreation, slices block until hardware is available

### Expected Downtime
- **Minimum:** 10-15 minutes for slice recreation + pod restart
- **Realistic:** 30-60 minutes including training job restart and checkpoint loading
- **Risk scenario:** Hours if TPU v5e capacity is constrained during recreation

## Preparation Checklist

```
TPU Multislice Maintenance Preparation
- [ ] Checkpoint strategy finalized
- [ ] Training resumption tested
- [ ] Maintenance window identified
- [ ] Capacity risk mitigated
- [ ] Monitoring configured

Checkpointing (Critical)
- [ ] Enable frequent checkpointing (every 30-60 minutes vs daily)
- [ ] Verify checkpoint save location (GCS bucket accessible across zones)
- [ ] Test checkpoint restore in staging environment
- [ ] Configure training framework for automatic resumption from latest checkpoint
- [ ] Document checkpoint restore command sequence for ops team

Maintenance Control
- [ ] Apply "no upgrades" maintenance exclusion to defer 30 days if needed:
      gcloud container clusters update CLUSTER_NAME \
        --zone ZONE \
        --add-maintenance-exclusion-name "llm-training-campaign" \
        --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
        --add-maintenance-exclusion-end-time $(date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ) \
        --add-maintenance-exclusion-scope no_upgrades
- [ ] Coordinate with GCP account team on TPU v5e capacity availability during maintenance window
- [ ] Schedule maintenance during natural training gap if possible

Operational Readiness
- [ ] On-call team briefed on multislice restart behavior
- [ ] Training progress/loss monitoring active
- [ ] Runbook for manual training restart post-maintenance
- [ ] Stakeholder communication: "Training will restart from checkpoint, expect 1-2 hour gap"
```

## Mitigation Strategies

### Option 1: Checkpoint and Accept Restart (Recommended)
```bash
# Before maintenance: Force checkpoint save
kubectl exec -it TRAINING_POD -- python save_checkpoint.py --force

# After maintenance: Verify all slices healthy, restart training
kubectl get pods -A | grep tpu
python resume_training.py --from-checkpoint=gs://BUCKET/latest
```

### Option 2: Defer Maintenance (30-day max)
```bash
# Apply "no upgrades" exclusion to delay maintenance
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "critical-training-run" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades
```

### Option 3: Coordinate Training Cycles
Plan training campaigns in <30 day cycles with natural maintenance gaps between campaigns.

## Critical Considerations

**Checkpoint Strategy:** This is your primary defense. Ensure checkpoints are:
- Saved frequently (every 30-60 min for large models)
- Stored in persistent storage (GCS, not local disks)
- Tested for successful restoration
- Include optimizer state, learning rate schedules, and random number generator states

**Capacity Risk:** TPU v5e is in high demand. If GKE can't provision replacement slices during maintenance:
- Your job blocks until hardware becomes available
- Could extend downtime from minutes to hours
- Work with your GCP account team to understand capacity availability

**Training Framework Integration:** Common frameworks handle this differently:
- **JAX/Flax:** Use `orbax` for checkpointing, configure auto-resumption
- **PyTorch/XLA:** Use `torch_xla.distributed.checkpoint`, verify `WORLD_SIZE` consistency after restart
- **Custom training:** Ensure your checkpointing includes all necessary state

## Post-Maintenance Validation

```bash
# Verify all TPU slices healthy
kubectl get pods -A -o wide | grep tpu

# Check TPU topology preserved
kubectl exec -it TRAINING_POD -- python -c "import torch_xla.core.xla_model as xm; print(xm.get_ordinal(), xm.xrt_world_size())"

# Restart training from checkpoint
python resume_training.py --from-checkpoint=gs://BUCKET/checkpoints/latest
```

The key insight for TPU multislice: **plan for full restart, not graceful migration**. Unlike GPU node upgrades where individual nodes can be cordoned/drained, TPU slices are atomic units that recreate entirely. Your checkpoint strategy is your primary tool for minimizing training progress loss.
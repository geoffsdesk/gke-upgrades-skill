# TPU Multislice Maintenance Impact & Preparation

## What Will Actually Happen

**Critical: Your entire training job will be interrupted.** TPU multislice environments have unique maintenance behavior:

### Cascading Restart Behavior
- **ANY maintenance event on ANY slice triggers restart of ALL slices** in your multislice environment
- Even if maintenance only affects 1 of your 4 slices, all 4 slices (1,024 TPU chips total) will be recreated
- This is **atomic recreation** — not rolling upgrades like Standard GKE node pools

### Training Job Impact
- **All training pods across all slices restart simultaneously**
- Training progress is lost unless you have checkpointing enabled
- Job must resume from the last saved checkpoint
- **No graceful migration** — TPU slices are recreated entirely in a single step

### Capacity Risk
- If insufficient TPU v5e capacity exists during recreation, slices will block until hardware becomes available
- This can cause **extended downtime beyond the maintenance window** — potentially hours to days depending on TPU availability in your zone

## Preparation Checklist

```markdown
TPU Multislice Maintenance Prep
- [ ] Verify training job has checkpointing enabled and working
- [ ] Set aggressive checkpoint frequency (every 30-60 minutes during maintenance period)
- [ ] Test checkpoint restore procedure in advance
- [ ] Identify current training step/epoch for restart planning
- [ ] Coordinate with team — plan for multi-hour outage
- [ ] Document slice configuration for recreation verification
- [ ] Monitor TPU capacity in your zone leading up to maintenance
```

## Recommended Actions

### 1. **Checkpoint Strategy (Critical)**
```bash
# Verify your training framework is checkpointing
# For JAX/Flax training:
# - Ensure orbax.checkpoint or similar is saving state frequently
# - Test restoration from checkpoint before maintenance

# Example verification:
ls -la /path/to/checkpoints/
# Should show recent checkpoint files with timestamps
```

### 2. **Pre-Maintenance Validation**
```bash
# Document current slice configuration
gcloud compute tpus tpu-vm list --zone=ZONE
kubectl get pods -n NAMESPACE -o wide | grep tpu

# Verify checkpoint location and recency
kubectl exec -it TRAINING_POD -- ls -la /checkpoints/
```

### 3. **During Maintenance Window**
- **Expect complete training interruption** — plan accordingly
- Monitor slice recreation: `gcloud compute tpus tpu-vm list --zone=ZONE`
- **Do not attempt to reschedule** until all slices are fully available
- Verify network topology and placement after recreation

### 4. **Post-Maintenance Recovery**
```bash
# Verify all slices are healthy
kubectl get pods -n NAMESPACE | grep tpu
gcloud compute tpus tpu-vm list --zone=ZONE

# Confirm inter-slice connectivity
kubectl logs TRAINING_POD | grep -i "slice\|topology"

# Resume training from checkpoint
# Your training script should automatically detect and load latest checkpoint
```

## Key Differences from Standard GKE

Unlike standard node pool maintenance:
- **No surge upgrade option** — TPU slices are recreated atomically
- **No blue-green strategy** — all slices restart together
- **Cascading impact** — maintenance on any slice affects the entire multislice job
- **Capacity dependency** — recreation can be delayed by TPU hardware availability

## Timeline Planning

**Conservative estimate: 2-6 hours total downtime**
- Slice deletion: ~15 minutes
- TPU hardware allocation: 30 minutes - several hours (depends on capacity)
- Slice recreation and initialization: ~30-60 minutes
- Training job restart and checkpoint loading: ~15-30 minutes

**If TPU capacity is constrained in your zone, this could extend to days.**

## Long-term Recommendations

1. **Automated checkpointing**: Set up frequent automated checkpoints during known maintenance periods
2. **Multi-zone deployment**: Consider distributing slices across zones (if your training framework supports it) to reduce single-zone capacity risk
3. **Maintenance exclusions**: Use GKE maintenance exclusions to defer maintenance during critical training milestones:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "critical-training" \
  --add-maintenance-exclusion-start-time START_TIME \
  --add-maintenance-exclusion-end-time END_TIME \
  --add-maintenance-exclusion-scope no_upgrades
```

4. **TPU reservation monitoring**: Track TPU capacity trends in your zone to predict recreation delays

This is fundamentally different from regular Kubernetes workload maintenance — treat it as a planned complete restart of your training pipeline, not a rolling update.
# TPU Multislice Maintenance Event Guide

## What Will Actually Happen

**Critical point:** Your TPU multislice environment has fundamentally different maintenance behavior than regular GPU nodes. Here's what to expect:

### Atomic Recreation, Not Rolling Updates
- **All 4 slices will be recreated simultaneously** — there is no rolling update for multislice TPU environments
- **Every pod across all slices will restart** — your training job will be completely interrupted
- **Cascading restart:** A maintenance event on ANY single slice triggers restart of ALL slices in the multislice environment

### Timeline and Capacity Risk
- **Downtime:** Expect 30-60 minutes minimum for slice recreation (can be longer if TPU capacity is constrained)
- **Capacity dependency:** If insufficient TPU v5e resources exist during recreation, your slices will block until hardware becomes available
- **No graceful migration:** Unlike CPU/GPU nodes, TPU slices cannot be live-migrated — recreation is the only path

## Preparation Checklist

```markdown
Pre-Maintenance Checklist - TPU Multislice
- [ ] Training job checkpoint saved at latest opportunity
- [ ] Checkpoint verification: can restore from latest checkpoint successfully
- [ ] Training resumption script tested from checkpoint
- [ ] Model artifacts backed up to Cloud Storage
- [ ] TPU quota confirmed sufficient for recreation (1,024 v5e chips total)
- [ ] Maintenance window timing confirmed with team
- [ ] Training progress documented (steps completed, loss curves, etc.)
```

## Recommended Action Plan

### Option 1: Proactive Checkpoint and Wait (Recommended)
```bash
# 1. Trigger immediate checkpoint in your training job
# (implementation depends on your training framework)

# 2. Verify checkpoint integrity
# Test restoration on a smaller slice if possible

# 3. Gracefully stop training before the maintenance window
# This prevents mid-step interruption and potential checkpoint corruption
```

### Option 2: Request Maintenance Exclusion
```bash
# Apply a 30-day "no upgrades" exclusion to defer maintenance
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-campaign-protection" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades
```

**Important:** This only delays the inevitable. Use this time to reach a natural checkpoint/pause in your training campaign.

## Post-Maintenance Recovery

### Validation Steps
```bash
# 1. Verify all slices are healthy
kubectl get pods -n NAMESPACE -o wide
kubectl get nodes -l cloud.google.com/gke-accelerator=tpu-v5-lite-podslice

# 2. Check TPU topology is correct
# Your training framework should verify slice interconnect

# 3. Validate checkpoint accessibility
# Ensure GCS buckets/persistent volumes are mounted correctly
```

### Training Resumption
```bash
# Start training from latest checkpoint
# Monitor for any topology/performance regressions
# Verify loss curves resume at expected values
```

## Critical Considerations

### Multislice-Specific Risks
- **Slice placement:** Recreated slices may not land in the same physical topology, potentially affecting RDMA performance
- **All-or-nothing:** Unlike GPU clusters where you can upgrade pools sequentially, all TPU slices restart simultaneously
- **Capacity scarcity:** TPU v5e chips are in high demand — recreation may queue if no capacity is available

### Training Job Protection
- **Never run maintenance during active training steps** — checkpoint corruption risk is high
- **Plan for extended downtime** — 30-60+ minutes is normal for large multislice recreation
- **Verify compact placement policies** if you use them — maintenance may break physical co-location

## Framework-Specific Notes

### JAX/Flax Training
- Use `jax.checkpoint` with regular saves to GCS
- Test restoration on a smaller slice configuration first
- Monitor for any JAX compilation regressions post-maintenance

### PyTorch/XLA Training
- Leverage `torch_xla.core.xla_model.save()` for checkpoints
- Verify distributed training state is properly restored
- Check for any XLA backend issues after TPU recreation

## When to Contact Support

Contact GKE support immediately if:
- Slice recreation has been stuck for >2 hours
- Recreated slices are missing from expected zones
- Training performance drops significantly post-maintenance (may indicate topology issues)
- Any slices show hardware errors after recreation

**Key insight:** Plan TPU multislice maintenance like you would plan a complete training restart — because that's exactly what it is. The "maintenance event" is really a full environment recreation that requires training job coordination.
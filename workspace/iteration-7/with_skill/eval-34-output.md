# TPU Multislice Maintenance Impact & Preparation Guide

## What Will Actually Happen

**Atomic recreation of ALL slices:** Your TPU multislice environment will experience a **complete restart** of all 4 slices simultaneously. This is fundamentally different from CPU/GPU node upgrades:

- **All 4 slices restart together** — GKE treats the entire multislice as a single unit
- **No rolling upgrade** — unlike CPU nodes, there's no gradual replacement 
- **Complete job termination** — your LLM training will stop and need to restart from the last checkpoint
- **Cascading effect** — maintenance on ANY slice triggers restart of ALL slices in the environment

**Timeline:** The restart process typically takes 15-30 minutes for TPU slice provisioning + your job startup time.

## Critical Preparation Steps

### 1. Force checkpoint save BEFORE maintenance window
```bash
# If using JAX/Flax - trigger immediate checkpoint
# This is environment-specific to your training framework

# Verify checkpoint integrity and completeness
# Test that you can actually restore from it
```

### 2. Verify checkpoint restoration works
```bash
# Test restore on a smaller slice first if possible
# Confirm model state, optimizer state, and step counter are preserved
# Validate that training can resume from exact step
```

### 3. Plan for extended downtime
- **Minimum**: 15-30 min for TPU provisioning
- **Reality**: Add your job startup time (model loading, data pipeline init, etc.)
- **Risk buffer**: TPU capacity constraints can extend provisioning time

### 4. Configure maintenance exclusion (if timing is critical)
```bash
# Block all upgrades for up to 30 days to defer past critical training periods
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-campaign-jan2024" \
  --add-maintenance-exclusion-start-time "2024-01-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-02-14T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

### 5. Capacity dependency planning
```bash
# Check TPU quota and availability in your zone
gcloud compute tpus list --zone=ZONE
gcloud compute project-info describe --format="yaml(quotas)" | grep -A 5 tpu
```

If TPU v5e capacity is scarce in your zone during the maintenance window, the restart could be delayed significantly.

## Framework-Specific Preparation

### JAX/Flax Training
```python
# Ensure checkpointing is frequent and atomic
checkpoint_manager = orbax.checkpoint.CheckpointManager(
    checkpoint_dir,
    orbax.checkpoint.PyTreeCheckpointer(),
    options=orbax.checkpoint.CheckpointManagerOptions(
        save_interval_steps=1000,  # Adjust based on your needs
        max_to_keep=3,
        create=True
    )
)

# Before maintenance window - force save
checkpoint_manager.save(step, {'model': model_state, 'optimizer': optimizer_state})
```

### PyTorch/XLA Training
```python
# Atomic checkpoint saves with verification
torch.save({
    'step': step,
    'model_state_dict': model.state_dict(),
    'optimizer_state_dict': optimizer.state_dict(),
    'loss': loss,
}, f'checkpoint_step_{step}.pth')

# Verify checkpoint immediately after save
checkpoint = torch.load(f'checkpoint_step_{step}.pth')
# Test model.load_state_dict(checkpoint['model_state_dict'])
```

## Post-Restart Recovery Process

### 1. Verify TPU slice health
```bash
kubectl get nodes -l accelerator=tpu
kubectl describe nodes | grep -A 10 "TPU"
```

### 2. Monitor job restart
```bash
# Check pod status across all slices
kubectl get pods -A -l workload-type=training

# Monitor TPU utilization recovery
kubectl logs -l app=training-job --tail=100 -f
```

### 3. Validate training resumption
- Confirm training resumes from exact checkpoint step
- Verify loss curves continue smoothly (no jump/reset)
- Check that data pipeline resumes from correct position
- Monitor for any TPU performance degradation

## Risk Mitigation

**Checkpoint frequency:** For large models, increase checkpoint frequency before known maintenance. The overhead is worth the reduced risk of lost progress.

**Backup strategy:** Keep multiple recent checkpoints. TPU slice failures during restart can corrupt the most recent save.

**Capacity planning:** TPU v5e availability can be constrained. Consider:
- Reserved capacity if this is business-critical training
- Cross-zone backup plan (though this requires data migration)
- Relationship with your Google Cloud account team for capacity assistance

## Alternative: Defer via Maintenance Exclusion

Given that TPU multislice training is measured in weeks/months, consider using maintenance exclusions to control timing:

```bash
# "No upgrades" exclusion defers ALL maintenance for up to 30 days
# Use during critical training phases, then allow during planned gaps
```

**Important:** Even with exclusions, emergency security updates may still trigger restarts. Plan accordingly.

The key insight for TPU multislice: **treat every maintenance event as a planned restart**. The atomic recreation behavior means there's no graceful migration — only checkpoint-restore cycles.
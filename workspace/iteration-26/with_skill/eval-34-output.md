# TPU Multislice Maintenance Impact & Preparation

## What Will Actually Happen

Your TPU multislice training environment has **fundamentally different upgrade behavior** than regular GPU/CPU clusters:

### Critical Impact Points:
1. **Cascading restart across ALL slices**: A maintenance event on ANY single slice in your multislice environment triggers restart of ALL 4 slices simultaneously. This is not rolling—it's atomic recreation of the entire multislice environment.

2. **Complete job termination**: Your LLM training job will be forcibly terminated across all 1,024 TPU chips. There's no graceful migration or partial continuation—the entire training run stops.

3. **Capacity dependency risk**: All 4 slices are recreated simultaneously. If insufficient TPU v5e resources exist in your zone during recreation, slices will block until hardware becomes available. This can cause **extended downtime** (potentially hours) beyond the normal maintenance window.

## Immediate Preparation Steps

### 1. Save Training State (Critical)
```bash
# Ensure your training script has checkpointing enabled and force a checkpoint save
# Most frameworks auto-checkpoint, but trigger a manual save before maintenance
python your_training_script.py --save_checkpoint --checkpoint_path=gs://your-bucket/checkpoints/pre-maintenance
```

### 2. Verify Checkpoint Integrity
```bash
# Test that you can actually resume from the checkpoint
python your_training_script.py --restore_checkpoint --checkpoint_path=gs://your-bucket/checkpoints/pre-maintenance --dry_run
```

### 3. Document Current Training State
- Current step/epoch number
- Loss values and convergence metrics  
- Training hyperparameters
- Model configuration
- Data pipeline state (which examples you've processed)

### 4. Plan for Extended Downtime
- **TPU capacity may not be immediately available** after maintenance
- Plan for potentially 4-8 hours of downtime (worst case)
- Communicate timeline to stakeholders expecting training results

### 5. Apply Maintenance Exclusion (If Time Permits)
```bash
# If you need to delay the maintenance event, apply a 30-day exclusion
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "tpu-training-protection" \
    --add-maintenance-exclusion-start-time START_TIME \
    --add-maintenance-exclusion-end-time END_TIME \
    --add-maintenance-exclusion-scope no_upgrades
```

**Important**: This only works if the maintenance event hasn't already been scheduled. GKE maintenance exclusions are honored even past EoS, but may not apply to already-committed TPU host maintenance.

## Post-Maintenance Recovery

### 1. Verify Slice Recreation
```bash
kubectl get nodes -l cloud.google.com/gke-accelerator=tpu-v5-lite-podslice
kubectl get pods -n your-training-namespace
```

### 2. Resume Training
```bash
# Resume from your pre-maintenance checkpoint
python your_training_script.py --restore_checkpoint --checkpoint_path=gs://your-bucket/checkpoints/pre-maintenance
```

### 3. Validate Training Continuity
- Confirm loss values align with pre-maintenance state
- Check that all 4 slices are participating in training
- Monitor for any performance degradation

## Multislice-Specific Considerations

### Slice Placement Consistency
- **Compact placement policies**: Verify that recreated slices maintain the same physical co-location for optimal interconnect performance
- **Network topology**: Confirm RDMA/GPUDirect networking is properly configured across all slices post-recreation

### Training Framework Implications
- **JAX/XLA**: Ensure your training script handles TPU mesh recreation gracefully
- **Data parallelism**: Verify data sharding resumes correctly across the 4-slice topology
- **Gradient synchronization**: Confirm all-reduce operations work across recreated slices

## Prevention Strategy

For future training campaigns:

### 1. Use Extended Release Channel
```bash
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --release-channel extended
```
Extended channel provides up to 24 months of support and does NOT auto-upgrade minor versions (except at end of extended support). This gives maximum control over when maintenance happens.

### 2. Implement Persistent Maintenance Exclusions
```bash
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
```
This blocks disruptive upgrades while still allowing control plane security patches.

### 3. Schedule Training Campaigns Around Known Maintenance Windows
- Monitor the [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) for planned updates
- Enable scheduled upgrade notifications (72h advance warning) when available:
```bash
gcloud container clusters update CLUSTER_NAME --enable-scheduled-upgrades
```

## Key Takeaway

Unlike GPU training where individual nodes can be upgraded rolling fashion, **TPU multislice environments are all-or-nothing**. The entire training job across all 1,024 chips will restart. Your checkpoint strategy is your only protection against losing training progress.

The critical preparation is ensuring you have a recent, verified checkpoint that can resume your LLM training exactly where it left off. Everything else is secondary to that checkpoint integrity.
# TPU Multislice Maintenance Impact & Preparation

## What Will Actually Happen

**Critical impact: Your entire training job will be interrupted.** Here's the sequence:

### Cascading Restart Behavior
- **Any maintenance on ANY slice triggers restart of ALL slices** in your multislice environment
- This is a fundamental characteristic of TPU multislice - they operate as a single logical unit
- All 4 slices (1,024 TPU v5e chips total) will restart simultaneously, not rolling

### Atomic Recreation Process
- Each slice undergoes **atomic recreation** - not rolling updates like regular pods
- All pods on each slice terminate and recreate in a single step
- Your training job will lose all in-memory state (gradients, optimizer state, etc.)

### Capacity Dependency Risk
- If insufficient TPU v5e resources exist during recreation, slices will block until hardware becomes available
- This can cause **extended downtime beyond the normal maintenance window**
- TPU v5e capacity is scarce - there's real risk of extended unavailability

## Preparation Steps

### 1. Immediate Checkpoint Save
```bash
# Force a checkpoint save before the maintenance window
# (Replace with your training framework's checkpoint command)
kubectl exec -it TRAINING_POD -- python save_checkpoint.py --force

# Verify checkpoint integrity and completeness
kubectl exec -it TRAINING_POD -- python verify_checkpoint.py
```

### 2. Training Job Preparation
- **Pause new training epochs** - don't start any new work that can't complete before maintenance
- **Enable frequent checkpointing** if not already configured (every 10-15 minutes)
- **Test checkpoint resume** in a dev environment to verify your job can restart cleanly
- **Document current training progress** - step count, loss values, learning rate schedule position

### 3. Resource Monitoring
```bash
# Check TPU v5e availability in your zone before maintenance
gcloud compute tpus list --zone=ZONE --format="table(name,state,acceleratorType)"

# Monitor TPU quotas
gcloud compute project-info describe --format="yaml(quotas)" | grep -i tpu
```

### 4. Maintenance Window Planning
- **Plan for several hours of downtime** - not just the maintenance duration
- TPU multislice recreation typically takes 15-30 minutes per slice under normal conditions
- Add buffer time for potential capacity delays
- **Coordinate with your research team** - this will be a hard stop, not graceful

### 5. Post-Maintenance Recovery Plan
```bash
# After maintenance, verify all slices are healthy
kubectl get pods -l training-job=LLM_TRAINING -o wide
kubectl describe tpu SLICE_NAME

# Check TPU topology is intact
kubectl exec -it TRAINING_POD -- python -c "import jax; print(jax.device_count(), jax.local_device_count())"

# Resume from latest checkpoint
kubectl exec -it TRAINING_POD -- python train.py --resume-from-checkpoint=LATEST_CHECKPOINT
```

### 6. Alternative: Proactive Migration (Advanced)
If you have access to another TPU v5e reservation:
- Save checkpoint
- Terminate current job cleanly  
- Recreate on different hardware before maintenance
- **Only viable if you have guaranteed capacity elsewhere**

## Key Differences from Regular GKE Workloads

- **No rolling updates** - atomic recreation only
- **No surge capacity** - existing slices must be recreated in place  
- **Cascading failures** - one slice maintenance affects all slices
- **Capacity blocking** - recreation can be delayed by hardware availability

## What NOT to Do

- ❌ Don't try to use PDBs - they don't apply to TPU slice recreation
- ❌ Don't expect graceful termination - pods will be force-terminated
- ❌ Don't plan for quick recovery - budget hours, not minutes
- ❌ Don't assume maintenance exclusions help - GKE host maintenance bypasses cluster-level controls

## Bottom Line

**Treat this as a planned training interruption, not a minor maintenance event.** The entire 1,024-chip training run will restart from your last checkpoint. Ensure your checkpointing strategy is solid and plan for extended downtime.
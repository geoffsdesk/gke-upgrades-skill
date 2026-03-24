# TPU Multislice Maintenance Impact & Preparation Guide

## What Will Actually Happen During Maintenance

**Critical difference from standard GKE:** TPU multislice environments have **atomic recreation behavior** that's fundamentally different from regular node upgrades.

### TPU Multislice Maintenance Behavior:
1. **All slices restart simultaneously** - Your entire 4-slice, 1024-chip training environment will be recreated as a single atomic operation
2. **No rolling updates** - Unlike standard node pools, there's no gradual node-by-node replacement
3. **Cascading restart trigger** - A maintenance event on ANY slice triggers restart of ALL slices in the multislice environment
4. **Complete job termination** - Your LLM training job will be forcibly terminated when the slices are recreated

### Timeline Expectations:
- **Slice recreation time:** 10-20 minutes for TPU v5e slices to become available
- **Job restart overhead:** Additional 5-15 minutes for your training framework to reinitialize
- **Total downtime:** Expect 15-35 minutes of complete training halt

## Pre-Maintenance Checklist

```
TPU Multislice Maintenance Preparation
- [ ] Cluster: ___ | TPU slices: 4x v5e-256 | Training framework: ___

Critical Actions
- [ ] Enable checkpointing if not already configured
- [ ] Verify latest checkpoint integrity and accessibility
- [ ] Document current training step/epoch for restart verification
- [ ] Test checkpoint restore process in dev environment
- [ ] Confirm sufficient persistent storage quota for checkpoints
- [ ] Review training script for graceful restart behavior

Maintenance Window Planning
- [ ] Maintenance notification received with specific timing
- [ ] Checkpoint save scheduled 30 minutes before maintenance window
- [ ] Team availability confirmed during maintenance window
- [ ] Downstream consumers (evaluation, serving) notified of potential delay

Risk Mitigation
- [ ] Backup checkpoint stored in separate region/zone
- [ ] Training data pipeline verified accessible after restart
- [ ] Multi-host initialization scripts tested
- [ ] TPU topology verification commands prepared
- [ ] Monitoring/alerting configured for post-maintenance validation
```

## Preparation Commands

### Pre-Maintenance Checkpoint
```bash
# Force immediate checkpoint save (adapt to your framework)
# JAX/Flax example:
kubectl exec -it training-pod-0 -- python -c "
import checkpoint_utils
checkpoint_utils.save_checkpoint('/persistent-disk/checkpoints/', 
                                 step=current_step, 
                                 force=True)
"

# Verify checkpoint integrity
kubectl exec -it training-pod-0 -- ls -la /persistent-disk/checkpoints/
kubectl exec -it training-pod-0 -- python -c "
import checkpoint_utils
checkpoint_utils.verify_checkpoint('/persistent-disk/checkpoints/step_XXXX')
"
```

### Pre-Maintenance State Capture
```bash
# Document current training state
kubectl get pods -l app=llm-training -o wide
kubectl exec training-pod-0 -- cat /tmp/training_metrics.log | tail -n 50

# Capture TPU topology (for post-maintenance verification)
kubectl exec training-pod-0 -- python -c "
import jax
print('TPU topology:', jax.devices())
print('Process count:', jax.process_count())
print('Local device count:', jax.local_device_count())
"
```

## During Maintenance

### Expected Behavior:
- All training pods will be **terminated immediately** when TPU slices are recreated
- **No graceful shutdown** - TPU maintenance doesn't respect `terminationGracePeriodSeconds`
- Your job manager (if using GKE batch jobs) should detect the failure and restart

### Monitoring Commands:
```bash
# Watch slice recreation
watch 'kubectl get nodes -l cloud.google.com/gke-accelerator=tpu-v5litepod-256'

# Monitor pod restart
watch 'kubectl get pods -l app=llm-training'

# Check TPU resource allocation
kubectl describe node NODE_NAME | grep -A 10 "Allocated resources"
```

## Post-Maintenance Validation

### Critical Checks:
```bash
# Verify all TPU slices are healthy
kubectl get nodes -l cloud.google.com/gke-accelerator=tpu-v5litepod-256
kubectl describe nodes | grep -E "(Ready|tpu-v5)"

# Confirm training pods restarted successfully
kubectl get pods -l app=llm-training -o wide

# Validate TPU topology matches pre-maintenance
kubectl exec training-pod-0 -- python -c "
import jax
print('Post-maintenance TPU count:', len(jax.devices()))
print('Expected: 1024 TPU chips across 4 slices')
assert len(jax.devices()) == 1024, 'TPU count mismatch!'
"

# Verify checkpoint restore
kubectl logs training-pod-0 | grep -i "checkpoint\|restore\|step"

# Confirm training resumed from correct step
kubectl exec training-pod-0 -- cat /tmp/current_step.txt
```

## Training Framework Configuration

### JAX/Flax Checkpoint Strategy:
```python
# Ensure frequent checkpointing before maintenance
checkpoint_config = {
    'save_interval_steps': 100,  # More frequent during maintenance periods
    'max_to_keep': 5,
    'async_save': True,  # Don't block training
    'save_on_preemption': True
}

# Robust restart logic
def initialize_or_restore():
    if checkpoint_exists():
        step, state = restore_checkpoint()
        logger.info(f"Resumed training from step {step}")
        return step, state
    else:
        logger.info("Starting fresh training")
        return 0, initialize_fresh_state()
```

### Multi-Host Coordination:
```python
# Critical: Ensure all hosts coordinate during restart
import jax
jax.distributed.initialize()  # Must happen before any TPU operations

# Verify topology after restart
expected_chips = 1024
actual_chips = len(jax.devices())
assert actual_chips == expected_chips, f"TPU topology mismatch: {actual_chips} != {expected_chips}"
```

## Maintenance Exclusion Strategy (Limited Effectiveness)

**Important:** Maintenance exclusions have **limited effectiveness** for TPU infrastructure maintenance. Google may need to perform critical TPU infrastructure updates regardless of exclusions.

```bash
# Apply maintenance exclusion (may not prevent all TPU maintenance)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "llm-training-campaign" \
  --add-maintenance-exclusion-start-time $(date -Iseconds) \
  --add-maintenance-exclusion-end-time $(date -d '+14 days' -Iseconds) \
  --add-maintenance-exclusion-scope no_upgrades
```

## Recovery Runbook

If training doesn't resume automatically:

```bash
# 1. Check node health
kubectl get nodes -l cloud.google.com/gke-accelerator=tpu-v5litepod-256

# 2. If nodes are NotReady, check events
kubectl get events --field-selector reason=NodeNotReady

# 3. Restart training deployment
kubectl rollout restart deployment llm-training

# 4. If pods are stuck pending
kubectl describe pod training-pod-0 | grep -A 10 Events

# 5. Check TPU quota/allocation
gcloud compute tpus list --zone ZONE

# 6. Emergency: Scale down and up to force reallocation
kubectl scale deployment llm-training --replicas=0
sleep 30
kubectl scale deployment llm-training --replicas=1
```

## Key Differences from Standard GKE Maintenance

| Standard Node Maintenance | TPU Multislice Maintenance |
|---------------------------|----------------------------|
| Rolling replacement | Atomic recreation of all slices |
| Respects PDBs (1 hour) | No graceful termination |
| Surge capacity available | No surge - complete replacement |
| Per-node timing | All-at-once timing |
| Maintenance exclusions effective | Limited exclusion effectiveness |

**Bottom line:** Plan for a **complete restart** of your training job, not a gradual migration. Your checkpoint strategy is your primary defense against lost progress.
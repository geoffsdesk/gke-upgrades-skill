# TPU Multislice Maintenance Impact & Preparation Plan

## What Will Actually Happen

**Critical understanding:** Your multislice environment has fundamentally different maintenance behavior than single GPU clusters:

### Atomic Recreation Behavior
- **All 4 slices will be recreated entirely in a single step** — this is not a rolling upgrade
- **Cascading restart:** The maintenance event on ANY slice triggers restart of ALL sl4 slices simultaneously
- **Complete job termination:** Your LLM training run will be terminated and must restart from the last checkpoint

### Maintenance Timeline
- **Duration:** TPU slice recreation typically takes 15-30 minutes per slice, but all happen in parallel
- **Capacity dependency:** If insufficient TPU v5e resources exist during recreation, slices block until hardware is available — this can extend downtime significantly
- **No partial availability:** Unlike node pool upgrades, there's no "some nodes upgraded, some not" state

## Preparation Checklist

### Before Maintenance (24-48 hours prior)

```bash
# 1. Force an immediate checkpoint save
kubectl exec -it TRAINING_POD -- python save_checkpoint.py --force-save

# 2. Verify checkpoint integrity and restart capability
kubectl exec -it TRAINING_POD -- python validate_checkpoint.py --latest

# 3. Document current training state
kubectl logs TRAINING_POD | grep -E "step|loss|checkpoint" | tail -20

# 4. Check TPU slice health before maintenance
kubectl get tpu -A
kubectl describe tpu SLICE_NAME -n NAMESPACE
```

### Checkpoint Strategy (Critical)

**Your training job WILL be terminated** — ensure robust checkpointing:

```python
# Example: Force frequent checkpoints before maintenance
import checkpointing_library

# Reduce checkpoint interval temporarily
checkpoint_manager.save_interval_steps = 100  # vs normal 1000
checkpoint_manager.force_save_on_preemption = True
checkpoint_manager.validate_on_save = True
```

### Resource Reservation Verification

```bash
# Check your TPU reservation status
gcloud compute tpu-vm list --zone ZONE --format="table(name,state,networkEndpoints[0].ipAddress,acceleratorType)"

# Verify reservation has capacity for recreation
gcloud compute reservations describe TPU_RESERVATION_NAME --zone ZONE
```

## During Maintenance

### What You'll Observe

1. **Job termination notification** (if your training framework supports it)
2. **Pod eviction** from all TPU slices simultaneously  
3. **TPU slice deletion** and recreation
4. **Pod rescheduling** once new slices are ready

### Monitoring Commands

```bash
# Monitor slice recreation
watch 'kubectl get tpu -A'

# Watch for new pods scheduling
watch 'kubectl get pods -n TRAINING_NAMESPACE -l app=llm-training'

# Check events for recreation progress
kubectl get events -n TRAINING_NAMESPACE --sort-by='.lastTimestamp' | tail -10
```

## After Maintenance - Restart Procedure

### 1. Verify Infrastructure

```bash
# Confirm all TPU slices are ready
kubectl get tpu -A -o wide

# Check TPU topology is correct
kubectl describe tpu SLICE_NAME -n NAMESPACE | grep -A 10 "Network Endpoints"

# Verify pod scheduling
kubectl get pods -n TRAINING_NAMESPACE -o wide
```

### 2. Restart Training

```bash
# Restart training from latest checkpoint
kubectl apply -f training-job-restart.yaml

# Monitor restart logs
kubectl logs -f TRAINING_POD | grep -E "checkpoint|restored|step"
```

### 3. Validate Training Continuation

```python
# In your training script - verify checkpoint restore
def validate_restart():
    current_step = checkpoint_manager.latest_step()
    print(f"Resumed from step: {current_step}")
    
    # Verify model state
    assert model.training_step == current_step
    assert optimizer.state_dict() is not None
```

## Risk Mitigation

### Extended Downtime Scenarios

**If TPU capacity is constrained:**
- Slice recreation may be delayed hours/days until v5e hardware is available
- Consider having a **secondary training setup** ready (different zone/region)
- Monitor GCP status page for TPU availability issues

### Checkpoint Protection

```bash
# Backup checkpoints to persistent storage BEFORE maintenance
gsutil -m cp -r gs://TRAINING_BUCKET/checkpoints gs://BACKUP_BUCKET/checkpoints-$(date +%Y%m%d)

# Verify backup integrity
gsutil ls -la gs://BACKUP_BUCKET/checkpoints-$(date +%Y%m%d)/
```

## Key Differences from Standard GKE Upgrades

| Standard Node Upgrades | TPU Multislice Maintenance |
|------------------------|----------------------------|
| Rolling, node-by-node | Atomic, all-slices-at-once |
| Pods may survive on other nodes | All training pods terminated |
| Partial availability maintained | Complete service interruption |
| PDBs provide some protection | PDBs cannot prevent slice recreation |
| 1-hour drain timeout | Immediate termination |

## Maintenance Window Planning

**Schedule during training gaps:** Unlike GPU node upgrades where you might pause new job submissions, TPU multislice maintenance requires **complete training downtime**. Plan this during:
- Natural checkpoint boundaries (end of epoch)
- Scheduled model evaluation periods  
- Weekend/off-peak hours when team availability is lower

**Estimated total downtime:** 30-60 minutes (slice recreation + job restart + validation), assuming TPU capacity is available immediately.

This is fundamentally different from standard GKE maintenance — your 1024-chip training job will experience complete interruption, not graceful migration. The checkpoint strategy is your primary protection mechanism.
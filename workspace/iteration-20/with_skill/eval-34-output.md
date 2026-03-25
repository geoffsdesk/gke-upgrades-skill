# TPU Multislice Maintenance Impact & Preparation Guide

## What Will Actually Happen

**Critical understanding:** TPU multislice environments have fundamentally different maintenance behavior than GPU clusters:

### Atomic Recreation Behavior
- **All 4 slices will be recreated simultaneously** - this is not a rolling update
- **Complete training job termination** - your LLM training will stop entirely and need to restart from the last checkpoint
- **Cascading restart trigger** - maintenance on ANY slice in your multislice environment triggers restart of ALL slices
- **Duration:** Expect 15-30 minutes of downtime while slices are recreated and pods restart

### Capacity Risk
- If insufficient TPU v5e resources exist during recreation, slices will block until hardware becomes available
- This could extend downtime from minutes to hours or longer
- **No gradual degradation** - it's either all slices available or training can't proceed

## Pre-Maintenance Preparation Checklist

```
TPU Multislice Maintenance Preparation
- [ ] Checkpoint strategy verified and tested
- [ ] Training resumption workflow documented
- [ ] Capacity confirmation with Google Cloud (if possible)
- [ ] Monitoring and alerting configured
- [ ] Team coordination planned

Critical Actions (24-48 hours before maintenance):
- [ ] Force an immediate checkpoint save in your training code
- [ ] Verify checkpoint integrity and resumption capability
- [ ] Document exact training state (epoch, step, loss, etc.)
- [ ] Scale down any non-essential workloads to maximize available TPU quota
- [ ] Coordinate with other teams who might be competing for TPU resources

Day-of Preparation (2-4 hours before):
- [ ] Trigger final checkpoint save
- [ ] Gracefully stop training job
- [ ] Verify all checkpoint data is safely stored (GCS, Persistent Volumes)
- [ ] Put monitoring in place to detect when slices are recreated
```

## Training Job Protection Strategy

### Checkpoint Management
Your training job WILL be terminated. Focus on checkpoint resilience:

```python
# Ensure frequent, reliable checkpointing
# Save every N steps, not just at epoch boundaries
checkpoint_frequency = 100  # Adjust based on your step duration

# Verify checkpoint integrity before maintenance
def verify_checkpoint(checkpoint_path):
    # Load and validate model state
    # Confirm optimizer state preservation
    # Test resumption from this checkpoint
```

### Graceful Pre-Maintenance Shutdown
**2-4 hours before scheduled maintenance:**

```bash
# Gracefully stop your training job (don't wait for forced termination)
kubectl scale deployment llm-training --replicas=0

# Or send SIGTERM to training pods to trigger checkpoint save
kubectl delete pod TRAINING_POD_NAME --grace-period=300
```

## Post-Maintenance Recovery

### Validation Steps
```bash
# Check all TPU slices are healthy
kubectl get nodes -l cloud.google.com/gke-accelerator=tpu-v5litepod
kubectl get pods -l app=tpu-training -o wide

# Verify TPU topology is intact
kubectl exec -it TRAINING_POD -- python -c "
import jax
print(f'TPU devices: {jax.device_count()}')
print(f'Local devices: {jax.local_device_count()}')
"
```

### Training Resumption
```bash
# Restart training from latest checkpoint
kubectl apply -f training-deployment.yaml

# Monitor training resumption
kubectl logs -f TRAINING_POD_NAME
```

## Minimizing Impact

### Maintenance Timing Control (Limited)
```bash
# TPU maintenance windows are more restricted than regular GKE
gcloud container clusters update CLUSTER_NAME \
  --maintenance-window-start "2024-01-01T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"

# Note: TPU maintenance may not fully respect these windows
# due to hardware constraints
```

### Checkpoint Optimization
- **Increase checkpoint frequency** leading up to maintenance
- **Implement incremental checkpointing** to reduce save time
- **Use asynchronous checkpoint saves** to minimize training interruption
- **Store checkpoints in Google Cloud Storage** (not just local PVs) for resilience

## Risk Mitigation

### Before Maintenance
```bash
# Verify TPU quota and reservations
gcloud compute tpus list --zone=ZONE
gcloud compute reservations list --filter="name:tpu"

# Check for competing TPU usage in your project
gcloud compute tpus list --format="table(name,state,acceleratorType,zone)"
```

### Alternative Architecture (Future Consideration)
For mission-critical training that can't tolerate full restarts:
- Consider **multi-region TPU distribution** (if your model supports it)
- Evaluate **smaller slice sizes** with more frequent checkpointing
- Implement **training state replication** across independent environments

## Expected Timeline
- **T-72h:** Maintenance notification (if enabled)
- **T-4h:** Stop accepting new training iterations, force checkpoint
- **T-30min:** Gracefully terminate training job
- **T-0:** Maintenance begins, all slices recreate
- **T+30min:** Slices available, restart training
- **T+45min:** Training resumed from checkpoint (assuming no capacity issues)

## Key Contacts & Escalation
- Monitor GKE operations: `gcloud container operations list --cluster=CLUSTER --zone=ZONE`
- If slices don't recreate within 1 hour, engage Google Cloud Support with:
  - Cluster name and zone
  - TPU slice configuration
  - Training job requirements
  - Business impact details

**Bottom line:** Plan for complete training interruption. The multislice environment cannot be partially maintained - it's all-or-nothing recreation. Your preparation should focus entirely on checkpoint resilience and rapid recovery rather than trying to maintain continuous training.
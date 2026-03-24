# TPU Multislice Maintenance Impact & Preparation

## What Will Actually Happen

Your training job will experience a **complete restart**. Here's the specific behavior for TPU multislice environments:

### Atomic Recreation Behavior
- **All 4 slices will be recreated simultaneously** in a single atomic operation
- This is NOT a rolling upgrade - TPU multislice pods cannot be upgraded in-place
- **Cascading restart**: The maintenance event on ANY slice triggers restart of ALL slices in your multislice environment
- Total downtime: typically 10-20 minutes for slice recreation + your job restart time

### Capacity Risk
- If insufficient TPU v5e capacity exists during recreation, slices will block until hardware becomes available
- This can extend downtime from minutes to hours or longer
- TPU capacity is more constrained than regular compute, especially for large slice configurations like 4x256

## Preparation Checklist

```
TPU Multislice Maintenance Preparation
- [ ] Checkpoint saved at known-good state
- [ ] Checkpoint location accessible from new slices (GCS, not local storage)
- [ ] Training resume logic tested in staging environment
- [ ] Current training progress documented (step count, loss, etc.)
- [ ] Monitoring/alerting configured for job restart detection
- [ ] Team availability during maintenance window for manual intervention if needed
```

## Critical Actions

### 1. Force Checkpoint Now
```bash
# If your training framework supports it, trigger immediate checkpoint
# Example for common frameworks:
kubectl exec -it training-pod-0 -- python -c "
import signal
import os
os.kill(os.getppid(), signal.SIGUSR1)  # Trigger checkpoint in many frameworks
"
```

### 2. Verify Checkpoint Integrity
```bash
# Ensure checkpoint is complete and accessible
gsutil ls gs://your-checkpoint-bucket/latest/
# Test restore in a small environment if possible
```

### 3. Document Current State
```bash
# Capture current training metrics
kubectl logs training-pod-0 | tail -50 > pre-maintenance-state.log
# Note: step count, loss, learning rate, etc.
```

## Timeline Expectations

**Before maintenance:**
- GKE sends notifications ~7 days in advance
- You have until the maintenance window to prepare

**During maintenance:**
- All 4 slices recreated simultaneously (~10-20 min)
- New slices may land in different physical locations
- Network topology (if using custom placement) may change

**After maintenance:**
- Manual job restart required
- Checkpoint restore from GCS
- Validation of training resumption

## Restart Strategy

### Automated Restart (Recommended)
Configure your training Job/Deployment to automatically restart from the latest checkpoint:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: llm-training-restart
spec:
  template:
    spec:
      restartPolicy: OnFailure
      containers:
      - name: trainer
        image: your-training-image
        command: 
        - python
        - train.py
        - --resume-from-checkpoint
        - gs://your-checkpoint-bucket/latest
        nodeSelector:
          cloud.google.com/gke-tpu-topology: 4x4x4x4  # Your slice topology
```

### Manual Restart
If you prefer manual control:
1. Wait for all slices to be Ready
2. Verify checkpoint accessibility
3. Launch training job with resume flag
4. Monitor initial steps for correct resumption

## Risk Mitigation

### Capacity Planning
- TPU v5e capacity can be constrained
- Consider having a backup plan with smaller slice configuration
- Monitor GCP status page during maintenance window

### Checkpoint Strategy
- **Multiple checkpoints**: Keep last 3-5 checkpoints, not just latest
- **Frequent saves**: Increase checkpoint frequency before maintenance
- **Validation**: Test checkpoint restore in smaller environment if possible

### Monitoring Setup
```bash
# Set up alerts for slice readiness
kubectl get pods -l job-name=training -o wide --watch

# Monitor TPU slice status
gcloud compute tpus tpu-vm describe your-slice-name --zone=your-zone
```

## What NOT to Expect

- **No graceful migration**: Unlike regular pods, TPU slices cannot live-migrate
- **No partial availability**: All slices go down together, no gradual transition
- **No automatic job restart**: Your training framework won't automatically resume unless explicitly configured

## Post-Maintenance Validation

```bash
# Verify all slices are healthy
kubectl get pods -l app=training -o wide

# Check TPU topology is correct
kubectl describe node -l cloud.google.com/gke-accelerator=tpu-v5-lite

# Validate training resumption
kubectl logs training-pod-0 | grep -i "restored\|checkpoint\|resumed"

# Monitor first few training steps for correctness
kubectl logs -f training-pod-0 | grep "step\|loss"
```

The key insight: **plan for a complete restart, not an upgrade**. Your preparation should focus on clean checkpointing and automated restart rather than trying to minimize disruption during the maintenance event itself.
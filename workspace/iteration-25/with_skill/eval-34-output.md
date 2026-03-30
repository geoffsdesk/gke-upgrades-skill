# TPU Multislice Maintenance Impact & Preparation Guide

## What Will Actually Happen

**Complete Training Interruption:**
- **ALL 4 slices will restart simultaneously** when maintenance begins - this is not a rolling update
- TPU multislice environments have "atomic recreation" behavior - any maintenance event affecting one slice triggers restart of the entire multislice environment
- Your training job will be **completely terminated** and must be restarted from the last checkpoint
- **No graceful termination** - TPU slices are recreated entirely, not drained like regular nodes

**Downtime Characteristics:**
- **Minimum downtime:** 15-30 minutes for slice recreation + job restart
- **Potential extended downtime:** If insufficient TPU v5e capacity exists during recreation, slices will block until hardware becomes available - this could be hours or longer
- **Cascading impact:** Even if maintenance is scheduled for just one slice, all connected slices restart

## Immediate Preparation Steps

### 1. Force Checkpoint Before Maintenance
```bash
# If your training framework supports it, trigger immediate checkpoint
kubectl exec -it TRAINER_POD -c CONTAINER_NAME -- python checkpoint_now.py

# Or send SIGUSR1 if your training code handles it
kubectl exec TRAINER_POD -- kill -USR1 1
```

### 2. Verify Checkpoint Integrity
```bash
# Check your checkpoint storage (GCS bucket, Persistent Disk, etc.)
gsutil ls -la gs://YOUR_TRAINING_BUCKET/checkpoints/
# Verify latest checkpoint is complete and not corrupted
```

### 3. Prepare Job Restart Automation
Create a restart script that:
- Detects when all TPU pods are Ready
- Automatically resumes training from latest checkpoint
- Handles any TPU topology verification

```bash
# Example monitoring script
kubectl get pods -l job=tpu-training -o jsonpath='{.items[*].status.phase}' | grep -q "Running"
```

## Multislice-Specific Risks

### Capacity Dependency Risk
- **4 x 256 TPU v5e chips = massive capacity requirement**
- If Google doesn't have 1,024 TPU v5e chips available in your zone during recreation, you'll experience extended downtime
- TPU capacity is more constrained than GPU - no surge capacity exists

### Topology Preservation
- Verify replacement slices maintain the same TPU topology and interconnect
- Check that slice IDs and worker assignments remain consistent post-recreation

## Maintenance Window Strategy

### Option A: Controlled Restart (Recommended)
```bash
# 1. Pause new training epochs
# 2. Wait for current epoch to complete and checkpoint
# 3. Scale training job to 0 replicas BEFORE maintenance window
kubectl scale deployment tpu-trainer --replicas=0

# 4. Let GKE perform maintenance on empty slices
# 5. Restart training after maintenance completes
```

### Option B: Accept Forced Interruption
- Let maintenance happen mid-training
- Rely on checkpoint recovery (ensure checkpoints are frequent enough)
- Risk: potential loss of work since last checkpoint

## Recovery Planning

### Post-Maintenance Validation Script
```bash
#!/bin/bash
# Check all TPU slices are ready
kubectl get pods -l component=tpu-slice --no-headers | wc -l
# Should equal your expected slice count (4)

# Verify TPU topology
kubectl exec TPU_POD -- python -c "
import jax
print(f'TPU devices: {jax.device_count()}')
print(f'TPU hosts: {jax.process_count()}')
"

# Check slice interconnect
kubectl logs TPU_POD | grep -i "slice.*connected"
```

### Restart Command Template
```bash
# Resume training from checkpoint
kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: tpu-training-resume
spec:
  template:
    spec:
      containers:
      - name: trainer
        image: YOUR_TRAINING_IMAGE
        env:
        - name: RESUME_FROM_CHECKPOINT
          value: "gs://YOUR_BUCKET/checkpoints/latest"
        - name: TPU_SLICE_COUNT
          value: "4"
EOF
```

## Timeline Recommendations

**72 hours before:** Force checkpoint, verify backup integrity
**24 hours before:** Test restart procedure in staging environment
**2 hours before:** Pause new training, checkpoint, scale to 0
**During maintenance:** Monitor for slice recreation completion
**After maintenance:** Validate topology, restart training

## Key Monitoring

Watch these metrics during and after maintenance:
- TPU utilization returning to baseline
- Training loss continuity from checkpoint
- Inter-slice communication latency
- Any TPU topology warnings in logs

**Critical Point:** Unlike regular GKE node upgrades that can be gradual, TPU multislice maintenance is always atomic and disruptive. Plan for complete training interruption and ensure your checkpointing strategy can handle it.
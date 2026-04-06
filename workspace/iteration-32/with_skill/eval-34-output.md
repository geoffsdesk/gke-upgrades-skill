# TPU Multislice Maintenance Impact & Preparation

## What will actually happen during the maintenance event

**Critical difference from GPU clusters:** TPU multislice environments have fundamentally different upgrade behavior than standard node pools:

### Atomic recreation behavior
- **All 4 slices will be recreated simultaneously** — not rolling upgrades
- Each 256-chip slice is treated as a single atomic unit that gets recreated entirely
- **Cascading restart:** A maintenance event on ANY slice triggers restart of ALL slices in your multislice environment
- Your training job will be **completely terminated** across all 1,024 chips at once

### No graceful migration
- Unlike standard node pools where pods can migrate during surge upgrades, TPU slices cannot be partially drained
- All pods on all slices restart simultaneously when maintenance begins
- Training state in memory is completely lost unless checkpointed

## Preparation steps (execute before maintenance window)

### 1. Save training checkpoint immediately
```bash
# Trigger manual checkpoint in your training code
# Example for JAX/Flax training:
kubectl exec -n NAMESPACE POD_NAME -- python -c "
import signal
import os
# Send SIGUSR1 or your checkpoint trigger signal to training process
os.kill(TRAINING_PID, signal.SIGUSR1)
"

# Verify checkpoint saved to persistent storage
kubectl exec -n NAMESPACE POD_NAME -- ls -la /checkpoint/path/
```

### 2. Gracefully stop training job
```bash
# Scale down training deployment to avoid restart loops during maintenance
kubectl scale deployment TRAINING_DEPLOYMENT -n NAMESPACE --replicas=0

# Or delete the job entirely if using Jobs/CronJobs
kubectl delete job TRAINING_JOB -n NAMESPACE
```

### 3. Verify TPU resource availability
```bash
# Check TPU quota and reservations
gcloud compute tpus queued-resources list --zone ZONE

# Verify your reservation is still active
gcloud compute reservations describe TPU_RESERVATION_NAME --zone ZONE
```

### 4. Plan for extended downtime
- **Capacity dependency:** If insufficient TPU v5e resources exist during recreation, slices will block until hardware becomes available
- TPU multislice recreation can take **30+ minutes** even when resources are available
- Budget **1-3 hours** for full environment recovery in worst case

## During maintenance (what to expect)

### Timeline
1. **T+0:** GKE begins maintenance — all slices marked for recreation
2. **T+5-15 min:** All pods terminated, slices begin deletion
3. **T+15-45 min:** New slices provisioning (depends on TPU availability)
4. **T+30-60 min:** Slices ready, pods can be scheduled
5. **T+45-90 min:** Training job restarted and resumed from checkpoint

### Monitoring commands during maintenance
```bash
# Watch slice status
kubectl get nodes -l cloud.google.com/gke-tpu-accelerator=tpu-v5-lite-podslice

# Check TPU resource provisioning
gcloud compute tpus queued-resources list --zone ZONE

# Monitor pod scheduling
kubectl get pods -n NAMESPACE -o wide
```

## Post-maintenance recovery

### 1. Verify all slices are healthy
```bash
# All nodes should show Ready
kubectl get nodes -l cloud.google.com/gke-tpu-accelerator=tpu-v5-lite-podslice

# Check TPU topology is intact
kubectl describe nodes | grep "cloud.google.com/gke-tpu"
```

### 2. Restart training from latest checkpoint
```bash
# Scale training deployment back up
kubectl scale deployment TRAINING_DEPLOYMENT -n NAMESPACE --replicas=1

# Verify training resumed from checkpoint (not epoch 0)
kubectl logs -n NAMESPACE -f TRAINING_POD | grep -E "(checkpoint|epoch|step)"
```

### 3. Validate training performance
```bash
# Check training throughput returns to baseline
kubectl logs TRAINING_POD | grep "tokens/sec\|examples/sec\|steps/sec"

# Monitor for any TPU communication issues
kubectl logs TRAINING_POD | grep -E "(TPU|XLA|JAX)" | grep -i error
```

## Key recommendations

### Checkpoint strategy
- **Increase checkpoint frequency** leading up to maintenance (every 15-30 minutes instead of hourly)
- Use **asynchronous checkpointing** if possible to minimize training interruption
- Store checkpoints on **persistent volumes** or Cloud Storage, never local TPU memory

### Maintenance window planning
- **Don't schedule maintenance during critical training phases** (model convergence, final epochs)
- TPU multislice maintenance should happen during planned training gaps
- Consider **pausing training campaigns** entirely during maintenance periods

### Monitoring setup
```bash
# Set up alerts for TPU slice availability
gcloud alpha monitoring policies create --policy-from-file tpu-alert-policy.yaml

# Monitor training job health
kubectl create -f training-health-check.yaml
```

## What makes TPU multislice different

Unlike standard GKE node upgrades where surge/blue-green strategies minimize disruption:
- **No rolling updates** — atomic recreation only
- **No surge capacity** — can't run old + new slices simultaneously  
- **Higher blast radius** — one maintenance event affects entire training run
- **Longer recovery time** — slice recreation takes much longer than standard node replacement

**Bottom line:** Treat TPU multislice maintenance as a planned outage. Always checkpoint before maintenance windows and never run critical training during maintenance periods.
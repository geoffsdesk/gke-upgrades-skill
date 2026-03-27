# TPU Multislice Maintenance Impact & Preparation

## What will happen to your training job

**Complete training interruption with atomic recreation:**
- **All 4 slices will restart simultaneously** — TPU multislice maintenance is atomic, not rolling
- **Cascading restart behavior:** A maintenance event on ANY slice triggers restart of ALL slices in the multislice environment
- **All pods across all slices terminate and recreate** — there's no graceful migration for TPU multislice
- **Training job will be completely interrupted** — expect full stop/restart cycle

**Timeline expectations:**
- **Maintenance duration:** ~4 hours per slice, but since all slices restart together, total downtime is ~4 hours (not 16 hours)
- **Capacity dependency risk:** If insufficient TPU v5e capacity exists during recreation, slices will block until hardware becomes available — this could extend downtime significantly beyond 4 hours

## Critical preparation steps

### 1. Training checkpoint strategy (URGENT)

```bash
# Verify checkpoint frequency and location
kubectl describe job/deployment TRAINING_JOB_NAME
# Look for checkpoint interval and storage path

# Ensure checkpoints are saving to persistent storage (GCS)
# NOT local TPU memory or ephemeral storage
```

**Recommendations:**
- **Increase checkpoint frequency** before the maintenance window (e.g., every 15-30 minutes instead of hourly)
- **Force a checkpoint save** immediately before the maintenance window
- **Verify checkpoint integrity** — test that you can resume from the latest checkpoint
- **Use GCS for checkpoint storage** (never local storage that disappears with the pods)

### 2. Maintenance window coordination

```bash
# Check when maintenance is scheduled
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Apply maintenance exclusion if you need to delay (max 30 days)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "tpu-training-campaign" \
  --add-maintenance-exclusion-start-time YYYY-MM-DDTHH:MM:SSZ \
  --add-maintenance-exclusion-end-time YYYY-MM-DDTHH:MM:SSZ \
  --add-maintenance-exclusion-scope no_upgrades
```

**Key constraint:** The "no upgrades" exclusion can only defer for 30 days maximum. If your training run extends beyond that, you'll need to plan for the interruption.

### 3. Workload configuration for restart

```yaml
# Ensure your training job can resume from checkpoints
apiVersion: batch/v1
kind: Job
spec:
  template:
    spec:
      restartPolicy: OnFailure  # Critical for TPU jobs
      containers:
      - name: training
        env:
        - name: CHECKPOINT_PATH
          value: "gs://your-bucket/checkpoints/"  # Must be GCS
        - name: RESUME_FROM_CHECKPOINT
          value: "true"
        resources:
          limits:
            google.com/tpu: "256"  # Per slice
```

### 4. Pre-maintenance validation checklist

```markdown
Pre-Maintenance Checklist - TPU Multislice Training

Training State
- [ ] Latest checkpoint saved and verified (test resumption in dev)
- [ ] Checkpoint frequency increased to 15-30 minute intervals
- [ ] All checkpoints stored in GCS (not local storage)
- [ ] Training progress documented (current epoch, loss, etc.)
- [ ] Resume-from-checkpoint logic tested and working

Infrastructure
- [ ] TPU v5e quota verified sufficient for slice recreation (1024 chips total)
- [ ] No competing TPU reservations during maintenance window
- [ ] Maintenance window scheduled during acceptable downtime
- [ ] On-call team notified of expected 4+ hour training interruption

Monitoring
- [ ] Training metrics baseline captured
- [ ] Alert thresholds adjusted for expected restart
- [ ] Post-restart validation plan documented
```

### 5. Post-maintenance restart procedure

```bash
# After maintenance completes, verify TPU slices are healthy
kubectl get pods -l workload-type=tpu -o wide

# Check TPU topology is intact
kubectl describe pods TRAINING_POD_NAME | grep -A 10 "google.com/tpu"

# Monitor training resumption from checkpoint
kubectl logs -f TRAINING_POD_NAME --since=10m
```

## Alternative strategies for future runs

### For training campaigns longer than 30 days:
1. **Planned checkpoint breaks:** Design training to have natural pause points (end of epochs) where maintenance can happen with minimal waste
2. **Dedicated training node pools:** Use separate node pools with Extended release channel for maximum maintenance control (up to 24 months support)
3. **Multi-region training:** Split training across regions to reduce blast radius of regional maintenance events

### Maintenance exclusion strategy for ongoing campaigns:
```bash
# For long training campaigns, chain maintenance exclusions
# (max 3 per cluster, must leave 48h available in any 32-day window)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "training-phase-1" \
  --add-maintenance-exclusion-start-time 2024-01-01T00:00:00Z \
  --add-maintenance-exclusion-end-time 2024-01-30T23:59:59Z \
  --add-maintenance-exclusion-scope no_upgrades
```

**Important:** This only delays GKE-initiated maintenance. Google Cloud infrastructure maintenance (host-level TPU maintenance) cannot be excluded and will still cause restarts.

## Key takeaways

1. **Plan for complete restart** — no graceful migration exists for TPU multislice
2. **Checkpoint frequently** — your only protection against lost training progress
3. **Test resume logic** — verify you can actually restart from checkpoints before the maintenance window
4. **Budget 4+ hours downtime** — potentially longer if TPU capacity is constrained
5. **Use GCS for checkpoints** — never rely on local storage that vanishes with pods

The maintenance is unavoidable, but with proper checkpointing and restart logic, your training can resume exactly where it left off.
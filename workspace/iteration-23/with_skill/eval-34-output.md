# TPU Multislice Maintenance Impact & Preparation

## What Will Actually Happen

**Critical understanding**: TPU multislice maintenance is fundamentally different from regular node upgrades. Your training job will experience:

### 1. Complete Environment Restart
- **All 4 slices (1,024 TPU chips total) will restart simultaneously**
- This is NOT a rolling upgrade — TPU multislice environments are recreated atomically
- Your training job will be **completely interrupted** and must restart from the last checkpoint

### 2. Cascading Impact
- A maintenance event on **ANY** slice triggers restart of **ALL** slices in your multislice environment
- Even if only 1 of your 4 slices needs maintenance, all 1,024 chips restart together
- This is by design — multislice training requires synchronized hardware state

### 3. Extended Downtime Risk
- **Capacity dependency**: If insufficient TPU v5e resources exist during recreation, your slices will block until hardware becomes available
- Unlike CPU/GPU nodes where individual instances restart, TPU slices must be recreated as complete units
- Downtime could extend from minutes to hours depending on TPU availability in your zone

## Preparation Steps

### 1. Checkpoint Strategy (Critical)
```bash
# Verify your training job has recent checkpointing enabled
# Recommend checkpoint frequency: every 30-60 minutes for multislice jobs

# Check your current checkpoint configuration
kubectl describe job YOUR_TRAINING_JOB
# Look for checkpoint frequency and storage location
```

**Before maintenance window:**
- Force a checkpoint save immediately before the maintenance window
- Verify checkpoint integrity and can be loaded successfully
- Ensure checkpoint storage (GCS bucket) has sufficient space and proper permissions

### 2. Training Job Configuration
```bash
# Ensure your job can automatically resume from checkpoint
# Add restart policy for the training pod:
kubectl patch job YOUR_TRAINING_JOB -p '{"spec":{"template":{"spec":{"restartPolicy":"OnFailure"}}}}'

# Or if using a training operator (like Kubeflow), ensure it has resume logic
```

### 3. Maintenance Exclusion (Limited Help)
```bash
# Apply "no upgrades" exclusion to delay by up to 30 days
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "tpu-training-freeze" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time $(date -u -d '+30 days' +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-scope no_upgrades
```

**Important**: This only defers maintenance, doesn't prevent it. Use this time to reach a natural checkpoint/stopping point in your training.

### 4. Monitor TPU Capacity
```bash
# Check TPU quota and current utilization in your zone
gcloud compute tpu-vm instances list --zone ZONE
gcloud compute project-info describe --format="table(quotas.metric,quotas.limit,quotas.usage)"
```

## Recommended Timeline

### 3-7 Days Before Maintenance
- [ ] Enable more frequent checkpointing (every 30 minutes)
- [ ] Test checkpoint resume logic in a dev environment
- [ ] Apply maintenance exclusion if you need time to reach a training milestone

### 1-2 Hours Before Window
- [ ] Force checkpoint save
- [ ] Verify checkpoint file integrity
- [ ] Scale down any non-critical workloads in the cluster to maximize TPU availability for restart
- [ ] Have on-call team ready to monitor restart

### During Maintenance
- [ ] Monitor cluster status: `kubectl get nodes -l cloud.google.com/gke-accelerator=tpu-v5-litepod`
- [ ] Watch for TPU slice recreation
- [ ] Be prepared for extended wait if TPU capacity is constrained

### After Maintenance
- [ ] Verify all 4 slices are healthy and registered
- [ ] Confirm training job auto-resumed from latest checkpoint
- [ ] Validate training metrics show proper continuation (loss didn't jump, learning rate correct, etc.)

## Key Differences from Regular Node Maintenance

| Regular Nodes | TPU Multislice |
|---------------|----------------|
| Rolling updates, one node at a time | Atomic restart of entire multislice |
| Pods can migrate to other nodes | No migration possible — complete restart required |
| Graceful drain with terminationGracePeriodSeconds | Immediate termination, no drain period |
| Individual node capacity constraints | Entire slice capacity must be available |

## Monitoring Commands

```bash
# Monitor TPU node status
kubectl get nodes -l cloud.google.com/gke-accelerator=tpu-v5-litepod -o wide

# Check training job status
kubectl get jobs -n YOUR_NAMESPACE
kubectl describe job YOUR_TRAINING_JOB

# Monitor TPU-related events
kubectl get events --field-selector involvedObject.kind=Node,reason=NodeNotReady
```

## Recovery Expectations

- **Best case**: 5-15 minutes for slice recreation + job restart
- **Typical case**: 20-45 minutes including checkpoint loading
- **Worst case**: 1-4 hours if TPU capacity is constrained in your zone

**Bottom line**: Plan for your training job to restart completely. The maintenance event is not something your job can "ride through" — it's a mandatory restart of your entire 1,024-chip training environment.
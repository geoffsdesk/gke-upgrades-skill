# TPU Multislice Maintenance Impact & Preparation

## What will happen to your training job

**Complete training interruption is guaranteed.** TPU multislice environments have fundamentally different maintenance behavior than regular GPU clusters:

### Atomic recreation behavior
- **All 4 slices will restart simultaneously** — TPU multislice maintenance is atomic, not rolling
- **Cascading restart:** A maintenance event on ANY slice triggers restart of ALL slices in your multislice environment
- **Total pod restart:** All training pods across all 1,024 chips will terminate and restart from scratch
- **No graceful migration:** Unlike CPU nodes, TPU slices cannot live-migrate and must be recreated entirely

### Timeline expectations
- **Maintenance duration:** ~4 hours for slice recreation + pod startup time
- **Capacity dependency:** If insufficient TPU v5e-256 resources exist during recreation, slices will block until hardware becomes available
- **Extended downtime risk:** In high-demand periods, you could face hours to days of additional delay waiting for TPU capacity

## Preparation checklist

### Before maintenance window

```markdown
TPU Multislice Maintenance Prep
- [ ] **Critical:** Save training checkpoint immediately before maintenance window
- [ ] Verify checkpoint completeness and resumability in staging environment  
- [ ] Document current training step/epoch for clean restart
- [ ] Scale down any non-essential workloads to free TPU quota for faster slice recreation
- [ ] Coordinate with Google Cloud TAM if you have dedicated TPU reservations
- [ ] Set up monitoring for slice recreation progress
- [ ] Brief training team on expected 4+ hour downtime
```

### Checkpoint verification commands
```bash
# Verify recent checkpoints exist and are complete
gsutil ls -l gs://YOUR_CHECKPOINT_BUCKET/checkpoints/ | tail -10

# Test checkpoint loading in a staging environment
kubectl run checkpoint-test --image=YOUR_TRAINING_IMAGE \
  --restart=Never -- python verify_checkpoint.py --checkpoint_path=gs://YOUR_BUCKET/latest

# Document current training state
kubectl logs -f TRAINING_POD_NAME | grep -E "step|epoch|loss" | tail -5
```

### During maintenance
- **Monitor slice status:**
```bash
kubectl get nodes -l cloud.google.com/gke-accelerator=tpu-v5-litepod-256
kubectl get pods -l job-name=YOUR_TRAINING_JOB -o wide
```

- **Watch for slice availability:**
```bash
# Check TPU slice recreation progress
gcloud container node-pools describe tpu-nodepool \
  --cluster=CLUSTER_NAME --zone=ZONE \
  --format="table(status, instanceGroupUrls)"
```

### After maintenance
1. **Verify all slices are Ready:** All 4 TPU v5e-256 slices must show `Ready` status
2. **Confirm pod scheduling:** Training pods should schedule across all available slices
3. **Resume from checkpoint:** Restart training job pointing to your pre-maintenance checkpoint
4. **Validate training metrics:** Confirm loss curves and convergence continue smoothly

## Key differences from GPU maintenance

| Aspect | GPU clusters | TPU multislice |
|--------|-------------|----------------|
| **Restart pattern** | Rolling (one node at a time) | Atomic (all slices simultaneously) |
| **Capacity impact** | Temporary capacity reduction | Complete environment unavailable |
| **Graceful termination** | Respects terminationGracePeriodSeconds | Hard restart, no grace period |
| **Rollback option** | Can pause/resume upgrades | No rollback — maintenance completes or fails |
| **Cross-slice impact** | Isolated to specific nodes | Any slice maintenance affects entire environment |

## Maintenance exclusions won't help

**Important:** Standard GKE maintenance exclusions ("no upgrades", "no minor upgrades") do NOT block underlying TPU host maintenance. Google's TPU infrastructure requires periodic maintenance regardless of GKE cluster policies. 

The maintenance notification you received is likely **infrastructure-level TPU maintenance**, not a GKE version upgrade. This cannot be deferred through cluster maintenance policies.

## Risk mitigation for future

1. **Checkpoint frequency:** Increase checkpoint saves to every 15-30 minutes during known maintenance periods
2. **Multi-region training:** Consider splitting training across regions to reduce single-point-of-failure
3. **Reservation strategy:** Work with your Google Cloud TAM on dedicated TPU reservations to ensure capacity during recreation
4. **Monitoring setup:** Implement alerts for TPU slice health and training job status

**Bottom line:** Plan for 4+ hours of complete training downtime. Ensure your checkpoint strategy can handle this interruption gracefully, and communicate the maintenance impact to your training team well in advance.
# TPU Multislice Maintenance Impact & Preparation

## What Will Actually Happen

**Atomic recreation of ALL slices:** Your TPU multislice environment will undergo complete recreation, not rolling updates. Here's the critical difference from regular GKE upgrades:

- **All 4 slices restart simultaneously** — TPU multislice treats the entire environment as one atomic unit
- **Cascading restart behavior** — a maintenance event on ANY single slice triggers restart of ALL slices in your multislice environment
- **Complete job termination** — your LLM training job will be forcibly stopped and must restart from the last checkpoint

This is fundamentally different from regular node upgrades where pods migrate gradually. TPU multislice maintenance is an all-or-nothing event.

## Capacity Risk Assessment

**High risk of extended downtime:** During recreation, if insufficient TPU v5e capacity exists in your zone, the slices will block until hardware becomes available. With 1,024 chips (4×256), you're consuming significant TPU capacity that may not be immediately available for recreation.

**Reservation check:** If you have a TPU reservation, verify it covers your full capacity (1,024 chips). If you're using on-demand capacity, expect potential delays in slice recreation.

## Pre-Maintenance Preparation Checklist

```
TPU Multislice Maintenance Checklist

Training Job Protection
- [ ] Force checkpoint immediately before maintenance window
- [ ] Verify checkpoint completeness and integrity
- [ ] Test checkpoint restore on a smaller slice to confirm viability
- [ ] Document current training step/epoch for restart reference
- [ ] Save model state, optimizer state, and data loader position

Capacity Planning
- [ ] Confirm TPU v5e reservation covers 1,024 chips (if using reservations)
- [ ] Check quota limits: `gcloud compute tpus quota list --filter="metric:tpus"`
- [ ] Identify backup zones with TPU v5e availability (for disaster recovery)
- [ ] Estimate recreation time: 10-30 minutes typical, but can be hours if capacity-constrained

Infrastructure Readiness
- [ ] Backup training scripts and configuration
- [ ] Verify persistent storage (GCS buckets) accessibility
- [ ] Test slice recreation procedure in non-production environment
- [ ] Document slice topology and placement requirements
- [ ] Prepare monitoring for slice health post-recreation

Communication
- [ ] Notify ML team of expected training interruption
- [ ] Schedule maintenance during least critical training phase
- [ ] Set up alerts for slice recreation completion
- [ ] Plan team availability for restart validation
```

## Maintenance Window Strategy

**Option 1: Ride the maintenance wave**
```bash
# Apply maintenance exclusion to delay (max 30 days)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-campaign-block" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades
```

**Option 2: Control the timing**
```bash
# Set maintenance window for your preferred time
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start 2024-12-15T02:00:00Z \
  --maintenance-window-end 2024-12-15T06:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"
```

## Post-Maintenance Recovery

**Slice validation:**
```bash
# Check all slices are healthy
kubectl get pods -l job-name=your-training-job -o wide
kubectl describe tpu-multislice-resource-name

# Verify TPU topology reconstruction
kubectl exec -it training-pod -- python -c "
import jax
print(f'JAX devices: {jax.device_count()}')
print(f'Local devices: {jax.local_device_count()}')
print(f'Process count: {jax.process_count()}')
"
```

**Training restart procedure:**
```bash
# Restart from latest checkpoint
kubectl create job training-job-restart --from=cronjob/training-job
# Or scale up your existing deployment with checkpoint recovery flags
```

## Critical Timing Considerations

- **Multi-week training runs:** If you're in the middle of a multi-week LLM pre-training run, losing several hours to recreation + restart is significant but not catastrophic if checkpointing is solid
- **Checkpoint frequency:** Ensure you're checkpointing at least every 2-4 hours. Daily checkpoints risk losing too much work
- **Cascading failures:** If any slice fails to recreate properly, the entire multislice environment fails. Monitor all 4 slices carefully

## Recommendation

**Don't fight the maintenance** — TPU multislice environments need periodic maintenance for reliability. Instead:

1. **Checkpoint aggressively** in the 24-48 hours before maintenance
2. **Use the maintenance window** as an opportunity to validate your checkpoint/restore pipeline
3. **Have your ML team on standby** for quick restart validation
4. **Monitor slice recreation closely** — if it takes >1 hour, investigate capacity constraints

The key insight is that TPU multislice maintenance is fundamentally different from regular Kubernetes workload maintenance. Plan for a full restart, not graceful migration.
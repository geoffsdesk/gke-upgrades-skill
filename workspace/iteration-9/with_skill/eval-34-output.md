# TPU Multislice Maintenance Impact & Preparation Guide

## What Will Actually Happen

Your training job will experience **complete interruption** due to TPU multislice maintenance behavior:

### Atomic Recreation Pattern
- **All 4 slices restart simultaneously** — TPU multislice environments don't support rolling updates
- **Cascading restart trigger** — maintenance on ANY single slice forces restart of ALL slices in the multislice environment
- **Complete pod termination** — all training pods across all 1,024 chips will be terminated and recreated

### Expected Timeline
- **Maintenance duration:** ~4 hours per slice, but since all slices restart together, expect ~4 hours total downtime
- **Capacity dependency risk:** If insufficient TPU v5e resources exist during recreation, slices will block until hardware becomes available — this could extend downtime significantly

## Preparation Checklist

```
TPU Multislice Maintenance Prep
- [ ] Checkpoint current training state immediately
- [ ] Verify checkpoint integrity and resumability
- [ ] Document current training step/epoch for resume validation
- [ ] Confirm sufficient TPU v5e quota for slice recreation (1,024 chips)
- [ ] Set up monitoring for slice recreation status
- [ ] Notify stakeholders of expected 4+ hour training interruption
- [ ] Plan training resume process post-maintenance
```

## Maintenance Strategy

### Before Maintenance Window
```bash
# Check current slice status
kubectl get nodes -l cloud.google.com/gke-accelerator=tpu-v5-lite-podslice
kubectl get pods -n YOUR_NAMESPACE | grep tpu

# Force checkpoint now (don't wait for scheduled checkpoint)
# Trigger your training framework's checkpoint mechanism
# For example, if using JAX/Flax:
# Send checkpoint signal to training process or set checkpoint_every_steps=1 temporarily
```

### During Maintenance
- **Monitor slice recreation:** Track node status across all 4 slices
- **Capacity alerts:** Watch for "insufficient resources" errors that could extend downtime
- **Don't intervene:** TPU slice recreation is fully automated — manual intervention can interfere

### Post-Maintenance Validation
```bash
# Verify all slices healthy
kubectl get nodes -l cloud.google.com/gke-accelerator=tpu-v5-lite-podslice
# Should show all 4 slices with 256 chips each = 1,024 total

# Check TPU topology preserved
kubectl describe nodes | grep cloud.google.com/gke-tpu-topology

# Restart training from checkpoint
# Validate resume picked up from correct step/epoch
```

## Risk Mitigation

### Checkpoint Strategy
- **Immediate checkpoint:** Don't rely on scheduled checkpoints — force one now
- **Checkpoint validation:** Test restore process before maintenance window
- **Multiple checkpoint retention:** Keep several recent checkpoints in case latest is corrupted

### Capacity Considerations  
- **Peak demand timing:** TPU v5e capacity is constrained — maintenance during peak hours increases risk
- **Reservation status:** If you have TPU reservations, verify they cover your full 1,024-chip requirement
- **Fallback plan:** Consider if you can temporarily reduce slice count (e.g., 2 slices = 512 chips) if capacity issues arise

### Alternative Timing
If this is a **scheduled maintenance** (not emergency), consider requesting:
- **Maintenance exclusion:** Apply a 30-day "no upgrades" exclusion to defer until a planned training gap
- **Coordinated timing:** Work with your Google contact to schedule during your planned checkpoint window

## Command Reference

```bash
# Apply 30-day maintenance exclusion (if maintenance is deferrable)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-campaign" \
  --add-maintenance-exclusion-start-time $(date -Iseconds) \
  --add-maintenance-exclusion-end-time $(date -d "+30 days" -Iseconds) \
  --add-maintenance-exclusion-scope no_upgrades

# Monitor slice recreation during maintenance
watch 'kubectl get nodes -l cloud.google.com/gke-accelerator=tpu-v5-lite-podslice'

# Check for capacity issues
kubectl get events -A --field-selector reason=FailedScheduling
```

## Key Differences from GPU Maintenance

Unlike GPU node upgrades which can use rolling strategies, **TPU multislice maintenance is always atomic**. The interconnected nature of TPU slices means:
- No rolling updates possible
- No capacity preservation during maintenance  
- All training state lost unless checkpointed
- Restart requires full slice group recreation

**Bottom line:** Treat this as a planned training interruption, not a seamless upgrade. Checkpoint immediately and plan for ~4+ hours of downtime.
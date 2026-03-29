# TPU Multislice Maintenance Impact & Preparation

## What Will Actually Happen

**Critical impact:** TPU multislice environments have **cascading restart behavior** — a maintenance event on ANY slice in your multislice environment will trigger restart of ALL 4 slices simultaneously. This is fundamentally different from regular GPU node maintenance.

**Your specific scenario:**
- **4 TPU v5e slices × 256 chips each = 1,024 TPU chips total**
- **Atomic recreation:** All slices are recreated entirely in a single step (not rolling)
- **All training pods restart simultaneously** — there's no graceful migration
- **Capacity dependency:** If insufficient TPU v5e resources exist during recreation, slices will block until hardware becomes available

**Timeline expectation:**
- **Slice recreation:** ~10-20 minutes per slice, but all 4 happen in parallel
- **Pod startup:** Additional 5-15 minutes for training pods to initialize
- **Model loading:** Depends on your checkpoint size and storage (potentially 30+ minutes for large LLMs)
- **Total downtime:** Expect 45-90 minutes minimum, potentially longer if capacity is constrained

## Preparation Checklist

### Immediate Actions (Before Maintenance Window)

```markdown
- [ ] **Save training checkpoint immediately**
  - Trigger manual checkpoint: your training framework's checkpoint command
  - Verify checkpoint integrity and completeness
  - Note current step/epoch for restart validation

- [ ] **Verify checkpoint storage resilience**
  - Checkpoints on persistent storage (Cloud Storage, persistent disks)
  - NOT on local TPU storage or ephemeral volumes
  - Test checkpoint loading in a separate environment if possible

- [ ] **Document current training state**
  - Current step/epoch: ___
  - Learning rate schedule position: ___
  - Loss/metrics at last checkpoint: ___
  - Expected resume step after restart: ___

- [ ] **Validate TPU capacity availability**
  - Check TPU v5e quota in your zone
  - Confirm no competing reservations during maintenance window
  - Contact GCP support if capacity concerns exist

- [ ] **Prepare monitoring**
  - Set up alerts for slice recreation completion
  - Monitor pod restart and model loading phases
  - Have training metrics dashboard ready for validation
```

### Training Job Configuration

**Ensure your training job is maintenance-resilient:**

```bash
# Verify checkpoint frequency (recommend every 10-15 minutes for multislice)
# Check your training script's checkpoint interval

# Confirm graceful restart capability
kubectl describe deployment TRAINING_DEPLOYMENT
# Look for: proper checkpoint loading on startup, no hardcoded step numbers
```

**Pod disruption budget (limited effectiveness for TPU):**
```yaml
# While PDBs exist, TPU slice recreation bypasses normal drain
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: tpu-training-pdb
spec:
  selector:
    matchLabels:
      app: tpu-training
  maxUnavailable: 0  # Won't prevent slice recreation but documents intent
```

## During Maintenance

**What you'll observe:**
1. **All 4 slices cordon simultaneously** — no new pods scheduled
2. **Existing training pods receive SIGTERM** — your training job should checkpoint and exit gracefully
3. **Slices are deleted and recreated** — all 1,024 TPU chips replaced
4. **New pods scheduled to new slices** — training restarts from last checkpoint

**Expected log sequence:**
```
slice-1-0: SLICE_RECREATING
slice-2-0: SLICE_RECREATING  
slice-3-0: SLICE_RECREATING
slice-4-0: SLICE_RECREATING
# ... 10-20 minutes later ...
slice-1-0: Ready
slice-2-0: Ready
slice-3-0: Ready
slice-4-0: Ready
```

## Post-Maintenance Validation

```markdown
- [ ] **All slices operational**
  `kubectl get nodes -l cloud.google.com/gke-accelerator=tpu-v5e`

- [ ] **Training pods running**
  `kubectl get pods -l app=tpu-training`

- [ ] **Checkpoint loading successful**
  - Check training logs for successful checkpoint restoration
  - Verify resumed step matches expected post-checkpoint step
  - No "starting from scratch" or step=0 messages

- [ ] **Training metrics recovery**
  - Loss curve continues from pre-maintenance levels
  - No significant metric degradation or spikes
  - Learning rate schedule resumed correctly

- [ ] **Multislice topology correct**
  - All 4 slices visible to training job
  - Inter-slice communication working (check for topology errors in logs)
  - No training hanging on cross-slice synchronization
```

## Risk Mitigation

**Capacity risk:** TPU v5e capacity is extremely limited. If insufficient resources exist during recreation:
- **Escalation path:** Contact Google Cloud Customer Care immediately
- **Alternative:** Consider temporary migration to smaller slice configuration if training can continue
- **Timeline impact:** Could extend downtime from hours to days

**Checkpoint corruption risk:**
- Take multiple checkpoints before maintenance
- Store checkpoints redundantly (multiple Cloud Storage buckets)
- Test checkpoint loading before the maintenance window

**Extended downtime contingency:**
- Plan for 2-4 hour maintenance windows (not the typical 30-60 minutes)
- Notify stakeholders of potential extended outage
- Consider if training campaign can pause vs. must continue

## GKE-Specific Commands

```bash
# Monitor TPU node status during maintenance
watch 'kubectl get nodes -l cloud.google.com/gke-accelerator=tpu-v5e -o wide'

# Check slice recreation events
kubectl get events --field-selector involvedObject.kind=Node --sort-by='.lastTimestamp'

# Verify multislice pod distribution post-maintenance
kubectl get pods -o wide -l app=tpu-training | grep -E "slice-[0-4]"

# Check for TPU allocation errors
kubectl describe pods -l app=tpu-training | grep -A5 -B5 "Failed to allocate"
```

**Key insight:** Unlike GPU node maintenance where you might get rolling updates, TPU multislice maintenance is "all or nothing." Your 1,024-chip training job will experience a complete restart. Plan accordingly with robust checkpointing and expect 1-2 hours of downtime minimum.
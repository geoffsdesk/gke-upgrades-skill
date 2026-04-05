# TPU Multislice Maintenance Impact & Preparation Guide

## What Will Actually Happen

Your training job will be **completely terminated** across all slices simultaneously. Here's the exact sequence:

### TPU Multislice Maintenance Behavior
- **Atomic recreation:** All 4 TPU v5e slices (1,024 chips total) will be recreated entirely in a single step — not rolling
- **Cascading restart:** The maintenance event on ANY slice triggers restart of ALL slices in your multislice environment
- **Complete job termination:** Your LLM training job cannot survive this — all model state in TPU memory is lost
- **Capacity dependency:** If insufficient TPU v5e resources exist during recreation, slices will block until hardware becomes available (potentially hours of additional downtime)

### Timeline Expectations
- **Total downtime:** 30-60 minutes minimum for slice recreation + job restart
- **Potential extended outage:** If TPU v5e capacity is constrained, could be several hours until all slices are available
- **No partial recovery:** All 4 slices must be healthy before training can resume

## Pre-Maintenance Preparation Checklist

```markdown
TPU Multislice Maintenance Prep
- [ ] Training checkpoint saved at latest iteration
- [ ] Checkpoint validation completed (can successfully restore)
- [ ] Training resumption procedure tested in dev environment
- [ ] Monitoring/alerting configured for slice health post-maintenance
- [ ] Stakeholder communication sent (expected 30-60min+ downtime)
- [ ] Alternative compute resources identified if extended outage occurs
- [ ] Job submission scripts updated with latest hyperparameters
- [ ] Data pipeline validated (no corruption during extended pause)
```

## Specific Actions to Take

### 1. Force Immediate Checkpoint
```bash
# Save checkpoint at current iteration (don't wait for next scheduled checkpoint)
# Method depends on your training framework:

# For JAX/Flax:
# Trigger immediate save via training loop signal or API call

# For PyTorch/XLA:
# Send checkpoint signal to training process
```

### 2. Validate Checkpoint Integrity
```bash
# Test restore from latest checkpoint before maintenance window
python validate_checkpoint.py --checkpoint_path=/path/to/latest
```

### 3. Document Current State
```bash
# Capture exact training state for resume
echo "Last completed step: $(cat /training/logs/step_counter)"
echo "Learning rate: $(cat /training/logs/current_lr)"
echo "Loss value: $(cat /training/logs/latest_loss)"
```

### 4. Prepare Auto-Resume Script
Since multislice restarts are predictable, create an automated restart:

```bash
#!/bin/bash
# multislice-resume.sh

# Wait for all 4 slices to be Ready
while [[ $(kubectl get pods -l tpu-slice=training -o jsonpath='{.items[*].status.phase}' | tr ' ' '\n' | sort -u) != "Running" ]]; do
  echo "Waiting for all TPU slices to be ready..."
  sleep 30
done

# Restart training from latest checkpoint
python train_llm.py \
  --resume_from_checkpoint=/checkpoints/latest \
  --tpu_slices=4 \
  --slice_size=256
```

## Post-Maintenance Validation

### 1. Verify Slice Health
```bash
# All slices must show Running and 256/256 Ready
kubectl get pods -l tpu-slice=training -o wide

# Check TPU topology is intact
python verify_tpu_topology.py --expected_slices=4 --chips_per_slice=256
```

### 2. Training Resume Verification
```bash
# Confirm model loads from checkpoint
# Verify loss continuity (no unexpected spikes)
# Check throughput matches pre-maintenance baseline (chips/sec)
tail -f /training/logs/training.log | grep -E "(step|loss|throughput)"
```

## Risk Mitigation Strategies

### Short-term (for this maintenance)
- **Schedule during natural training pause:** If you have planned evaluation or hyperparameter adjustment phases, align maintenance with those
- **Increase checkpoint frequency:** Save every 50-100 steps instead of every 1000 during the week before maintenance
- **Pre-provision alternative compute:** Have CPU/GPU fallback ready for critical experiments if TPU outage extends

### Long-term Architecture
- **Implement robust checkpointing:** Model weights + optimizer state + RNG state + exact step counter
- **Automate resume pipeline:** Scripts that can restart training without human intervention
- **Cross-region redundancy:** For critical training runs, consider multi-region TPU allocation (if budget allows)

## Emergency Procedures

If slices don't come back or training fails to resume:

### 1. Escalation Path
```bash
# Check slice provisioning status
gcloud container node-pools describe tpu-pool --cluster=CLUSTER --zone=ZONE

# Contact Google Cloud Support with:
# - Cluster name and zone
# - Multislice configuration (4x256 TPU v5e)
# - Timestamp of maintenance event
# - Error messages from kubectl/training logs
```

### 2. Fallback Compute
```bash
# Emergency smaller-scale training on available TPUs
# Reduce model size or batch size to fit available hardware
python train_llm.py \
  --model_scale=reduced \
  --tpu_slices=1 \
  --slice_size=64
```

## Key Insight

TPU multislice maintenance is fundamentally different from standard GKE upgrades — it's a **complete environment recreation**, not a rolling update. Your 1,024-chip training job will experience full termination regardless of PDBs, graceful shutdown periods, or other Kubernetes-level protections. The TPU hardware itself is being maintained, which requires complete deallocation.

**Bottom line:** Treat this as planned downtime, ensure your checkpointing is bulletproof, and have your resume automation ready to go.
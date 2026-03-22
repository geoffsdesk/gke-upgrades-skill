# TPU Multislice Maintenance Impact & Preparation

## What Will Actually Happen

Your training job will experience a **complete restart** due to TPU multislice upgrade behavior:

### TPU Multislice Upgrade Characteristics
- **Atomic recreation**: Each TPU slice (256 chips) is recreated entirely in a single step — not rolling
- **Cascading restart**: A maintenance event on ANY slice triggers restart of ALL slices in your multislice environment
- **All 4 slices restart simultaneously**: Your entire 1,024-chip training environment goes down at once
- **No graceful migration**: Unlike CPU/GPU workloads, TPU slices cannot be drained or migrated — they must be recreated

### Timeline & Duration
- **Capacity dependency**: If insufficient TPU v5e resources exist during recreation, slices will block until hardware becomes available
- **Extended downtime risk**: This can cause hours or days of downtime if TPU capacity is constrained
- **All-or-nothing**: Either all 4 slices come back successfully, or none do

## Pre-Maintenance Preparation Checklist

```
TPU Multislice Maintenance Preparation
- [ ] Training checkpoint saved at current step
- [ ] Checkpoint location verified accessible (GCS bucket, persistent volumes)
- [ ] Training resumption commands/scripts prepared
- [ ] Monitoring dashboards configured for post-restart validation
- [ ] Team notified of expected downtime window
- [ ] Alternative compute resources identified (if available) for urgent experiments

TPU-Specific Checks
- [ ] TPU reservation status confirmed (if using reservations)
- [ ] Verify no other critical TPU workloads competing for same resource pool
- [ ] GKE cluster health verified: `kubectl get nodes | grep tpu`
- [ ] TPU slice connectivity tested: check inter-slice communication logs
- [ ] Model sharding configuration documented for restart

Training Job Preparation  
- [ ] Enable frequent checkpointing (every N steps based on training velocity)
- [ ] Verify checkpoint restoration works from current state
- [ ] Document current training metrics (loss, perplexity, step count)
- [ ] Test training restart procedure in a smaller environment if possible
- [ ] Ensure training script handles checkpoint resumption correctly
```

## Recommended Actions

### 1. Immediate: Force Checkpoint Now
```bash
# If your training framework supports it, trigger an immediate checkpoint
# Example for JAX-based training:
kubectl exec -it TRAINING_POD -- python save_checkpoint.py --step current
```

### 2. Maintenance Window Control (if time permits)
```bash
# Check current maintenance window
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="yaml(maintenancePolicy)"

# Apply 30-day "no upgrades" exclusion to delay maintenance
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "critical-training-run" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time $(date -u -d "+30 days" +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-scope no_upgrades
```

### 3. Post-Maintenance Restart Procedure
```bash
# Verify all TPU slices are available
kubectl get nodes -l cloud.google.com/gke-accelerator=tpu-v5-litepod-256

# Check TPU slice connectivity
kubectl logs -l job-name=TRAINING_JOB | grep -i "slice\|tpu\|connection"

# Restart training from checkpoint
kubectl apply -f training-job-manifest.yaml
# Or trigger restart via your training orchestration system
```

## Key Differences from CPU/GPU Maintenance

| Aspect | CPU/GPU Clusters | TPU Multislice |
|--------|------------------|----------------|
| **Upgrade method** | Rolling, surge, or blue-green | Atomic recreation only |
| **Graceful shutdown** | Respects PDBs, termination grace | Hard restart — no graceful option |
| **Partial availability** | Some nodes stay up during upgrade | All slices down simultaneously |
| **Capacity risk** | Surge nodes may fail to provision | All slices may fail to recreate |
| **Workload impact** | Jobs can migrate between nodes | Jobs must restart from checkpoint |

## Training-Specific Considerations

### Checkpointing Strategy
- **Increase checkpoint frequency** before maintenance events
- **Test checkpoint restoration** — many TPU training issues surface during restart
- **Verify checkpoint completeness** — partially written checkpoints can corrupt training state

### Model Sharding Recovery
- **Document sharding configuration**: TPU multislice models are sharded across all 1,024 chips
- **Verify shard reassignment**: After restart, ensure model shards are correctly distributed across recreated slices
- **Test inter-slice communication**: RDMA/high-speed interconnect between slices must be re-established

### Capacity Planning
- **TPU v5e scarcity**: These are in extremely high demand — recreation may wait for available hardware
- **Reservation status**: If using TPU reservations, verify they're still active and cover all 4 slices
- **Alternative resources**: Have a backup plan if TPU capacity is unavailable (smaller slice count, different TPU generation, etc.)

This is fundamentally different from standard GKE upgrades — there's no way to avoid the training restart, so preparation and checkpointing are your primary mitigation strategies.
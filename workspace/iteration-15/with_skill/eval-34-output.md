## TPU Multislice Maintenance Impact

Your training job will experience a **complete restart** — this is fundamentally different from CPU/GPU maintenance. Here's what actually happens:

### What Will Happen During Maintenance

**Atomic Recreation:** Each TPU slice (256 chips) gets recreated entirely in a single step. There's no rolling upgrade — all 256 chips restart simultaneously per slice.

**Cascading Restart:** Since you have 4 interconnected slices, a maintenance event on **ANY single slice triggers restart of ALL 4 slices**. This is due to the tight coupling in multislice environments — the training job spans all slices and can't survive partial failure.

**Capacity Risk:** During recreation, if insufficient TPU v5e resources exist in your zone, the slice will block until hardware becomes available. With 4x256 chips (1024 total), this represents significant capacity that needs to be available simultaneously.

**Timeline:** Expect 10-30 minutes of downtime per maintenance event, assuming capacity is available. If capacity is constrained, it could be hours.

## Pre-Maintenance Preparation

### 1. Checkpoint Strategy (Critical)
```bash
# Verify your training job has robust checkpointing enabled
# Ensure checkpoints are saved to persistent storage (GCS/persistent disks)
# NOT to local TPU storage which will be destroyed

# Example checkpoint verification
gsutil ls gs://YOUR_CHECKPOINT_BUCKET/
# Confirm recent checkpoints exist and are complete
```

### 2. Maintenance Exclusion (Buy Time)
```bash
# Apply "no upgrades" exclusion for immediate protection (up to 30 days)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-freeze-$(date +%Y%m%d)" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades
```

This blocks ALL maintenance for 30 days, even past End of Support. Use this time to plan a controlled checkpoint-and-restart.

### 3. Training Job Protection
```bash
# Set very high PDB to prevent accidental eviction
kubectl patch pdb YOUR_TRAINING_PDB \
  -p '{"spec":{"minAvailable":"100%"}}'

# But understand: maintenance events bypass PDB protection
# This only protects against other disruptions
```

## Recommended Maintenance Strategy

### Option A: Controlled Restart (Recommended)
1. **Save checkpoint manually** during a natural stopping point
2. **Scale training job to zero** before maintenance window
3. **Allow maintenance to proceed** (remove exclusion)
4. **Restart training from checkpoint** after maintenance completes

```bash
# Scale down training workload
kubectl scale deployment YOUR_TRAINING_DEPLOYMENT --replicas=0

# Wait for clean shutdown and final checkpoint
# Remove maintenance exclusion to allow upgrade
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "training-freeze-$(date +%Y%m%d)"
```

### Option B: Extended Exclusion Chain
Use multiple 30-day exclusions to defer maintenance until your training campaign completes. **Risk:** Accumulates security patches and may hit GKE's exclusion limits.

## Post-Maintenance Recovery

### 1. Verify TPU Slice Health
```bash
# Check all nodes are Ready
kubectl get nodes -l accelerator=tpu

# Verify TPU topology is intact
kubectl describe nodes -l accelerator=tpu | grep "topology.gke.io"

# Confirm all 4 slices are available
kubectl get pods -l workload=training -o wide
```

### 2. Restart Training from Checkpoint
```bash
# Launch training job pointing to latest checkpoint
kubectl apply -f training-job-manifest.yaml

# Monitor startup - multislice initialization takes several minutes
kubectl logs -f deployment/YOUR_TRAINING_DEPLOYMENT
```

### 3. Validate Training Resume
- Verify loss curve continues smoothly from checkpoint
- Check that all 1024 chips are participating (no degraded performance)
- Monitor for any topology/interconnect issues

## Key Differences from CPU/GPU Maintenance

| Aspect | CPU/GPU Clusters | TPU Multislice |
|--------|-----------------|----------------|
| **Upgrade type** | Rolling node-by-node | Atomic slice recreation |
| **Job survival** | Can survive with PDBs | Always restarts |
| **Capacity impact** | Gradual | All-or-nothing |
| **Recovery time** | Seconds to minutes | 10-30+ minutes |

## Planning for Future Maintenance

1. **Dedicated TPU node pools** with maintenance exclusions during active campaigns
2. **Checkpoint frequency** aligned with expected maintenance windows (weekly/bi-weekly)
3. **Capacity reservations** to guarantee post-maintenance recovery
4. **Multi-region backup strategy** for mission-critical training (though cross-region checkpointing adds complexity)

The bottom line: TPU multislice maintenance is a **planned restart**, not a rolling upgrade. Your job will restart from the last checkpoint — ensure that checkpoint is recent and the restart process is tested.
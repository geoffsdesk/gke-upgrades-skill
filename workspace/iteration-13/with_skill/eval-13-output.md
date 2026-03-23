# GKE Upgrade Plan for Long-Running Batch Jobs (1.30 → 1.31)

## Executive Summary

Your 8-16 hour batch jobs require special handling since GKE's default 1-hour pod eviction timeout is far shorter than your job duration. I recommend using **maintenance exclusions** to block upgrades during active job campaigns, combined with a **dedicated batch processing node pool** for maximum control.

## Upgrade Strategy

### Option 1: Maintenance Exclusions (Recommended)
Use GKE's "no minor or node upgrades" exclusion to block the 1.31 upgrade during active batch campaigns while still allowing security patches on the control plane.

```bash
# Block minor and node upgrades until your batch campaign completes
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "batch-campaign-q1" \
  --add-maintenance-exclusion-start-time "2024-12-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-25T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

**Key benefits:**
- Control plane still receives security patches
- Complete protection for batch jobs
- Available until version 1.30 reaches End of Support (~14 months from release)

### Option 2: Dedicated Batch Node Pool Architecture
Isolate batch jobs on a separate node pool with independent upgrade controls.

```bash
# Create dedicated batch processing node pool
gcloud container node-pools create batch-processing \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --machine-type c2-standard-16 \
  --num-nodes 3 \
  --enable-autoscaling \
  --min-nodes 0 \
  --max-nodes 10 \
  --node-labels=workload-type=batch \
  --node-taints=batch-only=true:NoSchedule

# Configure batch jobs to use this pool
```

Add to your batch job specs:
```yaml
spec:
  template:
    spec:
      nodeSelector:
        workload-type: batch
      tolerations:
      - key: batch-only
        operator: Equal
        value: "true"
        effect: NoSchedule
```

## Upgrade Execution Plan

### Phase 1: Control Plane (Safe - No Job Impact)
```bash
# Upgrade control plane first (no impact on running pods)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.31.3-gke.1535000

# Verify control plane upgrade
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

### Phase 2: Node Pool Upgrade (During Job Gap)
Wait for your batch jobs to complete naturally, then upgrade during a scheduled gap:

```bash
# Configure conservative surge settings for batch pool
gcloud container node-pools update batch-processing \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade the batch node pool during job gap
gcloud container node-pools upgrade batch-processing \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.3-gke.1535000
```

### Phase 3: Remove Exclusions
After successful upgrade, remove the maintenance exclusion to resume normal auto-upgrade behavior:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "batch-campaign-q1"
```

## Pre-Upgrade Checklist

```markdown
- [ ] **Version compatibility verified**: 1.30 → 1.31 is supported
- [ ] **Batch job checkpoint capability confirmed**: Jobs can resume from checkpoints if needed
- [ ] **Resource requests set**: All batch containers have CPU/memory requests
- [ ] **No bare pods**: All jobs managed by Job/CronJob controllers
- [ ] **Maintenance exclusion configured**: "no minor or node upgrades" active during campaign
- [ ] **Job completion timeline known**: Clear gaps identified for node upgrades
- [ ] **PDB configuration reviewed**: Not overly restrictive for batch workloads
- [ ] **Control plane upgrade tested**: In staging environment first
```

## Alternative: Cordon-and-Wait Pattern

If you need more granular control, use manual node management:

```bash
# When ready to upgrade, cordon batch nodes
kubectl cordon -l workload-type=batch

# Wait for current jobs to complete naturally (8-16 hours)
kubectl get pods -l workload-type=batch --watch

# Once nodes are empty, upgrade the pool
gcloud container node-pools upgrade batch-processing \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.3-gke.1535000

# Uncordon after upgrade completes
kubectl uncordon -l workload-type=batch
```

## Monitoring During Upgrade

```bash
# Monitor job status during upgrade window
kubectl get jobs -A -o wide

# Check for any stuck or pending batch pods
kubectl get pods -A -l workload-type=batch

# Verify node upgrade progress
watch 'kubectl get nodes -l workload-type=batch'
```

## Key Considerations

1. **Control plane upgrades are safe** - They don't impact running pods, so you can upgrade from 1.30 → 1.31 immediately
2. **Node upgrades require planning** - Schedule during natural job completion gaps
3. **Maintenance exclusions are temporary** - Plan to remove them once the upgrade is complete
4. **Version skew is acceptable** - Nodes can run 1.30 while control plane runs 1.31 for up to the version skew limit

## Next Steps

1. Apply maintenance exclusion immediately to block auto-upgrades
2. Upgrade control plane during any maintenance window (no job impact)
3. Plan node pool upgrade for your next scheduled batch job gap
4. Consider implementing the dedicated node pool architecture for future campaigns

This approach gives you complete control over upgrade timing while maintaining security patch delivery and following GKE best practices.
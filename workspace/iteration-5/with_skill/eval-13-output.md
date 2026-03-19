# GKE Upgrade Strategy for Long-Running Batch Jobs

## Executive Summary

Your 8-16 hour batch jobs require special handling during GKE upgrades since the default 1-hour pod eviction timeout will forcibly terminate them. Here's a comprehensive strategy to upgrade from 1.29 to 1.30 without job loss.

## Environment Analysis

- **Cluster mode:** Standard GKE
- **Current version:** 1.29
- **Target version:** 1.30 (sequential upgrade recommended)
- **Critical constraint:** 8-16 hour batch jobs cannot be interrupted
- **Challenge:** GKE's default surge upgrade timeout (1 hour) << job duration

## Recommended Strategy: Dedicated Batch Node Pool + Cordon-and-Wait

### 1. Node Pool Architecture

Isolate batch workloads on dedicated node pools with auto-upgrade disabled:

```bash
# Create dedicated batch processing node pool (if not already separated)
gcloud container node-pools create batch-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --machine-type c2-standard-16 \
  --num-nodes 3 \
  --enable-autorepair \
  --no-enable-autoupgrade \
  --node-labels workload=batch \
  --node-taints batch=true:NoSchedule

# Configure batch jobs to target this pool
# Add to your job specs:
# nodeSelector:
#   workload: batch
# tolerations:
# - key: batch
#   operator: Equal
#   value: "true"
#   effect: NoSchedule
```

### 2. Maintenance Exclusion Strategy

Apply a "no minor or node upgrades" exclusion to protect running jobs while still allowing control plane security patches:

```bash
# Block node pool upgrades during active batch processing periods
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "batch-processing-protection" \
  --add-maintenance-exclusion-start-time 2024-12-01T00:00:00Z \
  --add-maintenance-exclusion-end-time 2024-12-31T23:59:59Z \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

This exclusion:
- ✅ Blocks node pool upgrades (protects your jobs)
- ✅ Allows control plane security patches
- ✅ Can be extended up to version End of Support
- ✅ Gives you full control over timing

### 3. Upgrade Execution Plan

#### Phase 1: Control Plane Upgrade (Safe - No Job Impact)
```bash
# Upgrade control plane first (no impact on running pods)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.30

# Verify control plane upgrade
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

#### Phase 2: Non-Batch Node Pools
```bash
# Upgrade other node pools normally (web services, APIs, etc.)
gcloud container node-pools upgrade general-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30
```

#### Phase 3: Batch Pool Upgrade (Coordinated)

**Option A: Cordon-and-Wait (Recommended)**
```bash
# 1. Prevent new jobs from scheduling on old nodes
kubectl cordon -l workload=batch

# 2. Wait for current jobs to complete naturally
kubectl get jobs -n batch-namespace --watch

# 3. When all jobs complete, upgrade the empty pool
gcloud container node-pools upgrade batch-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30

# 4. Uncordon nodes when upgrade completes
kubectl uncordon -l workload=batch
```

**Option B: Blue-Green for Batch Pool**
```bash
# 1. Create new batch pool at target version
gcloud container node-pools create batch-pool-v130 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30 \
  --machine-type c2-standard-16 \
  --num-nodes 3 \
  --no-enable-autoupgrade \
  --node-labels workload=batch,version=v130 \
  --node-taints batch=true:NoSchedule

# 2. Update job scheduling to prefer new pool
# Add nodeSelector: {workload: batch, version: v130}

# 3. Cordon old pool, wait for jobs to drain
kubectl cordon -l workload=batch,version!=v130

# 4. Delete old pool when empty
gcloud container node-pools delete batch-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE
```

## Workload Protection Enhancements

### 1. PodDisruptionBudgets
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: batch-jobs-pdb
  namespace: batch-namespace
spec:
  minAvailable: 100%  # Prevent any voluntary disruption
  selector:
    matchLabels:
      app: batch-processor
```

### 2. Job Checkpointing
Enhance your batch jobs with checkpointing so they can resume if disrupted:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: long-batch-job
spec:
  template:
    spec:
      restartPolicy: OnFailure
      containers:
      - name: processor
        image: your-batch-processor:latest
        env:
        - name: CHECKPOINT_INTERVAL
          value: "300"  # Save progress every 5 minutes
        - name: CHECKPOINT_PATH
          value: "/data/checkpoints/"
        volumeMounts:
        - name: checkpoint-storage
          mountPath: /data/checkpoints
      volumes:
      - name: checkpoint-storage
        persistentVolumeClaim:
          claimName: batch-checkpoints
      terminationGracePeriodSeconds: 600  # 10 min graceful shutdown
```

### 3. Pre-Upgrade Job Coordination

```bash
# Check for running jobs before any upgrade
kubectl get jobs -A --field-selector status.active=1

# Estimate completion times
kubectl describe jobs -n batch-namespace | grep "Start Time\|Duration"

# Verify no new jobs scheduled during maintenance
kubectl get cronjobs -A -o yaml | grep suspend: false
```

## Timeline and Risk Management

### Upgrade Windows
- **Control plane:** Any time (5-10 minutes, no pod disruption)
- **General pools:** Standard maintenance window
- **Batch pool:** Only when no active jobs (coordinate with job scheduler)

### Risk Mitigation
1. **Version compatibility verified:** 1.29→1.30 is a single minor version jump
2. **Rollback capability:** Blue-green provides instant rollback for batch pool
3. **Monitoring:** Set up alerts for job failures during upgrade windows
4. **Communication:** Notify job submitters of maintenance schedules

### Maintenance Exclusion Timeline
```bash
# After batch pool upgrade, remove the exclusion to resume normal auto-upgrades
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "batch-processing-protection"
```

## Alternative: Extended Release Channel

If your batch processing requires maximum stability and minimal upgrade frequency:

```bash
# Migrate to Extended channel (24-month support, versions 1.27+)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

Extended channel provides:
- Longer support windows (up to 24 months)
- Reduced upgrade frequency
- Extra cost but maximum predictability

## Pre-Upgrade Checklist for Batch Workloads

```
- [ ] Batch jobs isolated on dedicated node pool with auto-upgrade disabled
- [ ] "No minor or node upgrades" maintenance exclusion applied
- [ ] PodDisruptionBudgets configured (minAvailable: 100%)
- [ ] Job checkpointing implemented and tested
- [ ] terminationGracePeriodSeconds ≥ 600 seconds
- [ ] Current job queue status reviewed (no critical jobs starting during window)
- [ ] Rollback plan documented (blue-green pools or node pool recreation)
- [ ] Monitoring alerts configured for job failures
- [ ] Job scheduler team notified of maintenance window
```

This strategy ensures zero job interruption while maintaining cluster security through control plane patches. The dedicated batch pool with disabled auto-upgrade gives you complete control over when those nodes are updated.
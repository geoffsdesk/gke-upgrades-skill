# GKE Upgrade Plan for Long-Running Batch Jobs

## Overview
For 8-16 hour batch jobs, GKE's default 1-hour PDB timeout during surge upgrades will force-evict your jobs mid-execution. You need **autoscaled blue-green upgrade strategy** or **maintenance exclusions with job coordination**.

## Recommended Strategy: Autoscaled Blue-Green

**Why this works for your use case:**
- Respects extended `terminationGracePeriodSeconds` (no 1-hour force eviction)
- Cost-efficient: scales down old nodes as jobs drain to new nodes
- Built for long-running workloads that can't be interrupted

### Configuration Commands

```bash
# Enable autoscaling on your batch node pool
gcloud container node-pools update BATCH_NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 0 \
  --total-max-nodes MAX_NODES

# Configure autoscaled blue-green strategy
gcloud container node-pools update BATCH_NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --strategy=BLUE_GREEN \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=28800s
```

**Key parameters:**
- `blue-green-initial-node-percentage=0.25`: Start with 25% of nodes in the new pool
- `blue-green-full-batch-timeout=28800s`: 8 hours for green pool readiness (adjust to 57600s for 16-hour max)

## Alternative: Maintenance Exclusions + Job Coordination

If you prefer manual control:

```bash
# Block node upgrades during active batch campaigns
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "batch-processing-campaign" \
  --add-maintenance-exclusion-start-time 2024-01-15T00:00:00Z \
  --add-maintenance-exclusion-end-time 2024-01-30T23:59:59Z \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# This allows control plane patches but blocks disruptive node upgrades
```

**Workflow:**
1. Schedule batch job pause window
2. Remove exclusion during the gap
3. Manually trigger upgrade: `gcloud container clusters upgrade CLUSTER_NAME --zone ZONE --master --cluster-version 1.31.x-gke.xxxx`
4. Then upgrade node pools: `gcloud container node-pools upgrade BATCH_POOL --cluster CLUSTER_NAME --zone ZONE --cluster-version 1.31.x-gke.xxxx`

## Pre-Upgrade Batch Job Configuration

Ensure your batch jobs can survive the upgrade process:

### 1. Extended Grace Periods
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: long-batch-job
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 3600  # 1 hour minimum, up to job duration
      containers:
      - name: batch-processor
        image: your-batch-image
```

### 2. Checkpointing (Recommended)
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: checkpointed-job
spec:
  template:
    spec:
      containers:
      - name: batch-processor
        env:
        - name: CHECKPOINT_INTERVAL
          value: "300"  # Save state every 5 minutes
        - name: CHECKPOINT_PATH
          value: "/checkpoints"
        volumeMounts:
        - name: checkpoint-storage
          mountPath: /checkpoints
      volumes:
      - name: checkpoint-storage
        persistentVolumeClaim:
          claimName: batch-checkpoints
```

### 3. Safe-to-Evict Annotation
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: protected-job
spec:
  template:
    metadata:
      annotations:
        cluster-autoscaler.kubernetes.io/safe-to-evict: "false"
    spec:
      # ... job spec
```

## Complete Upgrade Runbook

### Phase 1: Control Plane Upgrade
```bash
# Control plane first (nodes can be up to 2 minor versions behind)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.31.x-gke.xxxx

# Verify (10-15 minutes)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

### Phase 2: Batch Job Preparation
```bash
# Pause new job submissions
kubectl scale deployment batch-job-controller --replicas=0

# Check running jobs
kubectl get jobs -A
kubectl get pods -A -l job-name

# Estimate completion time
kubectl describe jobs -A | grep -E "Start Time|Active"
```

### Phase 3: Node Pool Upgrade (Autoscaled Blue-Green)
```bash
# Trigger the upgrade - autoscaled blue-green handles the rest
gcloud container node-pools upgrade BATCH_NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.xxxx

# Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
kubectl get jobs -A --watch
```

### Phase 4: Validation
```bash
# Verify all nodes upgraded
kubectl get nodes -o wide

# Check job completion
kubectl get jobs -A
kubectl get pods -A | grep batch

# Resume job submissions
kubectl scale deployment batch-job-controller --replicas=1
```

## Timing Considerations

**Best practice:** Execute during your natural job gap window
- Schedule upgrades between batch campaigns when possible
- For continuous processing: autoscaled blue-green is your only option
- Control plane upgrades take 10-15 minutes (no job impact)
- Node upgrades take 2-8 hours depending on job completion

**Maintenance window configuration:**
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-20T02:00:00Z" \
  --maintenance-window-duration 8h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## Risk Mitigation

### Backup Strategy
```bash
# Before upgrade: backup job state/data
kubectl get jobs -A -o yaml > jobs-backup.yaml
kubectl get pvc -A -o yaml > pvc-backup.yaml

# Take application-level snapshots if applicable
```

### Rollback Plan
```bash
# If issues arise during blue-green upgrade
gcloud container node-pools rollback BATCH_NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE

# Jobs on old nodes continue running
# New jobs get scheduled to rolled-back pool
```

## Key Warnings

⚠️ **Never use standard surge for 8+ hour jobs** - GKE force-evicts after 1 hour regardless of PDB or grace period

⚠️ **Jobs without checkpointing** - Will restart from beginning if evicted during upgrade

⚠️ **Mixed node versions** - During upgrade, some jobs run on 1.30 nodes, some on 1.31. This is normal and supported.

The autoscaled blue-green strategy is specifically designed for your use case - it's the only native GKE upgrade method that respects long termination grace periods without force-eviction after 1 hour.
Here are several strategies to handle this upgrade without killing your long-running batch jobs:

## Option 1: Blue/Green Node Pool Strategy (Recommended)

```yaml
# Create new node pool with 1.31
apiVersion: v1
kind: ConfigMap
metadata:
  name: upgrade-strategy
data:
  steps: |
    1. Create new node pool with GKE 1.31
    2. Cordon old nodes to prevent new scheduling
    3. Wait for existing jobs to complete naturally
    4. Delete old node pool
```

**Implementation:**
```bash
# 1. Create new node pool with 1.31
gcloud container node-pools create "pool-v131" \
  --cluster=your-cluster \
  --zone=your-zone \
  --node-version=1.31.x \
  --num-nodes=3 \
  --machine-type=your-machine-type

# 2. Cordon old nodes (prevents new pods from scheduling)
kubectl get nodes -l cloud.google.com/gke-nodepool=old-pool-name -o name | \
  xargs -I {} kubectl cordon {}

# 3. Wait for jobs to complete, then drain
kubectl get nodes -l cloud.google.com/gke-nodepool=old-pool-name -o name | \
  xargs -I {} kubectl drain {} --ignore-daemonsets --delete-emptydir-data

# 4. Delete old node pool
gcloud container node-pools delete old-pool-name --cluster=your-cluster
```

## Option 2: Pause Auto-Upgrades During Job Windows

```yaml
# maintenance-policy.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: maintenance-windows
data:
  policy: |
    # Set maintenance exclusions during your batch job periods
    exclusions:
      - name: "batch-job-window"
        startTime: "2024-01-01T20:00:00Z"  # When jobs typically start
        endTime: "2024-01-02T12:00:00Z"    # When jobs complete
        scope: "NO_UPGRADES"
```

```bash
# Configure maintenance window to avoid your job schedule
gcloud container clusters update your-cluster \
  --maintenance-window-start "2024-01-15T02:00:00Z" \
  --maintenance-window-end "2024-01-15T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"
```

## Option 3: Job-Aware Upgrade with PodDisruptionBudgets

```yaml
# Ensure your batch jobs have PDBs
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: batch-job-pdb
spec:
  minAvailable: 1  # or 100% to prevent any disruption
  selector:
    matchLabels:
      app: batch-job
---
# Add nodeSelector to pin critical jobs to specific nodes
apiVersion: batch/v1
kind: Job
metadata:
  name: long-running-batch
spec:
  template:
    spec:
      nodeSelector:
        node-pool: stable-pool  # Pin to nodes you won't upgrade yet
      containers:
      - name: batch-processor
        image: your-image
```

## Option 4: Staged Upgrade Approach

```bash
# 1. First, upgrade control plane only (minimal disruption)
gcloud container clusters upgrade your-cluster \
  --master \
  --cluster-version=1.31.x

# 2. Wait for batch job completion window
# 3. Then upgrade nodes during low-activity period
gcloud container clusters upgrade your-cluster \
  --node-pool=your-node-pool \
  --cluster-version=1.31.x
```

## Best Practices for Future Upgrades

```yaml
# 1. Add job completion monitoring
apiVersion: v1
kind: ConfigMap
metadata:
  name: job-monitor
data:
  script: |
    #!/bin/bash
    # Check for running batch jobs before upgrade
    RUNNING_JOBS=$(kubectl get jobs --all-namespaces --field-selector status.active=1 -o name | wc -l)
    if [ $RUNNING_JOBS -gt 0 ]; then
      echo "❌ $RUNNING_JOBS batch jobs still running. Delaying upgrade."
      exit 1
    fi
    echo "✅ No active batch jobs. Safe to proceed with upgrade."
```

```yaml
# 2. Use job restart policies appropriately
apiVersion: batch/v1
kind: Job
spec:
  backoffLimit: 3
  template:
    spec:
      restartPolicy: OnFailure  # Restart on node failure
      containers:
      - name: batch-job
        image: your-image
        # Add checkpointing/state persistence for long jobs
        volumeMounts:
        - name: checkpoint-storage
          mountPath: /checkpoints
```

## Recommended Timeline

1. **Week 1**: Create new 1.31 node pool alongside existing 1.30 pool
2. **Week 2**: Cordon old nodes, let new jobs schedule on 1.31 nodes
3. **Week 3**: Wait for all jobs on old nodes to complete naturally
4. **Week 4**: Remove old node pool

This approach ensures zero job interruption while maintaining cluster health. The blue/green node pool strategy is typically the safest for your use case.
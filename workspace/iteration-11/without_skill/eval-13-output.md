Here are several strategies to handle this upgrade scenario while preserving your long-running batch jobs:

## Option 1: Node Pool Rotation (Recommended)

Create a new node pool with 1.31, migrate jobs gradually, then remove the old pool:

```bash
# Create new node pool with 1.31
gcloud container node-pools create batch-pool-v131 \
  --cluster=your-cluster \
  --zone=your-zone \
  --machine-type=your-machine-type \
  --num-nodes=desired-count \
  --node-version=1.31.x-gke.xxxx

# Cordon old nodes to prevent new job scheduling
kubectl cordon -l cloud.google.com/gke-nodepool=old-pool-name

# Wait for existing jobs to complete naturally
# Monitor with: kubectl get jobs -A

# Once jobs complete, drain and delete old pool
kubectl drain -l cloud.google.com/gke-nodepool=old-pool-name --ignore-daemonsets
gcloud container node-pools delete old-pool-name --cluster=your-cluster
```

## Option 2: Maintenance Window with Job Checkpointing

If your jobs support checkpointing:

```yaml
# Job with checkpoint/resume capability
apiVersion: batch/v1
kind: Job
metadata:
  name: resumable-batch-job
spec:
  template:
    spec:
      containers:
      - name: batch-worker
        image: your-batch-image
        env:
        - name: CHECKPOINT_ENABLED
          value: "true"
        - name: CHECKPOINT_INTERVAL
          value: "3600" # Every hour
        volumeMounts:
        - name: checkpoint-storage
          mountPath: /checkpoints
      volumes:
      - name: checkpoint-storage
        persistentVolumeClaim:
          claimName: checkpoint-pvc
      restartPolicy: OnFailure
```

## Option 3: Cluster Migration Strategy

For maximum safety, create a new cluster:

```bash
# Export current cluster config
kubectl get jobs -A -o yaml > running-jobs.yaml

# Create new 1.31 cluster
gcloud container clusters create batch-cluster-v131 \
  --release-channel=regular \
  --cluster-version=1.31.x-gke.xxxx \
  --zone=your-zone

# Gradually migrate completed jobs to new cluster
# Keep old cluster until all jobs finish
```

## Option 4: Scheduled Upgrade with Extended Maintenance Window

```bash
# Disable auto-upgrade temporarily
gcloud container clusters update your-cluster \
  --no-enable-autoupgrade

# Schedule upgrade during low-activity period
# Plan for 2-3x normal maintenance window

# Set up monitoring for job completion
kubectl get jobs -A --watch
```

## Best Practices During Upgrade

### 1. Pre-upgrade Preparation
```bash
# Backup job definitions
kubectl get jobs -A -o yaml > job-backup-$(date +%Y%m%d).yaml

# Document running jobs
kubectl get jobs -A --show-labels > running-jobs-status.txt
```

### 2. Job Monitoring Script
```bash
#!/bin/bash
# monitor-jobs.sh
while true; do
  RUNNING_JOBS=$(kubectl get jobs -A --field-selector status.active=1 --no-headers | wc -l)
  echo "$(date): $RUNNING_JOBS jobs still running"
  if [ $RUNNING_JOBS -eq 0 ]; then
    echo "All jobs completed - safe to proceed with upgrade"
    break
  fi
  sleep 300 # Check every 5 minutes
done
```

### 3. Job Resilience Improvements
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: resilient-batch-job
spec:
  backoffLimit: 3
  activeDeadlineSeconds: 57600 # 16 hours
  template:
    spec:
      containers:
      - name: batch-worker
        resources:
          requests:
            memory: "4Gi"
            cpu: "2"
        # Add health checks and graceful shutdown
        lifecycle:
          preStop:
            exec:
              command: ["/bin/sh", "-c", "cleanup-and-checkpoint.sh"]
      restartPolicy: OnFailure
      tolerations:
      - key: "node.kubernetes.io/unschedulable"
        operator: "Exists"
        effect: "NoSchedule"
```

## Recommended Approach

For your scenario, I recommend **Option 1 (Node Pool Rotation)** because:

- Zero disruption to running jobs
- Gradual migration capability  
- Easy rollback if issues arise
- Maintains cluster availability

**Timeline:**
1. Week 1: Create new node pool, test with small jobs
2. Week 2-3: Cordon old nodes, let jobs complete naturally
3. Week 4: Remove old node pool

This approach respects your job completion requirements while ensuring a smooth upgrade path.
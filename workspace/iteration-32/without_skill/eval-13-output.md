For long-running batch jobs during GKE upgrades, you have several strategies to avoid killing jobs mid-execution:

## 1. **Use Node Pool Blue-Green Strategy** (Recommended)

Create a new node pool with the target version and gradually migrate workloads:

```bash
# Create new node pool with v1.31
gcloud container node-pools create pool-v131 \
  --cluster=your-cluster \
  --zone=your-zone \
  --machine-type=your-machine-type \
  --num-nodes=3 \
  --node-version=1.31.x

# Cordon old nodes (prevent new scheduling)
kubectl cordon <old-node-names>

# Wait for existing jobs to complete naturally
# Monitor with:
kubectl get jobs --all-namespaces

# Once jobs complete, drain old nodes
kubectl drain <old-node-name> --ignore-daemonsets --delete-emptydir-data

# Delete old node pool
gcloud container node-pools delete old-pool --cluster=your-cluster
```

## 2. **Configure Job-Friendly PodDisruptionBudgets**

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: batch-job-pdb
spec:
  minAvailable: 1  # or maxUnavailable: 0
  selector:
    matchLabels:
      app: your-batch-job
```

## 3. **Upgrade Control Plane First**

```bash
# Upgrade control plane only (doesn't affect running workloads)
gcloud container clusters upgrade your-cluster \
  --master \
  --cluster-version=1.31.x \
  --zone=your-zone
```

## 4. **Use Maintenance Windows and Exclusions**

```bash
# Set maintenance exclusion during peak job hours
gcloud container clusters update your-cluster \
  --add-maintenance-exclusion-name=batch-jobs \
  --add-maintenance-exclusion-start=2024-01-15T20:00:00Z \
  --add-maintenance-exclusion-end=2024-01-16T12:00:00Z
```

## 5. **Implement Checkpointing in Jobs**

Make your jobs resumable:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: resumable-batch-job
spec:
  template:
    spec:
      restartPolicy: OnFailure
      containers:
      - name: batch-processor
        image: your-image
        env:
        - name: CHECKPOINT_DIR
          value: "/checkpoints"
        volumeMounts:
        - name: checkpoint-storage
          mountPath: /checkpoints
      volumes:
      - name: checkpoint-storage
        persistentVolumeClaim:
          claimName: checkpoint-pvc
```

## 6. **Complete Workflow Example**

```bash
#!/bin/bash

# 1. Check running jobs
echo "Current running jobs:"
kubectl get jobs --all-namespaces | grep -v Complete

# 2. Upgrade control plane first
gcloud container clusters upgrade your-cluster --master --cluster-version=1.31.x

# 3. Create new node pool
gcloud container node-pools create pool-v131 \
  --cluster=your-cluster \
  --machine-type=n1-standard-4 \
  --num-nodes=3 \
  --node-version=1.31.x

# 4. Cordon old nodes
kubectl get nodes -l cloud.google.com/gke-nodepool=old-pool -o name | \
  xargs kubectl cordon

# 5. Wait for jobs to complete (check periodically)
while kubectl get jobs --all-namespaces | grep -q Running; do
  echo "Jobs still running, waiting..."
  sleep 300  # Check every 5 minutes
done

# 6. Drain and delete old pool
kubectl get nodes -l cloud.google.com/gke-nodepool=old-pool -o name | \
  xargs kubectl drain --ignore-daemonsets --delete-emptydir-data --force

gcloud container node-pools delete old-pool --cluster=your-cluster
```

## 7. **Switch to Rapid Channel Temporarily**

For more control over upgrade timing:

```bash
# Switch to Rapid channel for manual control
gcloud container clusters update your-cluster \
  --release-channel=rapid

# Perform upgrade when ready
gcloud container clusters upgrade your-cluster \
  --cluster-version=1.31.x
```

## Best Practices:

- **Monitor job completion** before proceeding with node upgrades
- **Use persistent volumes** for job state/checkpoints
- **Test the upgrade process** in a staging environment first
- **Schedule upgrades** during low-activity periods
- **Consider using Spot instances** for the new node pool to reduce costs during transition

The blue-green node pool strategy is typically the safest approach for your use case, as it provides complete isolation between old and new infrastructure.
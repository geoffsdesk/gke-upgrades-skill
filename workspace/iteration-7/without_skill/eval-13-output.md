Here are several strategies to upgrade your GKE cluster without disrupting long-running batch jobs:

## Option 1: Blue-Green Cluster Strategy (Recommended)

Create a new cluster with v1.31 and migrate workloads:

```bash
# Create new cluster
gcloud container clusters create batch-cluster-v131 \
  --zone=us-central1-a \
  --cluster-version=1.31 \
  --release-channel=regular \
  --node-pool-config-similar-to-existing

# Gradually migrate new jobs to new cluster
# Let existing jobs complete on old cluster
# Decommission old cluster when empty
```

## Option 2: Maintenance Window Strategy

Schedule upgrades during low-activity periods:

```bash
# Set maintenance window (e.g., weekends)
gcloud container clusters update CLUSTER_NAME \
  --maintenance-window-start="2024-01-06T02:00:00Z" \
  --maintenance-window-end="2024-01-06T06:00:00Z" \
  --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SA"
```

## Option 3: Gradual Node Pool Upgrade

Control the upgrade process manually:

```bash
# Disable auto-upgrade temporarily
gcloud container node-pools update POOL_NAME \
  --cluster=CLUSTER_NAME \
  --no-enable-autoupgrade

# Add new node pool with v1.31
gcloud container node-pools create pool-v131 \
  --cluster=CLUSTER_NAME \
  --machine-type=n1-standard-4 \
  --node-version=1.31.x

# Cordon old nodes to prevent new job scheduling
kubectl cordon NODE_NAME

# Wait for jobs to complete, then drain nodes
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data

# Delete old node pool
gcloud container node-pools delete old-pool --cluster=CLUSTER_NAME
```

## Option 4: Job Management with Node Selectors

Use node selectors to control job placement:

```yaml
# Job template with node selector
apiVersion: batch/v1
kind: Job
metadata:
  name: long-running-job
spec:
  template:
    spec:
      nodeSelector:
        node-version: "v1.30"  # Pin to current version
      containers:
      - name: batch-job
        image: your-image
      restartPolicy: Never
```

## Option 5: Preemptible Job Design

Make jobs resumable:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: resumable-job
spec:
  template:
    spec:
      containers:
      - name: job
        image: your-job-image
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

## Recommended Implementation Plan

1. **Immediate**: Implement job checkpointing for future resilience
2. **Short-term**: Use blue-green cluster strategy for this upgrade
3. **Long-term**: Design jobs to be interruptible with proper state management

## Monitoring During Upgrade

```bash
# Monitor job completion
kubectl get jobs --watch

# Check node status
kubectl get nodes -o wide

# Monitor cluster events
kubectl get events --sort-by='.lastTimestamp'
```

The **blue-green cluster approach** is typically the safest for mission-critical batch jobs, as it provides complete isolation and rollback capability.
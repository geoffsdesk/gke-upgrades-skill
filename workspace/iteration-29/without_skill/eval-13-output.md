Here are several strategies to handle your GKE upgrade without killing long-running batch jobs:

## Option 1: Blue-Green Cluster Strategy (Recommended)

Create a parallel cluster and migrate workloads:

```yaml
# Create new cluster with 1.31
gcloud container clusters create my-cluster-v131 \
  --zone=us-central1-a \
  --cluster-version=1.31.x \
  --release-channel=regular \
  --machine-type=n1-standard-4 \
  --num-nodes=3
```

Then gradually shift new jobs to the new cluster while letting existing jobs complete on the old cluster.

## Option 2: Node Pool Rolling Strategy

Add a new node pool with 1.31, then drain old pools:

```bash
# Add new node pool with 1.31
gcloud container node-pools create pool-v131 \
  --cluster=my-cluster \
  --zone=us-central1-a \
  --node-version=1.31.x \
  --machine-type=n1-standard-4 \
  --num-nodes=3

# Cordon old nodes to prevent new jobs
kubectl cordon -l cloud.google.com/gke-nodepool=old-pool-name

# Wait for existing jobs to complete, then drain
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --force --grace-period=300
```

## Option 3: Job Checkpointing

Implement checkpointing in your batch jobs:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: long-running-job
spec:
  template:
    spec:
      containers:
      - name: batch-processor
        image: your-job:latest
        env:
        - name: CHECKPOINT_INTERVAL
          value: "3600"  # Save state every hour
        - name: CHECKPOINT_PATH
          value: "/checkpoints"
        volumeMounts:
        - name: checkpoint-storage
          mountPath: /checkpoints
      volumes:
      - name: checkpoint-storage
        persistentVolumeClaim:
          claimName: checkpoint-pvc
      restartPolicy: OnFailure
```

## Option 4: Maintenance Window with Job Scheduling

Use node selectors and taints to control job placement:

```yaml
# Taint nodes during maintenance
kubectl taint nodes NODE_NAME maintenance=true:NoSchedule

# Schedule jobs with toleration
apiVersion: batch/v1
kind: Job
metadata:
  name: batch-job
spec:
  template:
    spec:
      nodeSelector:
        maintenance: "false"
      tolerations:
      - key: "maintenance"
        operator: "Equal"
        value: "true"
        effect: "NoSchedule"
```

## Option 5: Use Maintenance Exclusions

Configure a maintenance exclusion window:

```bash
gcloud container clusters update my-cluster \
  --maintenance-exclusion-start=2024-01-15T09:00:00Z \
  --maintenance-exclusion-end=2024-01-16T18:00:00Z \
  --maintenance-exclusion-name="batch-job-protection"
```

## Recommended Approach

For your use case, I recommend **combining approaches**:

1. **Immediate**: Set up maintenance exclusions to prevent automatic updates
2. **Short-term**: Implement the blue-green cluster strategy
3. **Long-term**: Add checkpointing to your batch jobs for future upgrades

```bash
# Step 1: Protect current jobs
gcloud container clusters update my-cluster \
  --maintenance-exclusion-start=$(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --maintenance-exclusion-end=$(date -u -d '+3 days' +%Y-%m-%dT%H:%M:%SZ) \
  --maintenance-exclusion-name="batch-upgrade-protection"

# Step 2: Create new cluster
gcloud container clusters create my-cluster-v131 \
  --zone=us-central1-a \
  --cluster-version=1.31.x \
  --release-channel=regular

# Step 3: Route new jobs to new cluster, monitor old cluster until jobs complete
```

This approach gives you immediate protection while providing a clean migration path without job interruption.
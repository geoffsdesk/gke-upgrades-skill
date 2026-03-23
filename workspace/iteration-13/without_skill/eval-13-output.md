For long-running batch jobs during a GKE upgrade, you have several strategies to avoid killing jobs mid-execution:

## Option 1: Manual Node Pool Upgrade (Recommended)

Disable auto-upgrade temporarily and control the timing:

```yaml
# Disable auto-upgrade on your node pool
gcloud container node-pools update [NODE_POOL] \
  --cluster=[CLUSTER_NAME] \
  --zone=[ZONE] \
  --no-enable-autoupgrade
```

Then upgrade manually during maintenance windows:

```bash
# Upgrade control plane first
gcloud container clusters upgrade [CLUSTER_NAME] \
  --master \
  --cluster-version=1.31.x-gke.y

# Upgrade nodes when no critical jobs are running
gcloud container node-pools upgrade [NODE_POOL] \
  --cluster=[CLUSTER_NAME] \
  --zone=[ZONE]
```

## Option 2: Blue-Green Node Pool Strategy

Create a new node pool with 1.31 and migrate workloads:

```yaml
# Create new node pool with 1.31
gcloud container node-pools create batch-jobs-v131 \
  --cluster=[CLUSTER_NAME] \
  --zone=[ZONE] \
  --node-version=1.31.x-gke.y \
  --num-nodes=3

# Add node selector to new jobs
apiVersion: batch/v1
kind: Job
metadata:
  name: batch-job-new
spec:
  template:
    spec:
      nodeSelector:
        cloud.google.com/gke-nodepool: batch-jobs-v131
      containers:
      - name: job
        image: your-image
```

## Option 3: Configure PodDisruptionBudgets

Protect running jobs during rolling updates:

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: batch-job-pdb
spec:
  minAvailable: 1
  selector:
    matchLabels:
      job-type: batch-processing
```

## Option 4: Use Maintenance Windows

Configure maintenance exclusions for your known job schedules:

```yaml
gcloud container clusters update [CLUSTER_NAME] \
  --zone=[ZONE] \
  --add-maintenance-exclusion-name=batch-window \
  --add-maintenance-exclusion-start=2024-01-15T09:00:00Z \
  --add-maintenance-exclusion-end=2024-01-15T18:00:00Z
```

## Best Practices for Long-Running Jobs

1. **Make jobs resumable:**
```yaml
apiVersion: batch/v1
kind: Job
spec:
  backoffLimit: 3
  template:
    spec:
      restartPolicy: OnFailure
      containers:
      - name: batch-job
        image: your-image
        # Implement checkpointing in your application
```

2. **Use higher priority classes:**
```yaml
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: high-priority-batch
value: 1000
globalDefault: false
description: "High priority for long-running batch jobs"
```

## Recommended Approach

For your situation, I'd recommend **Option 1 (Manual Control)** combined with **Option 2 (Blue-Green)**:

1. Disable auto-upgrade immediately
2. Create a new node pool with 1.31
3. Let current jobs finish on old nodes
4. Schedule new jobs on the 1.31 node pool
5. Remove the old node pool once all jobs complete
6. Re-enable auto-upgrade if desired

This gives you complete control over timing while ensuring zero job interruption.
For your long-running batch jobs during a GKE upgrade, here are the best strategies to avoid job interruption:

## Option 1: Use Node Pool Surge Upgrade (Recommended)

Configure surge upgrade settings to minimize disruption:

```yaml
# Configure node pool with surge upgrade
gcloud container node-pools update [POOL-NAME] \
    --cluster=[CLUSTER-NAME] \
    --zone=[ZONE] \
    --max-surge-upgrade=2 \
    --max-unavailable-upgrade=0
```

This creates new nodes before draining old ones, allowing jobs to complete naturally.

## Option 2: Blue-Green Node Pool Strategy

Create a new node pool with v1.31 and migrate workloads:

```bash
# Create new node pool with v1.31
gcloud container node-pools create pool-v131 \
    --cluster=[CLUSTER-NAME] \
    --node-version=1.31.x \
    --num-nodes=3

# Cordon old nodes to prevent new scheduling
kubectl cordon [OLD-NODE-NAME]

# Wait for current jobs to complete, then drain
kubectl drain [OLD-NODE-NAME] --ignore-daemonsets --delete-emptydir-data
```

## Option 3: Schedule Upgrade During Low Activity

Time the upgrade for your maintenance window:

```bash
# Schedule upgrade during planned downtime
gcloud container clusters upgrade [CLUSTER-NAME] \
    --master \
    --cluster-version=1.31.x

# Then upgrade node pools
gcloud container node-pools upgrade [POOL-NAME] \
    --cluster=[CLUSTER-NAME] \
    --cluster-version=1.31.x
```

## Option 4: Job-Aware Configuration

Configure your batch jobs to handle interruptions gracefully:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: long-running-job
spec:
  backoffLimit: 3
  activeDeadlineSeconds: 57600  # 16 hours
  template:
    spec:
      restartPolicy: OnFailure
      terminationGracePeriodSeconds: 300
      containers:
      - name: batch-job
        image: your-image
        # Add checkpoint/resume logic if possible
```

## Recommended Approach

1. **Use surge upgrade** with `max-unavailable-upgrade=0`
2. **Monitor job completion** before allowing node drain
3. **Upgrade during maintenance windows** when possible
4. **Implement job checkpointing** for future resilience

The surge upgrade approach is typically best as it maintains capacity while upgrading, minimizing the risk to your long-running jobs.
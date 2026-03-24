For your long-running batch jobs, you'll need to plan the upgrade carefully to avoid job interruption. Here are the best approaches:

## Option 1: Node Pool Upgrade with Surge Settings (Recommended)

Configure your node pool to handle upgrades gracefully:

```yaml
# Configure node pool with surge upgrade strategy
gcloud container node-pools update [POOL_NAME] \
  --cluster=[CLUSTER_NAME] \
  --zone=[ZONE] \
  --max-surge-upgrade=1 \
  --max-unavailable-upgrade=0
```

This ensures new nodes are added before old ones are drained, giving jobs time to complete.

## Option 2: Manual Upgrade Control

Temporarily switch to manual upgrades for precise control:

```bash
# Disable auto-upgrade temporarily
gcloud container node-pools update [POOL_NAME] \
  --cluster=[CLUSTER_NAME] \
  --zone=[ZONE] \
  --no-enable-autoupgrade

# Upgrade when ready
gcloud container node-pools upgrade [POOL_NAME] \
  --cluster=[CLUSTER_NAME] \
  --zone=[ZONE] \
  --node-version=1.31.x
```

## Option 3: Blue-Green Node Pool Strategy

Create a new node pool alongside the existing one:

```bash
# Create new node pool with 1.31
gcloud container node-pools create new-pool-v131 \
  --cluster=[CLUSTER_NAME] \
  --zone=[ZONE] \
  --node-version=1.31.x \
  --num-nodes=3

# Cordon old nodes to prevent new job scheduling
kubectl cordon [OLD_NODE_NAME]

# Wait for existing jobs to complete, then delete old pool
gcloud container node-pools delete [OLD_POOL_NAME] \
  --cluster=[CLUSTER_NAME] \
  --zone=[ZONE]
```

## Job-Level Protection

Ensure your batch jobs have appropriate configurations:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: long-running-batch
spec:
  template:
    spec:
      restartPolicy: Never
      # Prevent preemption during upgrades
      priorityClassName: high-priority
      # Graceful shutdown handling
      terminationGracePeriodSeconds: 3600
      containers:
      - name: batch-job
        image: your-image
        # Handle SIGTERM gracefully in your application
```

## Monitoring Strategy

Set up monitoring to track job status during upgrades:

```bash
# Monitor running jobs
kubectl get jobs -w

# Check node drain status
kubectl describe node [NODE_NAME] | grep Unschedulable

# Monitor pod evictions
kubectl get events --field-selector reason=Evicted
```

## Recommended Approach

1. **Schedule during low activity**: Plan upgrades when fewer long-running jobs are expected
2. **Use surge upgrades**: Set `max-surge-upgrade=1` and `max-unavailable-upgrade=0`
3. **Monitor job completion**: Track running jobs before initiating upgrades
4. **Consider job checkpointing**: If possible, implement checkpointing in your batch jobs for resume capability

The surge upgrade strategy is typically the safest approach as it minimizes disruption while maintaining cluster capacity during the upgrade process.
For long-running batch jobs during a GKE upgrade, you have several strategies to avoid disrupting critical workloads. Here are the best approaches:

## Option 1: Manual Node Pool Management (Recommended)

Create a new node pool with the target version and drain jobs naturally:

```bash
# Create new node pool with 1.31
gcloud container node-pools create "pool-v1-31" \
  --cluster=your-cluster \
  --machine-type=your-machine-type \
  --num-nodes=3 \
  --node-version=1.31.x-gke.y

# Cordon old nodes to prevent new job scheduling
kubectl cordon <old-node-names>

# Monitor running jobs
kubectl get jobs --all-namespaces
kubectl get pods --field-selector=status.phase=Running

# Once jobs complete, drain and delete old pool
kubectl drain <old-nodes> --ignore-daemonsets --delete-emptydir-data
gcloud container node-pools delete old-pool --cluster=your-cluster
```

## Option 2: Switch to Rapid Release Channel Temporarily

The Rapid channel gives you more control over timing:

```bash
# Switch to Rapid channel
gcloud container clusters update your-cluster \
  --release-channel=rapid

# Pause auto-upgrades
gcloud container clusters update your-cluster \
  --no-enable-autoupgrade

# Upgrade when ready
gcloud container clusters upgrade your-cluster \
  --master --cluster-version=1.31.x-gke.y

# Upgrade node pools manually after jobs complete
gcloud container node-pools upgrade your-node-pool \
  --cluster=your-cluster \
  --node-version=1.31.x-gke.y
```

## Option 3: Job-Aware Scheduling Strategy

Configure your batch jobs to be more resilient:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: long-running-job
spec:
  backoffLimit: 3
  template:
    spec:
      restartPolicy: OnFailure
      # Add node affinity to control placement
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
            - matchExpressions:
              - key: node-version
                operator: In
                values: ["stable"]
      tolerations:
      - key: "batch-workload"
        operator: "Equal"
        value: "true"
        effect: "NoSchedule"
      containers:
      - name: job
        image: your-image
        # Add graceful shutdown handling
        lifecycle:
          preStop:
            exec:
              command: ["/bin/sh", "-c", "cleanup.sh"]
```

## Option 4: Maintenance Window Strategy

```bash
# Disable auto-upgrade temporarily
gcloud container clusters update your-cluster \
  --no-enable-autoupgrade

# Set up monitoring for job completion
kubectl get jobs -w

# Create maintenance window configuration
gcloud container clusters update your-cluster \
  --maintenance-window-start="2024-01-15T02:00:00Z" \
  --maintenance-window-end="2024-01-15T06:00:00Z" \
  --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SU"
```

## Monitoring Script for Job Completion

```bash
#!/bin/bash
# wait-for-jobs.sh

while true; do
  RUNNING_JOBS=$(kubectl get jobs --all-namespaces -o json | \
    jq -r '.items[] | select(.status.conditions == null or 
    (.status.conditions[] | select(.type == "Complete" or .type == "Failed") | length) == 0) | 
    .metadata.name')
  
  if [ -z "$RUNNING_JOBS" ]; then
    echo "All jobs completed. Safe to upgrade."
    break
  else
    echo "Jobs still running: $RUNNING_JOBS"
    sleep 300  # Check every 5 minutes
  fi
done
```

## Best Practices for Future Upgrades

1. **Implement checkpointing** in your batch jobs:
```dockerfile
# Save progress periodically
COPY checkpoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/checkpoint.sh
```

2. **Use PodDisruptionBudgets** (though limited for Jobs):
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: batch-job-pdb
spec:
  minAvailable: 1
  selector:
    matchLabels:
      job-type: critical-batch
```

3. **Consider CronJobs** for better restart capability:
```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: resumable-batch-job
spec:
  schedule: "@hourly"  # Adjust as needed
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: worker
            image: your-image
            command: ["./resume-or-start.sh"]
```

## Recommended Approach

For your situation, I'd recommend **Option 1 (Manual Node Pool Management)**:

1. Create new 1.31 node pool
2. Cordon existing nodes
3. Let current jobs finish naturally
4. New jobs will schedule on 1.31 nodes
5. Remove old node pool once empty

This gives you complete control without risking job interruption.
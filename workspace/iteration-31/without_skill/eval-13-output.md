Here are several strategies to handle this upgrade without disrupting your long-running batch jobs:

## Strategy 1: Blue-Green Cluster Migration (Recommended)

Create a new cluster with 1.31 and gradually migrate workloads:

```bash
# Create new cluster with 1.31
gcloud container clusters create batch-cluster-v131 \
    --zone=us-central1-a \
    --cluster-version=1.31 \
    --release-channel=regular \
    --num-nodes=3

# Configure kubectl contexts
kubectl config rename-context gke_PROJECT_ZONE_OLD-CLUSTER old-cluster
kubectl config rename-context gke_PROJECT_ZONE_NEW-CLUSTER new-cluster

# Stop scheduling new jobs on old cluster
kubectl --context=old-cluster cordon --all

# Monitor running jobs
kubectl --context=old-cluster get jobs --all-namespaces
```

Wait for existing jobs to complete, then migrate your job definitions to the new cluster.

## Strategy 2: Node Pool Replacement

Replace node pools incrementally while preserving running jobs:

```bash
# Create new node pool with 1.31
gcloud container node-pools create pool-v131 \
    --cluster=your-cluster \
    --zone=us-central1-a \
    --node-version=1.31 \
    --num-nodes=3

# Cordon old nodes to prevent new scheduling
kubectl cordon -l cloud.google.com/gke-nodepool=default-pool

# Add node selector to new jobs
kubectl patch cronjob my-batch-job -p '{"spec":{"jobTemplate":{"spec":{"template":{"spec":{"nodeSelector":{"cloud.google.com/gke-nodepool":"pool-v131"}}}}}}}'
```

## Strategy 3: Maintenance Window with Job Rescheduling

Configure jobs to be reschedulable and plan maintenance windows:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: resumable-batch-job
spec:
  backoffLimit: 3
  template:
    spec:
      restartPolicy: OnFailure
      containers:
      - name: batch-processor
        image: your-app:latest
        env:
        - name: CHECKPOINT_ENABLED
          value: "true"
        - name: CHECKPOINT_INTERVAL
          value: "300" # Save state every 5 minutes
        resources:
          requests:
            memory: "4Gi"
            cpu: "2"
        volumeMounts:
        - name: checkpoint-storage
          mountPath: /checkpoints
      volumes:
      - name: checkpoint-storage
        persistentVolumeClaim:
          claimName: checkpoint-pvc
      nodeSelector:
        workload-type: batch
```

## Strategy 4: Pause Auto-Upgrades and Manual Control

Temporarily disable auto-upgrades and control timing:

```bash
# Switch to no-release channel for manual control
gcloud container clusters update your-cluster \
    --release-channel=None

# Later, manually upgrade when jobs complete
gcloud container clusters upgrade your-cluster \
    --cluster-version=1.31.0-gke.1146000

# Monitor job completion
kubectl get jobs --all-namespaces --watch
```

## Job Monitoring and Safety Script

```bash
#!/bin/bash
# check-jobs.sh - Monitor running jobs before upgrade

echo "Checking for running jobs..."
RUNNING_JOBS=$(kubectl get jobs --all-namespaces -o jsonpath='{.items[?(@.status.active>0)].metadata.name}')

if [ -n "$RUNNING_JOBS" ]; then
    echo "⚠️  Active jobs found: $RUNNING_JOBS"
    echo "Estimated completion times:"
    kubectl get jobs --all-namespaces -o custom-columns=NAME:.metadata.name,NAMESPACE:.metadata.namespace,ACTIVE:.status.active,DURATION:.status.startTime --no-headers | while read job; do
        echo "  $job"
    done
    exit 1
else
    echo "✅ No active jobs - safe to upgrade"
fi
```

## Best Practices for Future Upgrades

1. **Implement checkpointing** in your batch jobs:
```dockerfile
# Add to your batch job container
COPY checkpoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/checkpoint.sh

# In your application
ENV CHECKPOINT_DIR=/var/checkpoints
ENV ENABLE_CHECKPOINTS=true
```

2. **Use Pod Disruption Budgets**:
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: batch-job-pdb
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: batch-processor
```

3. **Set appropriate termination grace periods**:
```yaml
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 1800  # 30 minutes
```

## Recommended Approach

For your situation, I'd recommend **Strategy 1 (Blue-Green)** because:
- Zero disruption to running jobs
- Easy rollback if issues arise
- Clean separation between old and new environments
- You can validate 1.31 compatibility before full migration

The process would be:
1. Create new 1.31 cluster
2. Stop new job scheduling on old cluster
3. Wait for current jobs to complete (8-16 hours)
4. Migrate job definitions and data to new cluster
5. Decommission old cluster

Would you like me to elaborate on any of these strategies or help you implement the migration plan?
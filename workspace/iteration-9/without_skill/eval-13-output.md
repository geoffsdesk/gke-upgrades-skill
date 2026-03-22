For your long-running batch jobs during a GKE upgrade, here are several strategies to handle this safely:

## 1. **Node Pool Rolling Strategy** (Recommended)

Create a temporary node pool for the upgrade:

```bash
# Create new node pool with 1.31
gcloud container node-pools create temp-pool-131 \
  --cluster=your-cluster \
  --machine-type=your-machine-type \
  --num-nodes=3 \
  --node-version=1.31.x-gke.y

# Cordon old nodes to prevent new job scheduling
kubectl cordon -l cloud.google.com/gke-nodepool=your-old-pool

# Wait for current jobs to complete naturally
# Monitor with: kubectl get jobs,pods -o wide

# Once jobs complete, drain and delete old pool
kubectl drain -l cloud.google.com/gke-nodepool=your-old-pool --ignore-daemonsets --delete-emptydir-data
gcloud container node-pools delete your-old-pool --cluster=your-cluster
```

## 2. **Configure Job Scheduling Controls**

Prevent jobs from starting during maintenance windows:

```yaml
# Add node affinity to jobs
apiVersion: batch/v1
kind: Job
metadata:
  name: long-batch-job
spec:
  template:
    spec:
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
            - matchExpressions:
              - key: cloud.google.com/gke-nodepool
                operator: In
                values: ["stable-pool"]  # Only schedule on designated pools
      restartPolicy: Never
```

## 3. **Maintenance Window Strategy**

```bash
# Set maintenance exclusions during your batch processing hours
gcloud container clusters update your-cluster \
  --add-maintenance-exclusion-name="batch-processing" \
  --add-maintenance-exclusion-start="2024-01-15T18:00:00Z" \
  --add-maintenance-exclusion-end="2024-01-16T10:00:00Z" \
  --add-maintenance-exclusion-scope="no_upgrades"
```

## 4. **Pod Disruption Budget Protection**

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: batch-job-pdb
spec:
  minAvailable: 1  # or maxUnavailable: 0
  selector:
    matchLabels:
      job-type: long-running-batch
```

## 5. **Checkpoint and Resume Pattern**

For jobs that support it, implement checkpointing:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: resumable-batch-job
spec:
  template:
    spec:
      containers:
      - name: batch-processor
        image: your-image
        env:
        - name: CHECKPOINT_PATH
          value: "/checkpoints"
        - name: RESUME_FROM_CHECKPOINT
          value: "true"
        volumeMounts:
        - name: checkpoint-storage
          mountPath: /checkpoints
      volumes:
      - name: checkpoint-storage
        persistentVolumeClaim:
          claimName: checkpoint-pvc
```

## 6. **Monitoring and Automation Script**

```bash
#!/bin/bash
# check-jobs-before-upgrade.sh

echo "Checking for running batch jobs..."
RUNNING_JOBS=$(kubectl get jobs -o jsonpath='{.items[?(@.status.active>0)].metadata.name}')

if [ ! -z "$RUNNING_JOBS" ]; then
    echo "Active jobs found: $RUNNING_JOBS"
    echo "Waiting for completion..."
    
    while [ ! -z "$(kubectl get jobs -o jsonpath='{.items[?(@.status.active>0)].metadata.name}')" ]; do
        echo "Jobs still running. Checking again in 30 minutes..."
        sleep 1800
    done
fi

echo "All jobs completed. Safe to proceed with upgrade."
```

## 7. **Complete Upgrade Workflow**

```bash
# 1. Schedule maintenance window
gcloud container clusters update your-cluster \
  --maintenance-window-start="2024-01-20T02:00:00Z" \
  --maintenance-window-end="2024-01-20T06:00:00Z" \
  --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SA"

# 2. Create new node pool
gcloud container node-pools create pool-131 \
  --cluster=your-cluster \
  --node-version=1.31.x-gke.y \
  --num-nodes=3

# 3. Cordon old nodes
kubectl cordon -l cloud.google.com/gke-nodepool=old-pool

# 4. Wait for jobs to complete (use monitoring script)
./check-jobs-before-upgrade.sh

# 5. Upgrade control plane
gcloud container clusters upgrade your-cluster \
  --master --cluster-version=1.31.x-gke.y

# 6. Clean up old pool
gcloud container node-pools delete old-pool --cluster=your-cluster
```

## Best Practices:

1. **Test in staging** with similar job patterns first
2. **Monitor job completion** before proceeding with each step  
3. **Use gradual rollout** - upgrade one node pool at a time
4. **Plan for rollback** - keep old node pool until confident
5. **Consider job queuing systems** like Argo Workflows for better control

The node pool strategy gives you the most control and safety for your long-running batch jobs.
Here's a comprehensive strategy to upgrade your GKE cluster without interrupting long-running batch jobs:

## 1. Use Node Pool Blue-Green Strategy

Create a new node pool with the upgraded version while keeping jobs on the old pool:

```bash
# Create new node pool with v1.30
gcloud container node-pools create "pool-v130" \
  --cluster="your-cluster" \
  --zone="your-zone" \
  --machine-type="n1-standard-4" \
  --num-nodes=3 \
  --node-version="1.30.x-gke.xxxx"

# Verify both pools exist
kubectl get nodes -o wide
```

## 2. Implement Node Selectors for Job Control

Add node selectors to control where new jobs are scheduled:

```yaml
# For existing long-running jobs (already scheduled)
apiVersion: batch/v1
kind: Job
metadata:
  name: batch-job-legacy
spec:
  template:
    spec:
      nodeSelector:
        cloud.google.com/gke-nodepool: "default-pool"  # old pool
      containers:
      - name: batch-processor
        image: your-image
```

```yaml
# For new jobs on upgraded nodes
apiVersion: batch/v1
kind: Job
metadata:
  name: batch-job-new
spec:
  template:
    spec:
      nodeSelector:
        cloud.google.com/gke-nodepool: "pool-v130"  # new pool
      containers:
      - name: batch-processor
        image: your-image
```

## 3. Prevent Disruptions on Old Nodes

Cordon old nodes to prevent new workloads while allowing existing jobs to complete:

```bash
# Cordon all nodes in the old pool
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool -o name | \
  xargs kubectl cordon

# Verify cordoned status
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool
```

## 4. Monitor Job Completion

Create a script to monitor running batch jobs:

```bash
#!/bin/bash
# monitor-jobs.sh

echo "Monitoring batch jobs on old node pool..."
while true; do
    RUNNING_JOBS=$(kubectl get jobs -A -o json | \
      jq -r '.items[] | select(.status.active > 0) | 
      select(.spec.template.spec.nodeSelector."cloud.google.com/gke-nodepool" == "default-pool") | 
      .metadata.name')
    
    if [ -z "$RUNNING_JOBS" ]; then
        echo "No active jobs on old node pool. Safe to proceed with cleanup."
        break
    else
        echo "Active jobs still running: $RUNNING_JOBS"
        echo "Waiting 30 minutes before next check..."
        sleep 1800  # 30 minutes
    fi
done
```

## 5. Implement Graceful Shutdown Handling

Ensure your batch jobs handle termination gracefully:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: resilient-batch-job
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 3600  # 1 hour for cleanup
      containers:
      - name: batch-processor
        image: your-image
        command: ["/app/batch-processor"]
        lifecycle:
          preStop:
            exec:
              command: ["/app/graceful-shutdown.sh"]
```

## 6. Step-by-Step Upgrade Process

```bash
# Step 1: Upgrade control plane first
gcloud container clusters upgrade your-cluster \
  --master --cluster-version="1.30.x-gke.xxxx" \
  --zone="your-zone"

# Step 2: Create new node pool (as shown above)

# Step 3: Cordon old nodes (as shown above)

# Step 4: Update job scheduling to use new nodes
kubectl patch deployment job-scheduler -p \
  '{"spec":{"template":{"spec":{"nodeSelector":{"cloud.google.com/gke-nodepool":"pool-v130"}}}}}'

# Step 5: Wait for all jobs to complete (use monitoring script)

# Step 6: Delete old node pool
gcloud container node-pools delete "default-pool" \
  --cluster="your-cluster" \
  --zone="your-zone"
```

## 7. Alternative: Use Maintenance Windows

If you have predictable quiet periods:

```bash
# Schedule upgrade during maintenance window
gcloud container clusters upgrade your-cluster \
  --start-time="2024-01-15T02:00:00Z" \
  --cluster-version="1.30.x-gke.xxxx"
```

## 8. Backup Strategy for Critical Jobs

Implement checkpointing for long-running jobs:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: checkpoint-batch-job
spec:
  template:
    spec:
      containers:
      - name: batch-processor
        image: your-image
        volumeMounts:
        - name: checkpoint-storage
          mountPath: /checkpoints
        env:
        - name: CHECKPOINT_INTERVAL
          value: "300"  # Save state every 5 minutes
      volumes:
      - name: checkpoint-storage
        persistentVolumeClaim:
          claimName: checkpoint-pvc
```

## 9. Verification Steps

After upgrade completion:

```bash
# Verify cluster version
kubectl version --short

# Verify all nodes are on new version
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion

# Check that jobs can schedule on new nodes
kubectl get pods -A -o wide | grep batch
```

This approach ensures zero downtime for your batch jobs while safely upgrading your cluster infrastructure.
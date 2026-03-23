For long-running batch jobs during GKE upgrades, you have several strategies to avoid killing jobs mid-execution. Here are the best approaches:

## 1. **Manual Upgrade Control (Recommended)**

Switch to manual upgrade mode to control timing:

```bash
# Disable auto-upgrade temporarily
gcloud container clusters update CLUSTER_NAME \
    --no-enable-autoupgrade \
    --zone=ZONE

# Upgrade when ready
gcloud container clusters upgrade CLUSTER_NAME \
    --master-upgrade-max-unavailable=0 \
    --node-upgrade-max-unavailable=1 \
    --zone=ZONE
```

## 2. **Node Pool Cordoning Strategy**

Prevent new jobs on nodes marked for upgrade:

```bash
# Cordon nodes before upgrade
kubectl cordon NODE_NAME

# Wait for existing jobs to complete
kubectl get jobs --watch

# Upgrade specific node pool
gcloud container node-pools upgrade POOL_NAME \
    --cluster=CLUSTER_NAME \
    --zone=ZONE
```

## 3. **Blue-Green Node Pool Approach**

Create a new node pool and migrate gradually:

```yaml
# Create new node pool with v1.31
apiVersion: v1
kind: NodePool
metadata:
  name: batch-pool-v131
spec:
  version: "1.31"
  # Same specs as current pool
```

```bash
# Create new node pool
gcloud container node-pools create batch-pool-v131 \
    --cluster=CLUSTER_NAME \
    --node-version=1.31.x \
    --num-nodes=3 \
    --zone=ZONE

# Gradually drain old pool
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data

# Delete old pool when empty
gcloud container node-pools delete old-pool-name
```

## 4. **Job-Aware Configuration**

Configure your batch jobs to handle disruptions gracefully:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: long-running-batch
spec:
  backoffLimit: 3
  activeDeadlineSeconds: 57600  # 16 hours
  template:
    spec:
      restartPolicy: OnFailure
      terminationGracePeriodSeconds: 300
      nodeSelector:
        batch-pool: "stable"  # Target specific nodes
      containers:
      - name: batch-job
        image: your-image
        resources:
          requests:
            cpu: 2
            memory: 4Gi
```

## 5. **Maintenance Window Planning**

```bash
# Check current job status
kubectl get jobs -o wide
kubectl describe job JOB_NAME

# Set maintenance window
gcloud container clusters update CLUSTER_NAME \
    --maintenance-window-start=2024-01-15T02:00:00Z \
    --maintenance-window-end=2024-01-15T06:00:00Z \
    --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SU"
```

## 6. **Monitoring and Automation Script**

```bash
#!/bin/bash
# upgrade-when-ready.sh

CLUSTER_NAME="your-cluster"
ZONE="your-zone"

check_running_jobs() {
    RUNNING_JOBS=$(kubectl get jobs --field-selector status.successful!=1 --no-headers | wc -l)
    echo "Running jobs: $RUNNING_JOBS"
    return $RUNNING_JOBS
}

wait_for_jobs_completion() {
    while check_running_jobs; do
        if [ $? -eq 0 ]; then
            echo "All jobs completed. Starting upgrade..."
            break
        fi
        echo "Jobs still running. Waiting 30 minutes..."
        sleep 1800  # Wait 30 minutes
    done
}

# Wait for jobs to complete
wait_for_jobs_completion

# Start upgrade
gcloud container clusters upgrade $CLUSTER_NAME --zone=$ZONE --quiet
```

## 7. **Recommended Workflow**

1. **Preparation Phase:**
   ```bash
   # Switch to manual upgrades
   gcloud container clusters update CLUSTER_NAME --no-enable-autoupgrade
   
   # Label nodes for identification
   kubectl label nodes batch-node-1 upgrade-batch=pending
   ```

2. **Execution Phase:**
   ```bash
   # Monitor jobs
   kubectl get jobs --watch
   
   # When jobs complete, upgrade master first
   gcloud container clusters upgrade CLUSTER_NAME --master --zone=ZONE
   
   # Then upgrade nodes in batches
   gcloud container clusters upgrade CLUSTER_NAME --zone=ZONE
   ```

3. **Validation Phase:**
   ```bash
   # Verify cluster health
   kubectl get nodes
   kubectl get jobs
   
   # Re-enable auto-upgrade if desired
   gcloud container clusters update CLUSTER_NAME --enable-autoupgrade
   ```

## Key Considerations:

- **Cost**: Blue-green approach doubles resources temporarily
- **Timing**: Plan upgrades during low-activity periods
- **Monitoring**: Set up alerts for job failures
- **Testing**: Test upgrade process on staging cluster first

The **manual upgrade control** combined with **job monitoring** is typically the most cost-effective approach for your use case.
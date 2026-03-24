Here are several strategies to upgrade your GKE cluster without disrupting your long-running batch jobs:

## Strategy 1: Controlled Node Pool Upgrade with Job Management

### Prepare for the upgrade:
```bash
# 1. Label nodes to track batch jobs
kubectl label nodes <node-name> workload-type=batch-processing

# 2. Add node selectors to your batch jobs
apiVersion: batch/v1
kind: Job
metadata:
  name: batch-job
spec:
  template:
    spec:
      nodeSelector:
        workload-type: batch-processing
      containers:
      - name: batch-processor
        image: your-image
```

### Upgrade approach:
```bash
# 1. Pause auto-upgrades temporarily
gcloud container clusters update CLUSTER_NAME \
    --no-enable-autoupgrade \
    --zone=ZONE

# 2. Create a new node pool with 1.31
gcloud container node-pools create new-pool-131 \
    --cluster=CLUSTER_NAME \
    --zone=ZONE \
    --node-version=1.31.x-gke.y \
    --num-nodes=3

# 3. Gradually drain old nodes only when jobs complete
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --grace-period=300
```

## Strategy 2: Separate Node Pools by Workload Type

### Create dedicated pools:
```bash
# Long-running batch jobs pool
gcloud container node-pools create batch-pool \
    --cluster=CLUSTER_NAME \
    --zone=ZONE \
    --node-taints=workload=batch:NoSchedule \
    --node-labels=workload-type=batch \
    --num-nodes=2

# Regular workloads pool  
gcloud container node-pools create regular-pool \
    --cluster=CLUSTER_NAME \
    --zone=ZONE \
    --node-labels=workload-type=regular \
    --num-nodes=3
```

### Configure job placement:
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: long-batch-job
spec:
  template:
    spec:
      nodeSelector:
        workload-type: batch
      tolerations:
      - key: workload
        operator: Equal
        value: batch
        effect: NoSchedule
      containers:
      - name: processor
        image: your-image
```

## Strategy 3: Job Completion Monitoring

### Monitor running jobs before upgrade:
```bash
#!/bin/bash
# Script to check if it's safe to upgrade

check_running_jobs() {
    RUNNING_JOBS=$(kubectl get jobs -A -o jsonpath='{.items[?(@.status.active>0)].metadata.name}')
    if [ -z "$RUNNING_JOBS" ]; then
        echo "No active jobs - safe to upgrade"
        return 0
    else
        echo "Active jobs found: $RUNNING_JOBS"
        return 1
    fi
}

# Wait for jobs to complete
while ! check_running_jobs; do
    echo "Waiting for jobs to complete..."
    sleep 300  # Check every 5 minutes
done
```

## Strategy 4: Blue-Green Cluster Approach

For critical workloads, consider a separate cluster:

```bash
# 1. Create new cluster with 1.31
gcloud container clusters create cluster-131 \
    --zone=ZONE \
    --cluster-version=1.31.x-gke.y \
    --num-nodes=3

# 2. Migrate workloads gradually
# 3. Decommission old cluster after all jobs complete
```

## Recommended Approach

For your use case, I recommend **Strategy 1** with these modifications:

### Implementation steps:
```bash
# 1. During a low-activity period, upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
    --master \
    --cluster-version=1.31.x-gke.y

# 2. Monitor job completion
kubectl get jobs -A --watch

# 3. When jobs complete, upgrade nodes in batches
gcloud container clusters upgrade CLUSTER_NAME \
    --node-pool=default-pool \
    --cluster-version=1.31.x-gke.y
```

### Add job completion hooks:
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: batch-job
  annotations:
    job.kubernetes.io/completion-mode: "NonIndexed"
spec:
  backoffLimit: 1
  template:
    metadata:
      annotations:
        cluster.k8s.io/machine-suffix: "allow-upgrade-after-completion"
    spec:
      restartPolicy: Never
      containers:
      - name: batch-processor
        image: your-image
        # Add cleanup/notification on completion
```

### Best practices:
1. **Schedule upgrades** during maintenance windows
2. **Use PodDisruptionBudgets** to prevent accidental termination
3. **Implement job checkpointing** where possible
4. **Monitor cluster events** during the upgrade process
5. **Test the upgrade process** on a staging cluster first

Would you like me to elaborate on any of these strategies or help you implement the monitoring scripts?
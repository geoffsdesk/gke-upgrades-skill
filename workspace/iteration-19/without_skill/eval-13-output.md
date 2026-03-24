Here are several strategies to upgrade your GKE cluster without interrupting long-running batch jobs:

## Option 1: Blue-Green Cluster Strategy (Recommended)

Create a new cluster running 1.31 and gradually migrate workloads:

```bash
# Create new cluster with 1.31
gcloud container clusters create batch-cluster-v131 \
    --zone=your-zone \
    --cluster-version=1.31 \
    --release-channel=regular \
    --node-pool-configs similar to existing

# Update your batch job scheduler to prefer the new cluster
# Allow existing jobs to complete on old cluster
# Decommission old cluster once empty
```

## Option 2: Maintenance Window with Job Coordination

```yaml
# Add a job completion check script
apiVersion: batch/v1
kind: CronJob
metadata:
  name: upgrade-readiness-check
spec:
  schedule: "*/30 * * * *"  # Check every 30 minutes
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: job-checker
            image: google/cloud-sdk:alpine
            command:
            - /bin/sh
            - -c
            - |
              RUNNING_JOBS=$(kubectl get jobs --all-namespaces -o json | jq '[.items[] | select(.status.active > 0)] | length')
              if [ $RUNNING_JOBS -eq 0 ]; then
                echo "No running jobs - safe to upgrade"
                # Trigger upgrade automation or send notification
              else
                echo "$RUNNING_JOBS jobs still running"
              fi
```

## Option 3: Node Pool Rotation Strategy

```bash
# 1. Add new node pool with 1.31
gcloud container node-pools create pool-v131 \
    --cluster=your-cluster \
    --zone=your-zone \
    --node-version=1.31.x

# 2. Cordon old nodes to prevent new job scheduling
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool -o name | \
    xargs -I {} kubectl cordon {}

# 3. Add node affinity to ensure new jobs use new nodes
apiVersion: batch/v1
kind: Job
metadata:
  name: batch-job
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
                values: ["pool-v131"]
      containers:
      - name: batch-worker
        image: your-batch-image

# 4. Wait for old jobs to complete, then delete old node pool
gcloud container node-pools delete default-pool --cluster=your-cluster
```

## Option 4: Preemptible/Spot Instance Strategy

If your jobs can handle interruption with checkpointing:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: resumable-batch-job
spec:
  template:
    spec:
      nodeSelector:
        cloud.google.com/gke-spot: "true"
      containers:
      - name: batch-worker
        image: your-batch-image
        env:
        - name: CHECKPOINT_INTERVAL
          value: "3600"  # Checkpoint every hour
        - name: CHECKPOINT_STORAGE
          value: "gs://your-bucket/checkpoints"
        volumeMounts:
        - name: checkpoint-storage
          mountPath: /checkpoints
```

## Monitoring and Validation Script

```bash
#!/bin/bash
# upgrade-monitor.sh

check_running_jobs() {
    kubectl get jobs --all-namespaces -o json | \
    jq -r '.items[] | select(.status.active > 0) | "\(.metadata.namespace)/\(.metadata.name)"'
}

check_node_versions() {
    kubectl get nodes -o json | \
    jq -r '.items[] | "\(.metadata.name): \(.status.nodeInfo.kubeletVersion)"'
}

echo "=== Current Running Jobs ==="
JOBS=$(check_running_jobs)
if [ -z "$JOBS" ]; then
    echo "No running jobs detected"
else
    echo "$JOBS"
fi

echo -e "\n=== Node Versions ==="
check_node_versions
```

## Recommendations:

1. **For minimal risk**: Use Blue-Green cluster strategy
2. **For cost optimization**: Use node pool rotation
3. **For speed**: Use maintenance window approach with job coordination
4. **Monitor throughout**: Use the monitoring script to track progress

The **node pool rotation strategy** is often the best balance of safety, cost, and operational simplicity for your use case, as it allows jobs to complete naturally while ensuring new workloads use updated nodes.
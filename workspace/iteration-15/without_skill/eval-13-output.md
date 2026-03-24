Here are several strategies to upgrade your GKE cluster without interrupting your long-running batch jobs:

## Option 1: Blue-Green Deployment (Recommended)

Create a parallel cluster and migrate workloads:

```bash
# Create new cluster with v1.31
gcloud container clusters create batch-cluster-v131 \
    --zone=us-central1-a \
    --cluster-version=1.31 \
    --release-channel=regular \
    --machine-type=n1-standard-4 \
    --num-nodes=3

# Configure kubectl context
kubectl config get-contexts
kubectl config use-context gke_PROJECT_ID_ZONE_batch-cluster-v131
```

Migration approach:
1. Deploy new jobs to the v1.31 cluster
2. Let existing jobs complete on v1.30 cluster
3. Decommission old cluster once all jobs finish

## Option 2: Node Pool Rolling Strategy

Add a new node pool with v1.31 and drain old nodes gracefully:

```bash
# Add new node pool with v1.31
gcloud container node-pools create pool-v131 \
    --cluster=your-cluster-name \
    --zone=us-central1-a \
    --node-version=1.31.x \
    --machine-type=n1-standard-4 \
    --num-nodes=3

# Cordon old nodes to prevent new scheduling
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool
kubectl cordon NODE_NAME

# Wait for jobs to complete, then drain
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --force --grace-period=300
```

## Option 3: Job-Aware Upgrade Strategy

Use node selectors and taints to control job placement:

```yaml
# Taint new nodes for v1.31 jobs only
apiVersion: v1
kind: Node
metadata:
  name: new-node
spec:
  taints:
  - key: "version"
    value: "v1.31"
    effect: "NoSchedule"

---
# Update job templates for new version
apiVersion: batch/v1
kind: Job
metadata:
  name: batch-job-v131
spec:
  template:
    spec:
      tolerations:
      - key: "version"
        operator: "Equal"
        value: "v1.31"
        effect: "NoSchedule"
      nodeSelector:
        kubernetes.io/version: "v1.31"
```

## Option 4: Maintenance Window Strategy

If you have predictable job schedules:

```bash
# Check running jobs
kubectl get jobs --all-namespaces
kubectl get pods --field-selector=status.phase=Running

# Schedule upgrade during low-activity period
gcloud container clusters upgrade your-cluster-name \
    --master \
    --cluster-version=1.31 \
    --zone=us-central1-a

# Then upgrade node pools
gcloud container node-pools upgrade default-pool \
    --cluster=your-cluster-name \
    --zone=us-central1-a
```

## Monitoring and Safety Measures

Set up monitoring to track job completion:

```bash
# Monitor job status
kubectl get jobs -w --all-namespaces

# Check node readiness
kubectl get nodes -o wide

# Monitor cluster events
kubectl get events --sort-by=.metadata.creationTimestamp
```

Create a job completion checker:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: job-monitor
spec:
  schedule: "*/5 * * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: monitor
            image: kubectl:latest
            command:
            - /bin/sh
            - -c
            - |
              RUNNING_JOBS=$(kubectl get jobs --all-namespaces -o json | jq '.items[] | select(.status.active > 0) | .metadata.name' | wc -l)
              if [ $RUNNING_JOBS -eq 0 ]; then
                echo "No running jobs - safe to proceed with upgrade"
              else
                echo "$RUNNING_JOBS jobs still running"
              fi
          restartPolicy: OnFailure
```

## Recommended Approach

For your scenario, I recommend **Option 1 (Blue-Green)** because:

1. **Zero downtime**: Existing jobs continue uninterrupted
2. **Easy rollback**: Keep old cluster until confident in new version
3. **Testing opportunity**: Validate v1.31 with test jobs first
4. **Clean separation**: No complex migration logic needed

The process would be:
1. Create new v1.31 cluster
2. Submit new batch jobs to new cluster
3. Monitor old cluster until all v1.30 jobs complete
4. Decomission old cluster
5. Total timeline: ~16 hours + buffer time

This approach gives you the safest upgrade path while maintaining your SLA for job completion.
Here are several strategies to handle this upgrade without killing your long-running batch jobs:

## Option 1: Cluster Blue-Green Upgrade (Recommended)

Create a new cluster and gradually migrate workloads:

```bash
# Create new cluster with v1.31
gcloud container clusters create batch-cluster-v131 \
    --zone=us-central1-a \
    --cluster-version=1.31 \
    --release-channel=regular \
    --num-nodes=3

# Migrate future jobs to new cluster
kubectl config use-context gke_PROJECT_ID_ZONE_batch-cluster-v131

# Once old jobs complete, delete old cluster
gcloud container clusters delete batch-cluster-v130
```

## Option 2: Node Pool Rolling Replacement

Add new node pool with v1.31 and drain old nodes gracefully:

```bash
# Add new node pool with v1.31
gcloud container node-pools create pool-v131 \
    --cluster=your-cluster \
    --zone=us-central1-a \
    --node-version=1.31 \
    --num-nodes=3

# Cordon old nodes to prevent new scheduling
kubectl cordon NODE_NAME

# Wait for running jobs to complete, then drain
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --force --grace-period=300

# Delete old node pool
gcloud container node-pools delete old-pool --cluster=your-cluster
```

## Option 3: Maintenance Window Strategy

Configure your batch jobs with proper handling:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: long-running-batch
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 3600  # 1 hour to cleanup
      containers:
      - name: batch-job
        image: your-image
        lifecycle:
          preStop:
            exec:
              command: ["/bin/sh", "-c", "cleanup_script.sh"]
      restartPolicy: Never
  backoffLimit: 3
```

## Option 4: Job Checkpointing

Implement checkpointing for resumable jobs:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: checkpointed-job
spec:
  template:
    spec:
      containers:
      - name: worker
        volumeMounts:
        - name: checkpoint-storage
          mountPath: /checkpoints
        env:
        - name: CHECKPOINT_INTERVAL
          value: "300"  # Save every 5 minutes
      volumes:
      - name: checkpoint-storage
        persistentVolumeClaim:
          claimName: checkpoint-pvc
```

## Pre-upgrade Preparation

1. **Audit running jobs:**
```bash
kubectl get jobs --all-namespaces
kubectl get pods --field-selector=status.phase=Running
```

2. **Set up monitoring:**
```bash
# Monitor job completion
kubectl get jobs -w

# Check node conditions
kubectl get nodes -o wide
```

3. **Implement PodDisruptionBudgets:**
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: batch-job-pdb
spec:
  minAvailable: 1
  selector:
    matchLabels:
      job-type: batch
```

## Recommended Approach

For your specific case, I'd recommend **Option 1 (Blue-Green)** because:
- Zero disruption to running jobs
- Easy rollback if issues arise
- Clean separation between old and new workloads
- No complex timing coordination needed

The process would be:
1. Create new v1.31 cluster
2. Stop scheduling new jobs on old cluster
3. Schedule all new jobs on new cluster
4. Monitor old cluster until all jobs complete
5. Decommission old cluster

This gives you complete control and eliminates the risk of killing long-running jobs during the upgrade process.
Here are several strategies to handle GKE upgrades without disrupting your long-running batch jobs:

## 1. **Node Pool Rolling Strategy (Recommended)**

Create a new node pool with the target version and migrate workloads:

```yaml
# Create new node pool with 1.31
gcloud container node-pools create batch-pool-v131 \
  --cluster=your-cluster \
  --machine-type=your-machine-type \
  --num-nodes=3 \
  --node-version=1.31.x \
  --zone=your-zone
```

Then use node affinity to schedule new jobs on the new pool:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: batch-job-new
spec:
  template:
    spec:
      nodeSelector:
        cloud.google.com/gke-nodepool: batch-pool-v131
      # your job spec
```

## 2. **Maintenance Window with PodDisruptionBudgets**

Set up PDBs to protect running jobs:

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: batch-jobs-pdb
spec:
  minAvailable: 100%  # Prevent any disruption
  selector:
    matchLabels:
      app: batch-processor
```

## 3. **Job Completion Awareness Strategy**

Use a script to monitor and coordinate upgrades:

```bash
#!/bin/bash
# Check for running batch jobs
running_jobs=$(kubectl get jobs --field-selector status.active=1 --no-headers | wc -l)

if [ $running_jobs -eq 0 ]; then
  echo "No running jobs, safe to upgrade"
  # Trigger upgrade
  gcloud container clusters upgrade your-cluster --node-pool-only
else
  echo "Jobs still running: $running_jobs"
  # Schedule retry
fi
```

## 4. **Separate Cluster Strategy**

For critical workloads, consider:

```yaml
# Deploy to a separate cluster for batch jobs
gcloud container clusters create batch-cluster \
  --cluster-version=1.31.x \
  --enable-autoscaling \
  --min-nodes=0 \
  --max-nodes=10
```

## 5. **Checkpoint and Resume Pattern**

Modify your batch jobs to support checkpointing:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: resumable-batch-job
spec:
  template:
    spec:
      containers:
      - name: processor
        image: your-app:latest
        env:
        - name: CHECKPOINT_INTERVAL
          value: "3600"  # Checkpoint every hour
        volumeMounts:
        - name: checkpoint-storage
          mountPath: /checkpoints
      volumes:
      - name: checkpoint-storage
        persistentVolumeClaim:
          claimName: checkpoint-pvc
```

## 6. **Upgrade Timing Strategy**

```bash
# Schedule maintenance during low-activity periods
# Use node taints to prevent new job scheduling
kubectl taint nodes batch-node-pool upgrade=in-progress:NoSchedule

# Wait for jobs to complete naturally
while [[ $(kubectl get jobs --field-selector status.active=1 --no-headers | wc -l) -gt 0 ]]; do
  echo "Waiting for jobs to complete..."
  sleep 300
done

# Proceed with upgrade
gcloud container clusters upgrade your-cluster
```

## **Recommended Approach:**

1. **Immediate**: Use the node pool strategy for the most control
2. **Plan new jobs** to use checkpointing for future upgrades
3. **Set up monitoring** to track job completion status
4. **Consider migrating** to GKE Autopilot for automatic, less disruptive upgrades

## **Monitoring Setup:**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: upgrade-monitor
data:
  monitor.sh: |
    #!/bin/bash
    while true; do
      RUNNING_JOBS=$(kubectl get jobs --all-namespaces -o jsonpath='{.items[?(@.status.active>0)].metadata.name}')
      echo "$(date): Running jobs: ${RUNNING_JOBS:-none}"
      sleep 300
    done
```

The node pool strategy gives you the most control and allows you to upgrade incrementally while ensuring zero disruption to running jobs.
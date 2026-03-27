Here are several strategies to handle this GKE upgrade without interrupting your long-running batch jobs:

## 1. **Node Pool Rolling Strategy** (Recommended)

Create a new node pool with v1.31, migrate jobs gradually, then remove the old pool:

```bash
# Create new node pool with v1.31
gcloud container node-pools create batch-jobs-v131 \
    --cluster=your-cluster \
    --zone=your-zone \
    --node-version=1.31.x-gke.xxx \
    --num-nodes=3 \
    --machine-type=your-machine-type \
    --disk-size=your-disk-size

# Cordon old nodes to prevent new jobs from scheduling
kubectl cordon -l cloud.google.com/gke-nodepool=old-pool-name

# Wait for existing jobs to complete, then delete old pool
gcloud container node-pools delete old-pool-name --cluster=your-cluster
```

## 2. **Maintenance Window Strategy**

Configure a maintenance window during your batch job downtime:

```bash
# Set maintenance window (example: 2-hour window daily)
gcloud container clusters update your-cluster \
    --maintenance-window-start="2024-01-15T02:00:00Z" \
    --maintenance-window-end="2024-01-15T04:00:00Z" \
    --maintenance-window-recurrence="FREQ=DAILY"
```

## 3. **Job-Aware Upgrade Process**

Use Kubernetes Job completion tracking:

```yaml
# Add this to your job monitoring
apiVersion: batch/v1
kind: Job
metadata:
  name: batch-job
  labels:
    upgrade-safe: "false"  # Mark jobs that shouldn't be interrupted
spec:
  template:
    metadata:
      labels:
        upgrade-safe: "false"
    spec:
      containers:
      - name: job
        image: your-image
        # Your job configuration
```

Monitor and wait for completion:

```bash
# Check for running jobs before upgrade
kubectl get jobs -l upgrade-safe=false --field-selector status.successful!=1

# Or check for running pods
kubectl get pods -l upgrade-safe=false --field-selector status.phase=Running
```

## 4. **Automated Solution with Script**

```bash
#!/bin/bash
# upgrade-with-job-protection.sh

CLUSTER_NAME="your-cluster"
ZONE="your-zone"
NEW_VERSION="1.31.x-gke.xxx"

# Function to check for running batch jobs
check_running_jobs() {
    kubectl get jobs --all-namespaces -o json | jq -r '.items[] | select(.status.active > 0) | .metadata.name' | wc -l
}

# Wait for jobs to complete
echo "Checking for running batch jobs..."
while [ $(check_running_jobs) -gt 0 ]; do
    echo "$(check_running_jobs) jobs still running. Waiting 30 minutes..."
    sleep 1800  # Wait 30 minutes
done

echo "No running jobs detected. Starting upgrade..."

# Upgrade control plane first
gcloud container clusters upgrade $CLUSTER_NAME \
    --master \
    --cluster-version=$NEW_VERSION \
    --zone=$ZONE

# Upgrade nodes
gcloud container clusters upgrade $CLUSTER_NAME \
    --node-pool=default-pool \
    --cluster-version=$NEW_VERSION \
    --zone=$ZONE
```

## 5. **Blue-Green Cluster Strategy** (For Critical Workloads)

For maximum safety, create a parallel cluster:

```bash
# Create new cluster with v1.31
gcloud container clusters create batch-cluster-v131 \
    --cluster-version=1.31.x-gke.xxx \
    --zone=your-zone \
    --num-nodes=3

# Migrate new jobs to new cluster gradually
# Keep old cluster running until all jobs complete
```

## 6. **PodDisruptionBudget Protection**

Protect critical jobs with PDBs:

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: batch-job-pdb
spec:
  minAvailable: 100%  # Don't allow any disruptions
  selector:
    matchLabels:
      job-type: long-running-batch
```

## **Recommended Approach:**

1. **Schedule during low-activity period**
2. **Use node pool rolling strategy** for gradual migration
3. **Monitor job completion** before proceeding
4. **Set up proper PodDisruptionBudgets**
5. **Test the process** on a staging cluster first

## **Pre-upgrade Checklist:**

```bash
# 1. Check current job status
kubectl get jobs --all-namespaces

# 2. Identify long-running jobs
kubectl get pods --all-namespaces --field-selector=status.phase=Running

# 3. Verify PodDisruptionBudgets
kubectl get pdb --all-namespaces

# 4. Check node pool status
gcloud container node-pools list --cluster=your-cluster
```

The **node pool rolling strategy** is typically the safest approach as it provides the most control over the upgrade process while minimizing disruption to your batch jobs.
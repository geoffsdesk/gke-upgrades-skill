Here are several strategies to handle your GKE upgrade while protecting long-running batch jobs:

## Option 1: Blue-Green Deployment (Recommended)

Create a parallel node pool with the new version:

```bash
# Create new node pool with v1.31
gcloud container node-pools create "v1-31-pool" \
    --cluster=your-cluster \
    --machine-type=your-machine-type \
    --num-nodes=3 \
    --node-version=1.31.x \
    --zone=your-zone

# Verify new nodes are ready
kubectl get nodes -l cloud.google.com/gke-nodepool=v1-31-pool
```

Configure job scheduling to use new nodes:

```yaml
# For new jobs, add node selector
apiVersion: batch/v1
kind: Job
metadata:
  name: batch-job-new
spec:
  template:
    spec:
      nodeSelector:
        cloud.google.com/gke-nodepool: v1-31-pool
      containers:
      - name: job-container
        image: your-image
```

## Option 2: Controlled Node Pool Upgrade

Upgrade node pools individually with careful timing:

```bash
# Cordon nodes to prevent new jobs
kubectl cordon <node-name>

# Wait for existing jobs to complete (monitor with)
kubectl get jobs --watch

# When node is clear of batch jobs, upgrade
gcloud container node-pools upgrade old-pool \
    --cluster=your-cluster \
    --node-version=1.31.x \
    --zone=your-zone
```

## Option 3: Job-Aware Upgrade Strategy

Use taints and tolerations to control job placement:

```bash
# Taint nodes you want to upgrade
kubectl taint nodes <node-name> upgrade-pending=true:NoSchedule

# Update your job templates to avoid tainted nodes
kubectl patch cronjob your-batch-job -p='
{
  "spec": {
    "jobTemplate": {
      "spec": {
        "template": {
          "spec": {
            "tolerations": [{
              "key": "upgrade-pending",
              "operator": "DoesNotExist"
            }]
          }
        }
      }
    }
  }
}'
```

## Option 4: Maintenance Window Approach

If you can coordinate a maintenance window:

```bash
# Pause CronJobs temporarily
kubectl patch cronjob your-batch-job -p '{"spec":{"suspend":true}}'

# Wait for running jobs to complete
kubectl wait --for=condition=complete job/your-running-job --timeout=18h

# Perform upgrade
gcloud container clusters upgrade your-cluster \
    --cluster-version=1.31.x \
    --zone=your-zone

# Resume CronJobs
kubectl patch cronjob your-batch-job -p '{"spec":{"suspend":false}}'
```

## Additional Considerations

**Pod Disruption Budgets** for job controllers:
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: batch-job-pdb
spec:
  minAvailable: 1
  selector:
    matchLabels:
      job-type: batch-processing
```

**Monitor job status** during upgrades:
```bash
# Check job completion status
kubectl get jobs -o wide

# Monitor node readiness
kubectl get nodes -o wide

# Watch for any evicted pods
kubectl get events --field-selector reason=Evicted
```

## Recommended Approach

I recommend **Option 1 (Blue-Green)** because it:
- Provides zero downtime for running jobs
- Allows easy rollback if issues arise
- Gives you time to validate the new version
- Minimizes risk to your long-running processes

After validating jobs run successfully on v1.31 nodes, gradually migrate workloads and decommission the old node pool.

Would you like me to elaborate on any of these approaches or help you plan the specific steps for your environment?
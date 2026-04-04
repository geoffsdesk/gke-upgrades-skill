Here are several strategies to handle your GKE upgrade without disrupting long-running batch jobs:

## Option 1: Blue-Green Node Pool Strategy (Recommended)

```yaml
# Create new node pool with 1.31
apiVersion: v1
kind: NodePool
metadata:
  name: batch-jobs-v131
spec:
  version: "1.31"
  nodeConfig:
    labels:
      node-version: "v131"
      workload-type: "batch"
  # Match your current pool configuration
```

Then migrate jobs gradually:
```yaml
# Update your job templates
apiVersion: batch/v1
kind: Job
metadata:
  name: batch-job
spec:
  template:
    spec:
      nodeSelector:
        node-version: "v131"  # Target new nodes
      # ... rest of job spec
```

## Option 2: Maintenance Window with Job Scheduling

```bash
# 1. Pause job scheduling
kubectl patch cronjob my-batch-jobs -p '{"spec":{"suspend":true}}'

# 2. Wait for running jobs to complete
kubectl get jobs --field-selector status.successful!=1,status.failed!=1

# 3. Upgrade during the gap
gcloud container clusters upgrade my-cluster \
  --cluster-version=1.31 \
  --zone=us-central1-a

# 4. Resume scheduling
kubectl patch cronjob my-batch-jobs -p '{"spec":{"suspend":false}}'
```

## Option 3: Cluster Migration Strategy

```bash
# 1. Create new cluster with 1.31
gcloud container clusters create batch-cluster-v131 \
  --cluster-version=1.31 \
  --release-channel=regular \
  --zone=us-central1-a

# 2. Gradually migrate workloads
# Use tools like Velero for backup/restore or manual migration
```

## Option 4: Staged Node Pool Upgrade with Taints

```bash
# 1. Create new node pool
gcloud container node-pools create upgraded-pool \
  --cluster=my-cluster \
  --node-version=1.31 \
  --zone=us-central1-a \
  --node-taints=upgrade=true:NoSchedule

# 2. Update job tolerations
kubectl patch job my-job -p '{
  "spec": {
    "template": {
      "spec": {
        "tolerations": [{
          "key": "upgrade",
          "operator": "Equal",
          "value": "true",
          "effect": "NoSchedule"
        }]
      }
    }
  }
}'

# 3. Remove taint and drain old nodes when ready
```

## Job Completion Monitoring Script

```bash
#!/bin/bash
# monitor-jobs.sh - Wait for jobs to complete

wait_for_jobs() {
  while true; do
    RUNNING_JOBS=$(kubectl get jobs -o jsonpath='{.items[?(@.status.active>0)].metadata.name}')
    
    if [ -z "$RUNNING_JOBS" ]; then
      echo "All batch jobs completed"
      break
    fi
    
    echo "Still running: $RUNNING_JOBS"
    sleep 300  # Check every 5 minutes
  done
}

wait_for_jobs
```

## Recommendations:

1. **Use Blue-Green approach** - Safest for critical workloads
2. **Test on dev cluster first** - Validate job compatibility with 1.31
3. **Plan for 24-48 hour window** - Allow buffer for longest jobs
4. **Monitor resource usage** - Ensure new nodes have adequate capacity
5. **Have rollback plan** - Keep old node pool until fully validated

## Additional Considerations:

```yaml
# Add PodDisruptionBudget to protect running jobs
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: batch-job-pdb
spec:
  minAvailable: "100%"  # Prevent any disruption
  selector:
    matchLabels:
      job-type: batch
```

Would you like me to elaborate on any of these approaches or help you plan the specific migration strategy for your environment?
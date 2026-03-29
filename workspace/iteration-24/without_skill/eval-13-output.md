You have several strategies to handle this GKE upgrade without interrupting your long-running batch jobs. Here are the best approaches:

## Strategy 1: Blue-Green Node Pool Deployment (Recommended)

This is the safest approach for your use case:

```bash
# 1. Create a new node pool with v1.31
gcloud container node-pools create "batch-pool-v131" \
    --cluster=your-cluster-name \
    --zone=your-zone \
    --machine-type=your-machine-type \
    --num-nodes=3 \
    --node-version=1.31.x-gke.y \
    --node-labels=pool=batch-v131

# 2. Update your job manifests to prefer the new pool
kubectl patch deployment your-batch-jobs -p '{
  "spec": {
    "template": {
      "spec": {
        "nodeSelector": {
          "pool": "batch-v131"
        }
      }
    }
  }
}'

# 3. Wait for current jobs to complete, then delete old pool
gcloud container node-pools delete old-pool-name \
    --cluster=your-cluster-name \
    --zone=your-zone
```

## Strategy 2: Pause Auto-Upgrade + Manual Control

```bash
# 1. Disable auto-upgrade temporarily
gcloud container clusters update your-cluster-name \
    --no-enable-autoupgrade \
    --zone=your-zone

# 2. Create a maintenance window
gcloud container clusters update your-cluster-name \
    --maintenance-window-start="2024-01-15T02:00:00Z" \
    --maintenance-window-end="2024-01-15T06:00:00Z" \
    --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SU" \
    --zone=your-zone
```

## Strategy 3: Job-Aware Upgrade with Taints

```yaml
# Add this to your batch job specs
apiVersion: batch/v1
kind: Job
metadata:
  name: long-running-batch
spec:
  template:
    spec:
      tolerations:
      - key: "node.kubernetes.io/unschedulable"
        operator: "Exists"
        effect: "NoSchedule"
      - key: "CriticalAddonsOnly"
        operator: "Exists"
      nodeSelector:
        workload-type: "batch"
      containers:
      - name: batch-job
        image: your-image
        resources:
          requests:
            memory: "4Gi"
            cpu: "2"
```

## Strategy 4: Cluster-Level Upgrade Scheduling

```bash
# 1. Check current job status
kubectl get jobs --all-namespaces -o wide

# 2. Set up a pre-upgrade hook script
cat << 'EOF' > check-jobs.sh
#!/bin/bash
RUNNING_JOBS=$(kubectl get jobs --all-namespaces --field-selector status.successful!=1 -o name | wc -l)
if [ $RUNNING_JOBS -gt 0 ]; then
    echo "Jobs still running, postponing upgrade"
    exit 1
fi
echo "Safe to upgrade"
exit 0
EOF

# 3. Schedule upgrade only when safe
while ! ./check-jobs.sh; do
    echo "Waiting for jobs to complete..."
    sleep 3600  # Check every hour
done

# Proceed with upgrade
gcloud container clusters upgrade your-cluster-name \
    --master --zone=your-zone
```

## Best Practices for Your Situation:

### 1. Job Configuration
```yaml
apiVersion: batch/v1
kind: Job
spec:
  # Prevent job restart on node drain
  backoffLimit: 0
  template:
    spec:
      restartPolicy: Never
      # Add priority class for important jobs
      priorityClassName: high-priority-batch
      # Use pod disruption budgets
      terminationGracePeriodSeconds: 300
```

### 2. Priority Class Setup
```yaml
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: high-priority-batch
value: 1000
globalDefault: false
description: "High priority for long-running batch jobs"
```

### 3. Monitoring Script
```bash
#!/bin/bash
# monitor-upgrade-readiness.sh
kubectl get jobs --all-namespaces \
    -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.conditions[*].type}{"\n"}{end}' | \
    grep -v Complete | \
    wc -l
```

## Recommended Approach:

For your 8-16 hour batch jobs, I recommend **Strategy 1 (Blue-Green Node Pool)** because:

1. **Zero downtime** for running jobs
2. **Easy rollback** if issues arise
3. **Gradual migration** of workloads
4. **Cost control** - you can size pools appropriately

The process would be:
1. Create new v1.31 node pool
2. Let current jobs finish on old nodes
3. Schedule new jobs on new nodes
4. Remove old pool once empty

This gives you complete control over the timing and ensures no job interruption.
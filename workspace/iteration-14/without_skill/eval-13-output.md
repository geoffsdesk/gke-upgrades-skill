Here are several strategies to handle your GKE upgrade without disrupting long-running batch jobs:

## Option 1: Workload-Aware Upgrade (Recommended)

Use GKE's built-in job completion awareness:

```yaml
# Configure cluster upgrade settings
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerNodePool
metadata:
  name: batch-nodepool
spec:
  upgradeSettings:
    strategy: SURGE
    maxSurge: 1
    maxUnavailable: 0
  management:
    autoUpgrade: false  # Control timing manually
```

## Option 2: Blue-Green Node Pool Strategy

Create a new node pool with 1.31, then migrate workloads:

```bash
# 1. Create new node pool with 1.31
gcloud container node-pools create "batch-pool-v131" \
    --cluster=your-cluster \
    --zone=your-zone \
    --node-version=1.31.x \
    --num-nodes=3 \
    --machine-type=your-machine-type

# 2. Cordon old nodes (prevent new scheduling)
kubectl cordon -l node-pool=old-batch-pool

# 3. Wait for existing jobs to complete naturally
# 4. Drain old nodes once jobs finish
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data

# 5. Delete old node pool
gcloud container node-pools delete old-batch-pool
```

## Option 3: Job-Aware Scheduling

Configure jobs to be upgrade-resilient:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: batch-job
spec:
  backoffLimit: 2
  template:
    spec:
      restartPolicy: OnFailure
      # Prefer nodes that aren't scheduled for upgrade
      affinity:
        nodeAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            preference:
              matchExpressions:
              - key: "cloud.google.com/gke-nodepool"
                operator: In
                values: ["stable-pool"]
      # Add tolerations for upgrade taints
      tolerations:
      - key: "node.kubernetes.io/unschedulable"
        operator: "Exists"
        effect: "NoSchedule"
```

## Option 4: Maintenance Window Strategy

```bash
# 1. Disable auto-upgrade temporarily
gcloud container clusters update your-cluster \
    --no-enable-autoupgrade

# 2. Monitor job completion
kubectl get jobs -w

# 3. Schedule upgrade during low-activity period
gcloud container clusters upgrade your-cluster \
    --master \
    --cluster-version=1.31.x

# 4. Upgrade node pools with controlled timing
gcloud container node-pools upgrade batch-nodepool \
    --cluster=your-cluster \
    --node-version=1.31.x
```

## Monitoring and Safety Measures

```bash
# Monitor running jobs
kubectl get jobs -o wide
kubectl get pods --field-selector=status.phase=Running

# Check node upgrade status
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,READY:.status.conditions[?(@.type==\"Ready\")].status

# Set up alerts for job failures
kubectl get events --field-selector type=Warning
```

## Best Practices for Future Upgrades

1. **Use Pod Disruption Budgets:**
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

2. **Implement checkpointing in your batch jobs** to enable graceful restarts

3. **Consider using multiple smaller node pools** for different workload types

4. **Set up proper monitoring** for job completion before initiating upgrades

## Recommended Approach

For your situation, I'd recommend **Option 2 (Blue-Green Node Pool)** because it:
- Provides complete isolation between old and new versions
- Allows natural completion of existing jobs
- Gives you full control over the migration timing
- Provides easy rollback if issues occur

The key is to cordon old nodes immediately after creating new ones, then patiently wait for jobs to complete before draining.
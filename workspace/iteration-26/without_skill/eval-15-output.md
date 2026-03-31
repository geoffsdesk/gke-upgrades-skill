Here's how to handle this situation step by step:

## Immediate Assessment

First, check the current state:
```bash
# Check node versions
kubectl get nodes -o wide

# Check failed upgrade status
gcloud container operations list --filter="operationType=UPGRADE_NODES"

# Get detailed error information
gcloud container operations describe [OPERATION_ID] --zone=[ZONE]
```

## Recovery Options

### Option 1: Resume the Failed Upgrade (Recommended)
```bash
# Check if the upgrade can be resumed
gcloud container node-pools describe [POOL_NAME] \
    --cluster=[CLUSTER_NAME] \
    --zone=[ZONE]

# If resumable, continue the upgrade
gcloud container node-pools upgrade [POOL_NAME] \
    --cluster=[CLUSTER_NAME] \
    --zone=[ZONE] \
    --node-version=1.32
```

### Option 2: Manual Node Replacement
If resume isn't possible:
```bash
# Drain problematic old nodes one by one
kubectl drain [NODE_NAME] --ignore-daemonsets --delete-emptydir-data

# Delete the old node
gcloud compute instances delete [NODE_NAME] --zone=[ZONE]

# The node pool will automatically create a replacement with v1.32
```

## Workload Safety Measures

While resolving:
```bash
# Ensure workloads are distributed properly
kubectl get pods -o wide --all-namespaces | grep -E "(1\.31|1\.30)"

# Check for any disrupted services
kubectl get endpoints
kubectl get ingress
```

## Prevention for Other Pools

Before upgrading remaining pools:
```bash
# Upgrade smaller pools first as a test
gcloud container node-pools upgrade [SMALLER_POOL] \
    --cluster=[CLUSTER_NAME] \
    --zone=[ZONE] \
    --node-version=1.32 \
    --max-surge-upgrade=1 \
    --max-unavailable-upgrade=0
```

## Monitor Throughout
```bash
# Watch the upgrade progress
watch "kubectl get nodes -o wide"

# Monitor workload health
kubectl top nodes
kubectl get events --sort-by='.lastTimestamp'
```

**Key Points:**
- Your mixed-version state (8 new, 12 old nodes) is temporarily stable
- Don't upgrade other pools until main pool is resolved
- Consider using smaller surge settings for remaining upgrades
- Check the specific error message to determine if it's transient or requires intervention

What error message did you see in the operation details? That will help determine the best recovery approach.
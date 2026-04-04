This is a manageable situation. Here's your recovery plan:

## Immediate Assessment
First, check the current state:
```bash
# Check node versions and status
kubectl get nodes -o wide

# Check the failed upgrade status
kubectl describe nodes | grep -E "Version|Conditions" -A 5

# Check workload health
kubectl get pods --all-namespaces -o wide | grep -v Running
```

## Recovery Options

### Option 1: Resume the Failed Upgrade (Recommended)
```bash
# Get the specific error details
gcloud container operations list --filter="status=FAILED"

# Attempt to resume/retry the upgrade
gcloud container node-pools upgrade [POOL_NAME] \
    --cluster=[CLUSTER_NAME] \
    --zone=[ZONE] \
    --node-version=1.32

# Or use specific upgrade strategy
gcloud container node-pools upgrade [POOL_NAME] \
    --cluster=[CLUSTER_NAME] \
    --max-surge-upgrade=1 \
    --max-unavailable-upgrade=0
```

### Option 2: Manual Node Replacement
If the automatic retry fails:
```bash
# Cordon and drain the problematic old nodes
kubectl cordon [OLD_NODE_NAME]
kubectl drain [OLD_NODE_NAME] --ignore-daemonsets --delete-emptydir-data

# Create new nodes in the pool (GKE will create v1.32 nodes)
gcloud container clusters resize [CLUSTER_NAME] \
    --node-pool=[POOL_NAME] \
    --num-nodes=[DESIRED_SIZE] \
    --zone=[ZONE]
```

## Risk Mitigation

### Check Version Compatibility
```bash
# Ensure your workloads can handle mixed versions temporarily
kubectl api-versions | sort

# Check for deprecated APIs
kubectl get events --sort-by='.lastTimestamp' | grep -i deprecat
```

### Monitor Workload Health
```bash
# Watch for scheduling issues
kubectl get pods -o wide | grep Pending

# Check node capacity
kubectl describe nodes | grep -E "Capacity|Allocatable" -A 5
```

## Other Node Pools
**Hold off** on upgrading the other two pools until the main pool is fully resolved. This gives you:
- Stable capacity for workload scheduling
- Rollback options if needed
- Reduced blast radius

## Next Steps Priority:
1. **Fix the main pool first** - it's your critical workload
2. **Verify workload stability** for 24-48 hours
3. **Then upgrade remaining pools** one at a time

What specific error are you seeing in the failed upgrade? That will help determine the best recovery approach.
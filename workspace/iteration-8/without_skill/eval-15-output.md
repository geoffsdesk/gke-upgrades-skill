Here's how to handle your partial node pool upgrade failure:

## Immediate Assessment

**First, check your workload status:**
```bash
# Check pod distribution and health
kubectl get pods -o wide --all-namespaces | grep -E "(Pending|Failed|Unknown)"

# Verify nodes status
kubectl get nodes -o wide
kubectl describe nodes | grep -E "(Ready|Taint|Condition)"
```

## Recovery Options

### Option 1: Resume the Failed Upgrade (Recommended)
```bash
# Check the upgrade status
gcloud container operations list --filter="TYPE:UPGRADE_NODES"

# Get detailed error information
gcloud container operations describe [OPERATION-ID] --zone=[ZONE]

# Attempt to resume/retry the upgrade
gcloud container clusters upgrade [CLUSTER-NAME] \
    --node-pool=[WORKLOAD-POOL-NAME] \
    --cluster-version=1.32 \
    --zone=[ZONE]
```

### Option 2: Manual Node Replacement
If the resume fails, replace problematic nodes:
```bash
# Cordon and drain stuck nodes
kubectl cordon [NODE-NAME]
kubectl drain [NODE-NAME] --ignore-daemonsets --delete-emptydir-data --force

# Delete the problematic node
gcloud container clusters delete-node [NODE-NAME] \
    --zone=[ZONE] \
    --cluster=[CLUSTER-NAME]
```

## Before Proceeding Further

1. **Verify workload tolerance:**
   - Ensure your applications can handle more node disruptions
   - Check PodDisruptionBudgets are properly configured
   - Confirm you have adequate capacity on upgraded nodes

2. **Staging strategy for remaining pools:**
   ```bash
   # Upgrade remaining pools one at a time
   gcloud container clusters upgrade [CLUSTER-NAME] \
       --node-pool=[POOL-2-NAME] \
       --cluster-version=1.32 \
       --max-surge-upgrade=1 \
       --max-unavailable-upgrade=0
   ```

## Prevention for Future Upgrades

```bash
# Use surge upgrades for better resilience
gcloud container node-pools update [POOL-NAME] \
    --cluster=[CLUSTER-NAME] \
    --max-surge-upgrade=3 \
    --max-unavailable-upgrade=1
```

What specific error message did you see when the upgrade failed? This will help determine the best recovery approach.
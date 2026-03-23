This is a recoverable situation. Here's how to handle the partial node pool upgrade:

## Immediate Assessment

First, check the current state:
```bash
# Check node versions and status
kubectl get nodes -o wide

# Check the upgrade status and error details
gcloud container operations list --filter="operationType=UPGRADE_NODES"
gcloud container operations describe [OPERATION_ID] --region=[REGION]
```

## Recovery Options

### Option 1: Resume the Failed Upgrade (Recommended)
```bash
# Retry the upgrade operation for the partially upgraded pool
gcloud container node-pools upgrade [NODE_POOL_NAME] \
    --cluster=[CLUSTER_NAME] \
    --region=[REGION] \
    --node-version=1.32.x
```

### Option 2: Manual Node Replacement
If the retry fails, replace the remaining old nodes manually:
```bash
# Cordon and drain old nodes one by one
kubectl cordon [OLD_NODE_NAME]
kubectl drain [OLD_NODE_NAME] --ignore-daemonsets --delete-emptydir-data --force

# Then trigger replacement via resize or specific node deletion
```

## Before Proceeding

1. **Verify workload health** on the 8 upgraded nodes
2. **Check pod disruption budgets** are properly configured
3. **Ensure adequate capacity** exists for workload scheduling

## Prevention for Remaining Pools

For your other two node pools:
```bash
# Upgrade with safer settings
gcloud container node-pools upgrade [POOL_NAME] \
    --cluster=[CLUSTER_NAME] \
    --region=[REGION] \
    --max-surge-upgrade=1 \
    --max-unavailable-upgrade=0
```

## Monitor Progress
```bash
# Watch the upgrade progress
kubectl get nodes --watch
kubectl get pods --all-namespaces | grep -v Running
```

What specific error message did you see when the upgrade failed? That will help determine the best recovery approach.
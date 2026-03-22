This is a recoverable situation. Here's how to handle the partial node pool upgrade:

## Immediate Assessment

First, check the current state:
```bash
# Check cluster and node versions
kubectl get nodes -o wide

# Check the upgrade status and error details
kubectl describe nodes | grep -E "Version|Conditions"

# Check for any failing pods
kubectl get pods --all-namespaces | grep -v Running
```

## Recovery Options

### Option 1: Resume the Failed Upgrade (Recommended)
```bash
# Get detailed error information
gcloud container operations list --filter="targetId=YOUR_CLUSTER_NAME"

# Attempt to resume the upgrade
gcloud container clusters upgrade YOUR_CLUSTER_NAME \
    --node-pool=YOUR_MAIN_WORKLOAD_POOL \
    --cluster-version=1.32 \
    --zone=YOUR_ZONE
```

### Option 2: Manual Node Replacement
If the resume fails, replace remaining nodes manually:

```bash
# Identify nodes that need upgrading
kubectl get nodes -l cloud.google.com/gke-nodepool=YOUR_MAIN_WORKLOAD_POOL

# For each old node:
# 1. Cordon and drain
kubectl cordon NODE_NAME
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --force

# 2. Delete the node (GKE will auto-replace with new version)
gcloud compute instances delete NODE_NAME --zone=YOUR_ZONE
```

### Option 3: Create New Node Pool (Safest)
```bash
# Create a new pool with 1.32
gcloud container node-pools create new-workload-pool \
    --cluster=YOUR_CLUSTER_NAME \
    --node-version=1.32 \
    --num-nodes=20 \
    --zone=YOUR_ZONE \
    [other-config-options]

# Migrate workloads gradually, then delete old pool
```

## Before Proceeding

1. **Check workload tolerance**: Ensure your apps can handle the mixed-version state temporarily
2. **Review the error**: Use `gcloud logging read` to get detailed failure reasons
3. **Verify cluster health**: Ensure the 8 upgraded nodes are healthy

## Next Steps for Other Pools

Once the main pool is resolved:
- Upgrade smaller pools first to test
- Consider upgrading during low-traffic periods
- Use `--max-surge` and `--max-unavailable` for controlled rollouts

What specific error message are you seeing, and which approach would you prefer to try first?
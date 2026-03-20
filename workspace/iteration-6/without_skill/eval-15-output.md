This is a recoverable situation, but you need to act methodically to avoid workload disruption. Here's your action plan:

## Immediate Assessment

First, check the current state:
```bash
# Check node versions and status
kubectl get nodes -o wide

# Check the failed upgrade status
gcloud container operations list --filter="operationType=UPGRADE_NODES"

# Get detailed error information
gcloud container operations describe [OPERATION_ID] --region=[REGION]
```

## Recovery Options

### Option 1: Retry the Failed Upgrade (Recommended)
```bash
# Retry the same node pool upgrade
gcloud container clusters upgrade [CLUSTER_NAME] \
    --node-pool=[FAILED_POOL_NAME] \
    --cluster-version=1.30 \
    --region=[REGION]
```

### Option 2: Manual Node Replacement (if retry fails)
If the automatic retry doesn't work:

```bash
# Cordon the old nodes first
kubectl get nodes --selector="cloud.google.com/gke-nodepool=[POOL_NAME]" \
    -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' | \
    grep -E "1\.29|1\.28" | xargs kubectl cordon

# Drain each old node individually
kubectl drain [OLD_NODE_NAME] --ignore-daemonsets --delete-emptydir-data --grace-period=300

# Delete the old nodes from the node pool
gcloud container clusters resize [CLUSTER_NAME] \
    --node-pool=[POOL_NAME] \
    --num-nodes=[CURRENT_SIZE - OLD_NODES] \
    --region=[REGION]

# Scale back up (new nodes will use 1.30)
gcloud container clusters resize [CLUSTER_NAME] \
    --node-pool=[POOL_NAME] \
    --num-nodes=[ORIGINAL_SIZE] \
    --region=[REGION]
```

## After Main Pool Recovery

Once your main workload pool is fully upgraded:

```bash
# Upgrade remaining pools one at a time
gcloud container clusters upgrade [CLUSTER_NAME] \
    --node-pool=[POOL_NAME_2] \
    --cluster-version=1.30 \
    --region=[REGION]
```

## Key Considerations

- **Workload Impact**: Your 8 upgraded nodes can handle both 1.29 and 1.30 workloads, so you're not in immediate danger
- **Pod Scheduling**: Some pods might prefer the newer nodes - monitor for any scheduling issues
- **Surge Settings**: Check if your node pool has surge upgrade settings that might help:
  ```bash
  gcloud container node-pools describe [POOL_NAME] \
      --cluster=[CLUSTER_NAME] --region=[REGION]
  ```

## Prevention for Future Upgrades

- Enable surge upgrades: `--max-surge=1 --max-unavailable=0`
- Test upgrades on non-critical pools first
- Consider blue/green node pool strategy for critical workloads

What error message are you seeing in the operation details? That will help determine the best recovery approach.
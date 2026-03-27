This is a manageable situation. Here's your recovery plan:

## Immediate Assessment
First, check the current state:
```bash
# Check node versions and status
kubectl get nodes -o wide

# Check the upgrade status and error details
gcloud container operations list --filter="TYPE:UPGRADE_NODES"
gcloud container operations describe [OPERATION-ID] --zone=[ZONE]
```

## Recovery Options

### Option 1: Resume the Failed Upgrade (Recommended)
```bash
# Try to resume/retry the node pool upgrade
gcloud container node-pools upgrade [NODE-POOL-NAME] \
    --cluster=[CLUSTER-NAME] \
    --zone=[ZONE] \
    --node-version=1.32.x
```

### Option 2: Manual Cordoning and Replacement
If the resume fails, manually manage the remaining nodes:
```bash
# Identify which nodes still need upgrading
kubectl get nodes --selector='kubernetes.io/version!=v1.32.x'

# For each old node:
kubectl cordon [NODE-NAME]
kubectl drain [NODE-NAME] --ignore-daemonsets --delete-emptydir-data
```

## Key Considerations

**Workload Impact**: Your cluster is currently running mixed versions (1.32 control plane, mixed 1.31/1.32 nodes). This is supported but not ideal long-term.

**Common Failure Causes**:
- Resource constraints during drain
- Pods with PodDisruptionBudgets blocking drain
- Insufficient surge capacity
- Zone-specific issues

## Next Steps After Recovery

1. **Complete the main pool upgrade first** before touching other pools
2. **Check surge settings**: Ensure adequate `max-surge` and `max-unavailable` values
3. **Upgrade remaining pools** one at a time:
   ```bash
   gcloud container node-pools upgrade [POOL-NAME] --cluster=[CLUSTER] --zone=[ZONE]
   ```

**Pro tip**: Consider upgrading during low-traffic periods and ensure your surge settings allow for smooth rolling updates (typically `max-surge=1, max-unavailable=0` for production).

What specific error message are you seeing in the operation details?
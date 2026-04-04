This is a recoverable situation. Here's your step-by-step recovery plan:

## Immediate Assessment
First, check the current state:
```bash
kubectl get nodes -o wide
kubectl get pods --all-namespaces -o wide | grep -v Running
```
Look for any pods stuck on the partially upgraded nodes or scheduling issues.

## Recovery Options

### Option 1: Resume the Failed Upgrade (Recommended)
```bash
# Check the upgrade status and error details
gcloud container operations list --filter="operationType=UPGRADE_NODES"

# Get the specific error
gcloud container operations describe [OPERATION-ID] --zone=[ZONE]

# Attempt to resume/retry the upgrade
gcloud container node-pools upgrade [POOL-NAME] \
    --cluster=[CLUSTER-NAME] \
    --zone=[ZONE] \
    --node-version=1.32
```

### Option 2: If Resume Fails - Manual Cordoning
If the automatic retry doesn't work:

```bash
# Cordon the remaining old nodes to prevent new pods
kubectl get nodes --no-headers | grep "v1.31" | awk '{print $1}' | \
    xargs -I {} kubectl cordon {}

# Drain nodes one by one safely
kubectl drain [NODE-NAME] --ignore-daemonsets --delete-emptydir-data --force --grace-period=300

# Then try upgrading individual nodes or recreating the pool
```

## Before Proceeding with Other Pools
1. **Wait** until the main pool is fully stable
2. **Verify** all workloads are running normally
3. **Check** that the mix of 1.31 and 1.32 nodes isn't causing issues

## Risk Mitigation
- Your control plane on 1.32 supports nodes on 1.31, so you're not in a broken state
- Monitor resource capacity - you're running on reduced capacity
- Consider scaling up healthy node pools temporarily if needed

What error message did you see when the upgrade failed? That will help determine the best recovery approach.
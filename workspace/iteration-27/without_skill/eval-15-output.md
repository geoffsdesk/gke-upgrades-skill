This is a manageable situation! Here's your recovery plan:

## Immediate Assessment
First, check the current state:
```bash
kubectl get nodes -o wide
kubectl get pods --all-namespaces -o wide
```

Identify which nodes are on v1.32 vs older versions, and verify pod distribution.

## Recovery Options

### Option 1: Resume the Failed Upgrade (Recommended)
```bash
# Check the upgrade status
gcloud container operations list --filter="name:upgrade"

# If the operation is truly stuck, cancel it first
gcloud container operations cancel [OPERATION_ID] --zone=[ZONE]

# Then retry the node pool upgrade
gcloud container node-pools upgrade [POOL_NAME] \
  --cluster=[CLUSTER_NAME] \
  --zone=[ZONE] \
  --node-version=1.32.x
```

### Option 2: Cordoned Node Approach
If the upgrade keeps failing:
```bash
# Cordon the remaining old nodes
kubectl cordon [OLD_NODE_NAME]

# Drain them one by one (this forces pod rescheduling)
kubectl drain [OLD_NODE_NAME] --ignore-daemonsets --delete-emptydir-data

# Then upgrade individual nodes or small batches
gcloud container node-pools upgrade [POOL_NAME] \
  --cluster=[CLUSTER_NAME] \
  --zone=[ZONE] \
  --max-surge-upgrade=1 \
  --max-unavailable-upgrade=0
```

## Key Considerations

**Workload Impact**: Your pods should be running fine on the mixed-version nodes since control plane is v1.32. GKE supports nodes up to 2 minor versions behind.

**Before Proceeding**:
- Check if you have PodDisruptionBudgets configured
- Verify your workloads can handle node rescheduling
- Consider upgrading during low-traffic periods

**Other Node Pools**: Keep them on the old version until the main pool is fully upgraded to avoid complications.

What error message did you see when the upgrade failed? This will help determine the best approach.
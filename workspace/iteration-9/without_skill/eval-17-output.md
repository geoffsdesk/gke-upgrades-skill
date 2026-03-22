Yes, there are several strategies to work around quota constraints during node pool upgrades. Here are your options:

## Option 1: Use Max Unavailable Strategy
Configure the upgrade to replace nodes in-place rather than using surge capacity:

```bash
# For GKE
gcloud container node-pools update POOL_NAME \
    --cluster=CLUSTER_NAME \
    --zone=ZONE \
    --max-surge=0 \
    --max-unavailable=1

# For EKS, update the node group configuration
aws eks update-nodegroup-config \
    --cluster-name CLUSTER_NAME \
    --nodegroup-name NODEGROUP_NAME \
    --update-config maxUnavailable=1,maxUnavailablePercentage=null
```

## Option 2: Manual Rolling Update
Temporarily reduce cluster capacity and upgrade in batches:

```bash
# 1. Cordon nodes to prevent new pods
kubectl cordon NODE_NAME

# 2. Drain workloads to remaining nodes
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data

# 3. Delete the old node (frees quota immediately)
kubectl delete node NODE_NAME

# 4. Let the node pool create a replacement with new version
# 5. Repeat for next node once replacement is ready
```

## Option 3: Temporary Scale Down
If your workloads can tolerate it:

```bash
# Scale down non-critical workloads temporarily
kubectl scale deployment NON_CRITICAL_APP --replicas=0

# This frees up nodes that can be upgraded
# Scale back up after upgrade completes
```

## Option 4: Cross-Zone Strategy
If quota is available in other zones:

```bash
# Create new node pool in different zone with new version
# Migrate workloads gradually
# Delete old node pool when complete
```

## Safest Approach:
I'd recommend **Option 1** (max-unavailable strategy) as it:
- Doesn't require additional quota
- Maintains some cluster capacity during upgrade
- Is officially supported by the platform

Would you like me to help you implement any of these approaches for your specific platform?
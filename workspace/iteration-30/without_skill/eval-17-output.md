Yes, you have several options to work around the quota constraint while waiting for the increase:

## Option 1: Reduce Surge Settings (Quickest)
Temporarily lower the surge configuration to create fewer nodes at once:

```bash
# For GKE
gcloud container node-pools update POOL_NAME \
  --cluster=CLUSTER_NAME \
  --max-surge=1 \
  --max-unavailable=0

# For EKS (update the launch template)
aws eks update-nodegroup-config \
  --cluster-name CLUSTER_NAME \
  --nodegroup-name POOL_NAME \
  --update-config maxSurge=1,maxUnavailable=0
```

## Option 2: Drain and Replace Strategy
Manually drain nodes to free quota before creating new ones:

```bash
# Drain a node to free resources
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --force

# Delete the node from the cloud provider
# Then let the node pool controller create a replacement
```

## Option 3: Temporary Scale-Down
If your workload allows it:

```bash
# Scale down deployments temporarily
kubectl scale deployment DEPLOYMENT_NAME --replicas=N

# This may free up nodes that can be cordoned and drained
kubectl cordon NODE_NAME
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data
```

## Option 4: Use Different Instance Types
Switch to smaller instance types temporarily:

```bash
# Create a new node pool with smaller instances
# Migrate workloads gradually
# Delete the old pool once migration is complete
```

## Option 5: Staged Regional Upgrade
If using multiple zones, upgrade one zone at a time by:
- Temporarily reducing the node pool to single AZ
- Upgrade that subset
- Expand back and repeat

**Recommendation**: Start with Option 1 (reduce surge) as it's the safest and quickest. Set `max-surge=1` and `max-unavailable=0` to upgrade one node at a time within your quota limits.

Would you like me to provide specific commands for your cloud provider and orchestrator?
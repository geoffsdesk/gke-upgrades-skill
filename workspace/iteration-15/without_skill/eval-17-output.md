Yes, you have several options to proceed with the upgrade despite the quota constraints:

## Option 1: Reduce Surge Settings (Recommended)
Temporarily reduce the surge configuration to minimize resource requirements:

```bash
# For GKE
gcloud container node-pools update POOL_NAME \
  --cluster=CLUSTER_NAME \
  --zone=ZONE \
  --max-surge=1 \
  --max-unavailable=0

# For EKS (update the node group configuration)
aws eks update-nodegroup-config \
  --cluster-name CLUSTER_NAME \
  --nodegroup-name NODEGROUP_NAME \
  --update-config maxUnavailable=0,maxUnavailablePercentage=0

# Then retry the upgrade
```

## Option 2: Manual Rolling Update
Perform a controlled manual upgrade by cordoning and draining nodes one at a time:

```bash
# 1. Get current nodes
kubectl get nodes

# 2. For each node:
kubectl cordon NODE_NAME
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --force

# 3. Delete the old node (this frees up quota)
# For GKE:
gcloud compute instances delete NODE_NAME --zone=ZONE

# 4. The node pool will create a new node with the updated version
# 5. Wait for the new node to be ready, then repeat for next node
```

## Option 3: Temporary Scale Down
If you have workloads that can tolerate temporary reduction:

```bash
# Scale down non-critical deployments
kubectl scale deployment NON_CRITICAL_APP --replicas=0

# This frees up nodes that can be deleted to make room for surge capacity
# After upgrade, scale back up
```

## Option 4: Use Different Instance Types
If available, temporarily switch to smaller instance types for the upgrade:

```bash
# Create a new node pool with smaller instances
# Migrate workloads gradually
# Delete the old pool once migration is complete
```

## Monitoring Progress
```bash
# Watch the upgrade progress
kubectl get nodes -w

# Check node pool status
# GKE:
gcloud container node-pools describe POOL_NAME --cluster=CLUSTER_NAME

# EKS:
aws eks describe-nodegroup --cluster-name CLUSTER_NAME --nodegroup-name NODEGROUP_NAME
```

The manual rolling update (Option 2) is often the most reliable when quota-constrained, as it ensures you never exceed your current resource allocation while still completing the upgrade.
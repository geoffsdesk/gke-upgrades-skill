Yes, you have a few options to proceed with the upgrade despite the quota constraints:

## Option 1: In-Place Upgrade (if supported)
```bash
# For GKE, you can try an in-place upgrade without surge
gcloud container node-pools upgrade [NODE_POOL_NAME] \
  --cluster=[CLUSTER_NAME] \
  --zone=[ZONE] \
  --max-surge-upgrade=0 \
  --max-unavailable-upgrade=1
```

## Option 2: Manual Rolling Upgrade
Temporarily reduce your workload footprint to free up quota:

```bash
# 1. Scale down non-critical workloads
kubectl scale deployment [non-critical-app] --replicas=0

# 2. Cordon and drain nodes one by one
kubectl cordon [node-name]
kubectl drain [node-name] --ignore-daemonsets --delete-emptydir-data

# 3. Delete the old node to free quota
kubectl delete node [node-name]

# 4. Let the node pool create a new node with the updated version
# 5. Repeat for remaining nodes
```

## Option 3: Temporary Node Pool Strategy
```bash
# 1. Create a smaller temporary node pool with updated version
gcloud container node-pools create temp-pool \
  --cluster=[CLUSTER_NAME] \
  --machine-type=[smaller-instance-type] \
  --num-nodes=1

# 2. Migrate workloads gradually
kubectl cordon [old-nodes]
# Workloads will reschedule to new nodes

# 3. Delete old node pool once migration is complete
gcloud container node-pools delete [old-pool-name]
```

## Option 4: Modify Surge Settings
If your platform supports it, adjust upgrade parameters:
- Set `max-surge=0` and `max-unavailable=1`
- This upgrades one node at a time without requiring extra quota

The in-place upgrade (Option 1) is usually the quickest if your platform supports it, as it doesn't require additional compute resources during the upgrade process.
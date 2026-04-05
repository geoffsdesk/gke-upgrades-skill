Here are your options to upgrade without needing additional GPU quota for surge nodes:

## 1. Blue-Green Deployment Strategy
Create a new node pool with the upgraded configuration, migrate workloads, then delete the old pool:
```bash
# Create new pool with updated version
gcloud container node-pools create upgraded-pool \
  --cluster=your-cluster \
  --machine-type=a3-megagpu-8g \
  --num-nodes=64 \
  --node-version=TARGET_VERSION

# Cordon old nodes and drain workloads
kubectl cordon -l cloud.google.com/gke-nodepool=old-pool-name
kubectl drain -l cloud.google.com/gke-nodepool=old-pool-name --ignore-daemonsets

# Delete old pool once migration is complete
gcloud container node-pools delete old-pool-name
```

## 2. Rolling Update with Zero Surge
Modify the node pool to disable surge upgrades:
```bash
# Set max-surge to 0 and max-unavailable to a small number
gcloud container node-pools update your-pool-name \
  --cluster=your-cluster \
  --max-surge=0 \
  --max-unavailable=1
```
This upgrades nodes in-place without creating additional nodes.

## 3. Manual Batched Upgrades
Upgrade in smaller batches using node selectors:
```bash
# Upgrade specific nodes by cordoning/draining manually
kubectl cordon NODE_NAME
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data
# Node will be recreated with new version
```

## 4. Request Spot/Preemptible Quota
If available, temporarily use spot instances for surge capacity:
```bash
gcloud container node-pools update your-pool-name \
  --cluster=your-cluster \
  --spot
```

## 5. Cross-Zone Strategy
If you have quota in other zones, consider:
- Creating temporary capacity in another zone
- Moving some workloads temporarily
- Upgrading in phases

The **blue-green approach (#1)** is typically safest for critical GPU workloads, while **zero-surge rolling updates (#2)** require the least additional resources but have more downtime risk.

Which approach aligns best with your availability requirements and current setup?
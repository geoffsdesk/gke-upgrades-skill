Yes, you have several options to work around the quota constraint while waiting for the increase:

## Option 1: In-Place Upgrade (if supported)
Some platforms support in-place node upgrades without surge capacity:

**GKE:**
```bash
# Disable surge upgrade temporarily
gcloud container node-pools update POOL_NAME \
    --cluster=CLUSTER_NAME \
    --max-surge-upgrade=0 \
    --max-unavailable-upgrade=1
```

**EKS:**
```bash
# Set max unavailable instead of surge
aws eks update-nodegroup \
    --cluster-name CLUSTER_NAME \
    --nodegroup-name POOL_NAME \
    --update-config maxUnavailable=1
```

## Option 2: Manual Rolling Upgrade
Perform a controlled, manual upgrade:

```bash
# 1. Cordon nodes one by one
kubectl cordon NODE_NAME

# 2. Drain workloads
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data

# 3. Upgrade the node (platform-specific)
# 4. Uncordon when ready
kubectl uncordon NODE_NAME
```

## Option 3: Temporary Scale-Down
If your workload can tolerate it:

```bash
# 1. Scale down non-critical workloads
kubectl scale deployment NON_CRITICAL_APP --replicas=0

# 2. Reduce node pool size temporarily
# 3. Proceed with upgrade using freed quota
# 4. Scale back up after upgrade
```

## Option 4: Cross-Zone Reshuffling
If quota is zone-specific:

```bash
# Create new pool in different zone with available quota
# Migrate workloads, then upgrade original pool
```

**Recommendation:** Try Option 1 first (in-place upgrade) as it's safest and requires no additional resources. What platform are you using for your Kubernetes cluster?
Yes, there are several approaches to work around the quota limitation for your node pool upgrade:

## Option 1: In-Place Upgrade (Zero Surge)
Most managed Kubernetes services support setting surge parameters to 0:

**GKE:**
```bash
gcloud container node-pools update POOL_NAME \
  --cluster=CLUSTER_NAME \
  --zone=ZONE \
  --max-surge=0 \
  --max-unavailable=1
```

**AKS:**
```bash
az aks nodepool update \
  --cluster-name CLUSTER_NAME \
  --name POOL_NAME \
  --resource-group RG_NAME \
  --max-surge 0
```

**EKS:**
```yaml
# In your node group configuration
updateConfig:
  maxUnavailablePercentage: 25
  # Don't specify maxSurge - defaults to 0
```

## Option 2: Manual Rolling Update
1. **Cordon and drain nodes one by one:**
```bash
kubectl cordon NODE_NAME
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data
```

2. **Replace the node** (method varies by provider)
3. **Repeat for next node**

## Option 3: Temporary Workload Reduction
```bash
# Scale down non-critical workloads temporarily
kubectl scale deployment NON_CRITICAL_APP --replicas=0

# This frees up resources for surge nodes
```

## Option 4: Cross-AZ Resource Shuffling
If you have resources in multiple AZs within the region:
1. Temporarily shut down non-critical resources in other AZs
2. Use freed quota for surge nodes
3. Restore after upgrade

## Considerations:
- **In-place upgrades** increase risk of downtime but work within quota
- **Ensure PodDisruptionBudgets** are properly configured
- **Monitor critical workloads** closely during the process
- **Have rollback plan** ready

Which cloud provider and orchestration system are you using? I can provide more specific guidance.
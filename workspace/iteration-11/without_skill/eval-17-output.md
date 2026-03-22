Yes, you have several options to proceed with the upgrade despite the quota constraints:

## Option 1: In-Place Upgrade (Fastest)
If your cluster supports it, perform an in-place upgrade without surge capacity:

**GKE:**
```bash
gcloud container node-pools update POOL_NAME \
  --cluster=CLUSTER_NAME \
  --zone=ZONE \
  --max-surge-upgrade=0 \
  --max-unavailable-upgrade=1
```

**EKS:**
```bash
aws eks update-nodegroup-config \
  --cluster-name CLUSTER_NAME \
  --nodegroup-name NODEGROUP_NAME \
  --update-config maxUnavailable=1,maxUnavailablePercentage=0
```

## Option 2: Drain and Replace Manually
1. **Cordon and drain nodes one at a time:**
```bash
kubectl cordon NODE_NAME
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data
```

2. **Delete the drained node** (for managed node groups, it will be replaced automatically with the new version)

3. **Repeat for each node** until all are upgraded

## Option 3: Temporary Resource Cleanup
Free up quota temporarily:
- Scale down non-production workloads
- Delete unused node pools
- Reduce replica counts for development environments
- Check for abandoned resources (load balancers, disks, etc.)

## Option 4: Multi-Region Strategy
If your workloads support it:
- Create new node pool in a different region/zone with available quota
- Migrate workloads gradually
- Delete old node pool

## Recommendation
Start with **Option 1** (in-place upgrade) as it's the quickest and doesn't require additional resources. Just ensure you have good monitoring in place since you'll have temporary reduced capacity during the upgrade process.

Would you like me to help you implement any of these approaches?
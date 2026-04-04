This is a manageable situation, but you need to act carefully to avoid further disruption. Here's your recovery plan:

## Immediate Assessment
First, check the current state:
```bash
kubectl get nodes -o wide
# Look for node versions and Ready status

kubectl get pods --all-namespaces -o wide
# Identify any pods stuck on failed nodes
```

## Recovery Options

### Option 1: Resume the Failed Upgrade (Recommended)
Most cloud providers allow you to retry/resume a failed node pool upgrade:

**GKE:**
```bash
gcloud container operations list --filter="TYPE:UPGRADE_NODES"
# Find the failed operation, then retry
gcloud container node-pools upgrade POOL_NAME --cluster=CLUSTER_NAME
```

**EKS:**
```bash
aws eks describe-nodegroup --cluster-name CLUSTER --nodegroup-name POOL
# Check status, then update again
aws eks update-nodegroup-version --cluster-name CLUSTER --nodegroup-name POOL
```

**AKS:**
```bash
az aks nodepool upgrade --cluster-name CLUSTER --name POOL --resource-group RG
```

### Option 2: Manual Node Replacement
If resume fails, replace the remaining nodes manually:

```bash
# Cordon and drain old nodes one by one
kubectl cordon NODE_NAME
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --force

# Scale up new nodes (cloud provider specific)
# Then terminate old nodes after workloads migrate
```

## Critical Actions

1. **Don't upgrade other pools yet** - wait until this one is stable
2. **Check for version skew issues**:
   ```bash
   kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion
   ```
3. **Monitor workload health** - pods may be rescheduling
4. **Check cluster networking** - mixed versions can cause connectivity issues

## Prevention for Remaining Pools
- Upgrade remaining pools one at a time
- Use smaller batch sizes if your platform supports it
- Monitor each upgrade closely
- Consider maintenance windows for less critical pools

What cloud provider are you using? I can give more specific commands for resuming the upgrade.
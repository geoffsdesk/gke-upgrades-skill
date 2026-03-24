This is a manageable situation. Here's how to handle your partial node pool upgrade:

## Immediate Assessment

First, check the current state:
```bash
# Check node versions and status
kubectl get nodes -o wide

# Check the upgrade operation status
kubectl describe nodes | grep -E "Name:|Kernel Version:|Container Runtime Version:"

# Look for any failed pods or workloads
kubectl get pods --all-namespaces | grep -v Running
```

## Resolution Options

### Option 1: Resume the Failed Upgrade (Recommended)
Most cloud providers allow you to retry/resume a failed node pool upgrade:

```bash
# For GKE
gcloud container node-pools upgrade [NODE_POOL_NAME] \
  --cluster=[CLUSTER_NAME] \
  --zone=[ZONE]

# For EKS
aws eks update-nodegroup-version \
  --cluster-name [CLUSTER_NAME] \
  --nodegroup-name [NODE_POOL_NAME]

# For AKS
az aks nodepool upgrade \
  --cluster-name [CLUSTER_NAME] \
  --resource-group [RG_NAME] \
  --nodepool-name [NODE_POOL_NAME]
```

### Option 2: Manual Node-by-Node Upgrade
If the batch upgrade continues failing:

```bash
# Cordon and drain each old node individually
kubectl cordon [NODE_NAME]
kubectl drain [NODE_NAME] --ignore-daemonsets --delete-emptydir-data

# Then trigger replacement through your cloud provider
```

## Before Proceeding

1. **Check workload health**: Ensure your applications are running properly on the mixed-version nodes
2. **Review the error**: Check cloud provider logs for the specific failure reason
3. **Verify resources**: Ensure sufficient capacity exists for pod rescheduling

## For the Remaining Node Pools

Wait until the main workload pool is fully upgraded before touching the other two pools. This maintains stability and makes troubleshooting easier.

## Key Considerations

- **Pod Disruption Budgets**: Verify PDBs aren't blocking the upgrade
- **Resource constraints**: Check if insufficient capacity is causing scheduling issues
- **Daemonsets**: Ensure they're compatible with both node versions temporarily

What cloud provider are you using? I can provide more specific commands and troubleshooting steps.
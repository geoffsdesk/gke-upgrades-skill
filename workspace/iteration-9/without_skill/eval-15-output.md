This is a recoverable situation. Here's how to handle your partial node pool upgrade:

## Immediate Assessment

First, check the current state:
```bash
# Check cluster and node status
kubectl get nodes -o wide
kubectl get nodes --show-labels | grep -E "kubernetes.io/os|node.kubernetes.io/instance-type"

# Check for any failing workloads
kubectl get pods --all-namespaces | grep -v Running
```

## Recovery Options

### Option 1: Resume the Failed Upgrade (Recommended)
Most cloud providers allow you to retry/resume the upgrade:

**GKE:**
```bash
# Check upgrade status
gcloud container operations list --filter="targetId:CLUSTER_NAME"

# Resume/retry the upgrade
gcloud container clusters upgrade CLUSTER_NAME \
    --node-pool=POOL_NAME \
    --cluster-version=1.32.x
```

**EKS:**
```bash
# Check nodegroup status
aws eks describe-nodegroup --cluster-name CLUSTER_NAME --nodegroup-name POOL_NAME

# Update the nodegroup
aws eks update-nodegroup-version \
    --cluster-name CLUSTER_NAME \
    --nodegroup-name POOL_NAME \
    --version 1.32
```

**AKS:**
```bash
# Check upgrade status
az aks nodepool show --cluster-name CLUSTER_NAME --name POOL_NAME --resource-group RG_NAME

# Retry upgrade
az aks nodepool upgrade \
    --cluster-name CLUSTER_NAME \
    --name POOL_NAME \
    --resource-group RG_NAME \
    --kubernetes-version 1.32.x
```

### Option 2: Manual Node Replacement
If the resume fails, manually replace the remaining old nodes:

1. **Cordon and drain old nodes one by one:**
```bash
# Identify old nodes
kubectl get nodes -l kubernetes.io/version!=v1.32.x

# For each old node:
kubectl cordon NODE_NAME
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --timeout=600s
```

2. **Replace via cloud provider console or recreate the node pool**

## Before Proceeding
- **Check workload health** - ensure your 8 upgraded nodes can handle the current load
- **Review the error** - understand why the upgrade failed to prevent recurrence
- **Verify resource capacity** - ensure you have enough resources during the upgrade process

## Next Steps After Recovery
1. Wait for the main pool to complete before touching other pools
2. Upgrade remaining pools one at a time
3. Monitor application performance throughout

What cloud provider are you using? I can provide more specific commands and troubleshooting steps.
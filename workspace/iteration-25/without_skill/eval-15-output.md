This is a recoverable situation. Here's how to handle your partially failed node pool upgrade:

## Immediate Assessment

First, check the current state:
```bash
# Check node versions and status
kubectl get nodes -o wide

# Check the upgrade status and error details
kubectl describe nodes | grep -E "Version|Conditions" -A5

# Review any failed pods or workloads
kubectl get pods --all-namespaces | grep -v Running
```

## Recovery Options

### Option 1: Resume the Failed Upgrade (Recommended)
Most cloud providers allow you to retry/resume the failed upgrade:

**For GKE:**
```bash
gcloud container clusters upgrade CLUSTER_NAME \
    --node-pool=MAIN_WORKLOAD_POOL \
    --cluster-version=1.32
```

**For EKS:**
```bash
aws eks update-nodegroup-version \
    --cluster-name CLUSTER_NAME \
    --nodegroup-name MAIN_WORKLOAD_POOL \
    --version 1.32
```

**For AKS:**
```bash
az aks nodepool upgrade \
    --cluster-name CLUSTER_NAME \
    --name MAIN_WORKLOAD_POOL \
    --kubernetes-version 1.32
```

### Option 2: Manual Node Replacement
If retry fails, manually replace the remaining old nodes:

1. **Cordon and drain each old node:**
```bash
kubectl cordon NODE_NAME
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data
```

2. **Scale up new nodes** (cloud provider specific)
3. **Remove old nodes** once workloads migrate

## Key Considerations

- **Mixed versions are supported** - Kubernetes supports nodes up to 2 minor versions behind the control plane
- **Check workload compatibility** - Ensure your apps work with both 1.31 and 1.32 features
- **Monitor during upgrade** - Watch for resource constraints or pod scheduling issues
- **Complete remaining pools** - Upgrade your other two pools after resolving this one

## Before Proceeding
- Review the specific error message from the failed upgrade
- Ensure sufficient cluster resources for pod rescheduling
- Verify any custom admission controllers or policies won't block the upgrade

What cloud provider are you using? I can provide more specific troubleshooting steps based on the platform and error details.
This is a recoverable situation. Here's your step-by-step recovery plan:

## Immediate Assessment
1. **Check cluster health:**
   ```bash
   kubectl get nodes -o wide
   kubectl get pods --all-namespaces | grep -E "(Pending|CrashLoopBackOff|Error)"
   ```

2. **Identify the error:**
   ```bash
   # Check the upgrade operation status
   gcloud container operations list --filter="targetLink~your-cluster-name"
   gcloud container operations describe OPERATION_NAME --zone=YOUR_ZONE
   ```

## Recovery Options

### Option 1: Resume the Failed Upgrade (Recommended)
```bash
# Retry the node pool upgrade
gcloud container node-pools upgrade POOL_NAME \
    --cluster=CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --node-version=1.32.x
```

### Option 2: Manual Node Replacement
If the retry fails, manually replace the remaining nodes:
```bash
# Cordon old nodes first
kubectl cordon NODE_NAME

# Drain workloads (repeat for each old node)
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --force

# Delete the old nodes from the node pool
gcloud compute instances delete NODE_NAMES --zone=YOUR_ZONE
```

## Key Considerations

**Workload Compatibility:** Your workloads are likely running fine since:
- Kubernetes supports n-2 version skew between control plane (1.32) and nodes
- Your 8 upgraded nodes can handle most workloads

**Before Proceeding:**
- Ensure you have adequate capacity on the 8 upgraded nodes
- Check if any workloads have node selector constraints
- Verify PodDisruptionBudgets won't block the process

## Next Steps After Recovery
1. **Complete remaining pools:**
   ```bash
   gcloud container node-pools upgrade POOL2_NAME --cluster=CLUSTER_NAME --zone=YOUR_ZONE --node-version=1.32.x
   gcloud container node-pools upgrade POOL3_NAME --cluster=CLUSTER_NAME --zone=YOUR_ZONE --node-version=1.32.x
   ```

2. **Monitor cluster health throughout**

What specific error message did you see? This will help determine if we need a different approach.
Here's how to handle this partial node pool upgrade failure:

## Immediate Assessment

**1. Check the current state:**
```bash
# View node versions
kubectl get nodes -o wide

# Check cluster status
kubectl get nodes --show-labels | grep node-pool

# Review upgrade status in your cloud provider's console
```

**2. Identify the error:**
```bash
# Check for failed nodes
kubectl get nodes | grep -E "(NotReady|SchedulingDisabled)"

# Review events
kubectl get events --sort-by='.lastTimestamp' | tail -20
```

## Recovery Options

**Option 1: Resume the Failed Upgrade (Recommended)**
```bash
# Most cloud providers allow resuming
# GKE example:
gcloud container clusters upgrade CLUSTER_NAME \
    --node-pool=MAIN_WORKLOAD_POOL \
    --cluster-version=1.32

# EKS example:
aws eks update-nodegroup-version \
    --cluster-name CLUSTER_NAME \
    --nodegroup-name MAIN_WORKLOAD_POOL \
    --version 1.32
```

**Option 2: Manual Node Replacement**
```bash
# Cordon remaining old nodes
kubectl cordon NODE_NAME

# Drain workloads safely
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data

# Replace nodes through your cloud provider
# Then uncordon new nodes
kubectl uncordon NODE_NAME
```

## Workload Protection

**Ensure workload stability:**
```bash
# Check pod distribution
kubectl get pods -o wide --all-namespaces | grep MAIN_WORKLOAD_POOL

# Verify critical services are running
kubectl get deployments --all-namespaces
kubectl get services --all-namespaces
```

## Next Steps

1. **Fix the main pool first** - Don't touch other pools until this is resolved
2. **Monitor workload health** during the process
3. **Once main pool is stable**, proceed with other node pools one at a time
4. **Consider maintenance windows** for remaining upgrades

**What error message did you see when the upgrade failed?** This will help determine the best recovery approach.
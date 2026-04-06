This is a recoverable situation, but you need to act carefully to avoid workload disruption. Here's your step-by-step recovery plan:

## Immediate Assessment

First, check the current state:
```bash
kubectl get nodes -o wide
# Look for version mix and node status

kubectl get pods --all-namespaces -o wide --field-selector=status.phase!=Running
# Check for any disrupted workloads
```

## Recovery Options

### Option 1: Resume the Failed Upgrade (Recommended)
```bash
# Check the specific error
gcloud container operations list --filter="targetId:your-cluster-name"

# Retry the node pool upgrade
gcloud container clusters upgrade your-cluster-name \
    --node-pool=main-workload-pool \
    --cluster-version=1.32.x
```

### Option 2: Manual Node Replacement
If the automatic retry fails:
```bash
# Cordon and drain the remaining old nodes one by one
kubectl cordon NODE_NAME
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data

# The node pool should automatically replace them with 1.32 nodes
```

## Critical Considerations

**DO NOT** upgrade the other node pools yet. Having multiple node pools upgrading simultaneously with an already mixed-version cluster increases complexity.

**Pod Disruption**: With only 8/20 nodes upgraded, ensure your workloads can handle the current capacity and version mix.

**Version Skew**: K8s supports n-2 version skew, so 1.30+ nodes with 1.32 control plane should work, but resolve this quickly.

## Next Steps After Recovery

1. Complete the main workload pool upgrade
2. Verify all workloads are stable
3. Then upgrade the other two node pools sequentially
4. Monitor each upgrade completion before proceeding

What specific error message did you see when the upgrade failed? That will help determine the best recovery approach.
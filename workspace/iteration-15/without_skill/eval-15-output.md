This is a recoverable situation, but you need to act carefully to avoid workload disruptions. Here's your step-by-step recovery plan:

## Immediate Assessment

First, check the current state:
```bash
# Check cluster and node status
kubectl get nodes -o wide
kubectl get nodes --show-labels | grep node-pool

# Check for any failing pods due to version skew
kubectl get pods --all-namespaces --field-selector=status.phase=Failed
```

## Recovery Options

### Option 1: Resume the Failed Upgrade (Recommended)
```bash
# Get the specific error details
gcloud container operations list --filter="name:upgrade" --limit=5

# Retry the upgrade on the same pool
gcloud container clusters upgrade CLUSTER_NAME \
    --node-pool=MAIN_WORKLOAD_POOL \
    --zone=YOUR_ZONE \
    --async
```

### Option 2: Manual Node Replacement
If the resume fails, replace the remaining old nodes:

```bash
# Cordon old nodes first
kubectl get nodes -l cloud.google.com/gke-nodepool=MAIN_WORKLOAD_POOL \
  -o jsonpath='{.items[?(@.status.nodeInfo.kubeletVersion=="v1.31.*")].metadata.name}' | \
  xargs -I {} kubectl cordon {}

# Drain nodes one by one (be patient with this)
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --force --grace-period=300

# Delete the node from GKE
gcloud compute instances delete NODE_NAME --zone=YOUR_ZONE
```

## Key Considerations

**Version Skew**: You currently have a mixed environment (1.32 control plane, mix of 1.31/1.32 nodes). This is supported but should be temporary.

**Workload Safety**: 
- Ensure PodDisruptionBudgets are in place
- Monitor resource capacity during the process
- Upgrade during low-traffic periods if possible

**Order of Operations**:
1. Complete the main workload pool upgrade
2. Upgrade the other two node pools
3. Monitor for any application issues post-upgrade

## Monitoring During Recovery
```bash
# Watch node status
watch kubectl get nodes

# Monitor workload health
kubectl get pods --all-namespaces | grep -v Running
```

Would you like me to help you check the specific error details from the failed upgrade, or do you need guidance on any particular aspect of the recovery process?
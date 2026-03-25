This is a recoverable situation. Here's your action plan:

## Immediate Assessment
First, check the current state:
```bash
# Check node versions and status
kubectl get nodes -o wide

# Check the failed upgrade status
kubectl describe nodes <failed-node-name>

# Check for any pod scheduling issues
kubectl get pods --all-namespaces -o wide | grep -E "(Pending|Failed)"
```

## Recovery Options

### Option 1: Resume the Failed Upgrade (Recommended)
```bash
# Try to resume the node pool upgrade
gcloud container node-pools upgrade <POOL_NAME> \
    --cluster=<CLUSTER_NAME> \
    --zone=<ZONE> \
    --node-version=1.32

# Or if using regional cluster
gcloud container node-pools upgrade <POOL_NAME> \
    --cluster=<CLUSTER_NAME> \
    --region=<REGION> \
    --node-version=1.32
```

### Option 2: Manual Node Replacement
If resume fails, manually replace the remaining old nodes:
```bash
# Cordon and drain each old node
kubectl cordon <old-node-name>
kubectl drain <old-node-name> --ignore-daemonsets --delete-emptydir-data --force

# Delete the old node from the node pool
gcloud compute instances delete <old-node-name> --zone=<ZONE>
```

The node pool will automatically create new nodes with v1.32.

## Best Practices Moving Forward

1. **Smaller batches**: Use `--max-surge` and `--max-unavailable` to control upgrade pace:
```bash
gcloud container node-pools upgrade <POOL_NAME> \
    --cluster=<CLUSTER_NAME> \
    --max-surge=1 \
    --max-unavailable=1
```

2. **Test with non-critical pools first**: Upgrade your other two pools before fixing the main workload pool to test the process.

3. **Monitor during upgrade**:
```bash
watch kubectl get nodes
kubectl get events --sort-by='.lastTimestamp'
```

## Troubleshooting the Root Cause
Check what caused the failure:
```bash
gcloud logging read "resource.type=gke_cluster AND resource.labels.cluster_name=<CLUSTER_NAME>" \
    --limit=50 --format="table(timestamp,severity,textPayload)"
```

Would you like me to help you identify the specific error that caused the upgrade to fail?
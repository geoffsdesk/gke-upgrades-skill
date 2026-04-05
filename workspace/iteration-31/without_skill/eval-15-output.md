This is a recoverable situation. Here's how to handle your partially failed node pool upgrade:

## Immediate Assessment

First, check the current state:
```bash
# Check node versions and status
kubectl get nodes -o wide

# Check the upgrade operation status
kubectl describe nodepool <workload-pool-name>

# Look for specific error messages
kubectl get events --sort-by='.lastTimestamp' | grep -i upgrade
```

## Recovery Options

### Option 1: Resume the Failed Upgrade
If the upgrade process is still active but stalled:
```bash
# Try to resume the upgrade operation
gcloud container node-pools upgrade <pool-name> \
    --cluster=<cluster-name> \
    --zone=<zone> \
    --node-version=1.32

# Or via kubectl if using cluster autoscaler
kubectl patch nodepool <pool-name> -p '{"spec":{"version":"1.32"}}'
```

### Option 2: Manual Node-by-Node Upgrade
If the batch upgrade is stuck:
```bash
# Upgrade remaining nodes individually
for node in $(kubectl get nodes -l pool=<pool-name> -o name | grep v1.31); do
    kubectl drain $node --ignore-daemonsets --delete-emptydir-data --timeout=300s
    # Wait for node to upgrade via node auto-upgrade or manual intervention
    kubectl uncordon $node
done
```

### Option 3: Recreate Problematic Nodes
```bash
# Identify and recreate stuck nodes
kubectl get nodes --show-labels | grep NotReady

# For each problematic node:
kubectl drain <node-name> --ignore-daemonsets --force
kubectl delete node <node-name>
# The node pool will create a replacement with the target version
```

## Prevention for Remaining Pools

For your other two node pools:
- Upgrade during low-traffic periods
- Use smaller batch sizes: `--max-surge=1 --max-unavailable=0`
- Monitor resource availability before starting
- Ensure adequate cluster resources for pod rescheduling

## Key Considerations

- **Workload Impact**: Check if your applications are still running properly on the mixed-version nodes
- **Pod Disruption Budgets**: Ensure PDBs aren't blocking the node drain process
- **Resource Constraints**: Verify sufficient capacity exists for pod rescheduling
- **Monitoring**: Watch cluster health throughout the process

Would you like me to help you investigate the specific error that caused the initial failure?
This is a manageable situation, but you need to act carefully to avoid workload disruption. Here's your recovery plan:

## Immediate Assessment

First, check the current state:
```bash
# Check node versions and status
kubectl get nodes -o wide

# Check the failed upgrade error details
kubectl describe nodes <failed-node-name>
```

## Recovery Options

### Option 1: Resume/Retry the Failed Upgrade (Recommended)
Most cloud providers allow you to retry a failed node pool upgrade:

**For GKE:**
```bash
gcloud container operations list --filter="TYPE:UPGRADE_NODES"
# Find the failed operation, then retry
gcloud container node-pools upgrade POOL_NAME --cluster=CLUSTER_NAME --zone=ZONE
```

**For EKS:**
Check the managed node group status and update:
```bash
aws eks describe-nodegroup --cluster-name CLUSTER --nodegroup-name POOL_NAME
aws eks update-nodegroup-version --cluster-name CLUSTER --nodegroup-name POOL_NAME
```

**For AKS:**
```bash
az aks nodepool upgrade --cluster-name CLUSTER --name POOL_NAME --resource-group RG
```

### Option 2: If Retry Fails - Manual Remediation

1. **Cordon and drain problematic nodes:**
```bash
kubectl cordon <node-name>
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data --force
```

2. **Remove failed nodes from the pool and let auto-scaling replace them**

## Before Proceeding

1. **Ensure workload resilience:**
   - Verify your applications can handle the mixed-version nodes temporarily
   - Check that critical workloads have adequate replicas on upgraded nodes

2. **Check resource capacity:**
   - Ensure the 8 upgraded nodes can handle your workload during the upgrade

## Next Steps After Main Pool Recovery

1. **Upgrade remaining node pools one at a time**
2. **Monitor application health between each pool upgrade**
3. **Keep the upgrade window reasonable to avoid prolonged version skew**

## Important Considerations

- **Version skew**: Nodes can be 1-2 minor versions behind the control plane, so you have some time
- **Schedule maintenance window**: Plan for potential workload disruption
- **Backup plan**: Have a rollback strategy ready

What cloud provider are you using? I can provide more specific commands for your platform.
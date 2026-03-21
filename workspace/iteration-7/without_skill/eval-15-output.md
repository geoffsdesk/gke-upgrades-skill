This is a recoverable situation. Here's how to handle your partial node pool upgrade:

## Immediate Assessment

First, check the current state:
```bash
# Check node versions and status
kubectl get nodes -o wide

# Check the upgrade operation status
kubectl describe nodes | grep -E "KubeletVersion|Ready"
```

## Recovery Options

### Option 1: Resume the Failed Upgrade (Recommended)
```bash
# Check the upgrade status
gcloud container operations list --filter="TYPE:UPGRADE_NODES"

# If the operation is still running but stuck, you can try to resume
gcloud container node-pools upgrade [NODE_POOL_NAME] \
    --cluster=[CLUSTER_NAME] \
    --zone=[ZONE] \
    --node-version=1.32

# Use --async flag to run in background
```

### Option 2: Gradual Manual Approach
If the bulk upgrade keeps failing:
```bash
# Upgrade remaining nodes in smaller batches
gcloud container node-pools upgrade [NODE_POOL_NAME] \
    --cluster=[CLUSTER_NAME] \
    --zone=[ZONE] \
    --node-version=1.32 \
    --max-surge-upgrade=1 \
    --max-unavailable-upgrade=0
```

## Monitor Workload Health
```bash
# Check pod distribution and health
kubectl get pods -o wide --all-namespaces | grep -E "Pending|Error"

# Monitor during upgrade
watch kubectl get nodes
```

## Key Considerations

- **Mixed versions are supported**: Nodes can run N-2 versions behind the control plane
- **No rush**: Your workloads should continue running normally
- **Plan remaining pools**: Consider upgrading your other two pools during lower-traffic periods

## Troubleshooting Common Issues

Check for:
- Resource quotas being hit
- Pod disruption budgets blocking drainage
- Insufficient surge capacity
- Network connectivity issues

Would you like me to help you investigate the specific error that caused the upgrade to fail? Can you share the error message from the GKE operation logs?
This is a manageable situation. Here's your recovery plan:

## Immediate Assessment
First, check the current state:
```bash
# Check node versions and status
kubectl get nodes -o wide

# Check the upgrade status and error details
kubectl describe nodes | grep -A5 -B5 "KubeletVersion\|Ready"

# Check for any stuck pods or workload issues
kubectl get pods --all-namespaces --field-selector=status.phase!=Running
```

## Recovery Options

### Option 1: Resume the Failed Upgrade (Recommended)
```bash
# Get the specific error from GKE
gcloud container operations list --filter="status=RUNNING OR status=DONE" --limit=5

# Attempt to resume/retry the node pool upgrade
gcloud container clusters upgrade [CLUSTER-NAME] \
    --node-pool=[MAIN-WORKLOAD-POOL] \
    --zone=[YOUR-ZONE] \
    --cluster-version=1.30
```

### Option 2: Manual Node Replacement
If the upgrade can't resume:
```bash
# Cordon and drain the old nodes one by one
kubectl cordon [OLD-NODE-NAME]
kubectl drain [OLD-NODE-NAME] --ignore-daemonsets --delete-emptydir-data --force

# For each old node, you may need to manually delete and let GKE replace it
gcloud container clusters resize [CLUSTER-NAME] \
    --node-pool=[MAIN-WORKLOAD-POOL] \
    --num-nodes=[CURRENT-SIZE] \
    --zone=[YOUR-ZONE]
```

## What to Monitor
- **Pod scheduling**: Ensure workloads can still schedule on available nodes
- **Resource capacity**: You're running with reduced capacity (12/20 nodes)
- **Cross-version compatibility**: 1.29 and 1.30 nodes should coexist fine

## Next Steps After Recovery
1. Complete the main workload pool upgrade
2. Upgrade your other two node pools
3. Consider implementing blue-green node pool upgrades for future updates

**Immediate priority**: Get that main workload pool upgrade completed. The mixed-version state is temporary but should be resolved promptly.

What specific error message are you seeing in the GKE console or operations list?
This is a recoverable situation, but you need to act methodically to avoid service disruption. Here's your action plan:

## Immediate Assessment

1. **Check cluster health**:
   ```bash
   kubectl get nodes
   kubectl get pods --all-namespaces -o wide
   ```

2. **Identify the failure cause**:
   ```bash
   # Check GKE operations logs
   gcloud container operations list --filter="operationType=UPGRADE_NODES"
   gcloud container operations describe [OPERATION-ID]
   ```

## Recovery Options

### Option 1: Retry the Failed Upgrade (Recommended first try)
```bash
# Retry the node pool upgrade
gcloud container node-pools upgrade [NODE-POOL-NAME] \
    --cluster=[CLUSTER-NAME] \
    --zone=[ZONE] \
    --node-version=1.32
```

### Option 2: Manual Node Replacement (if retry fails)
```bash
# Cordon and drain the mixed-version nodes
kubectl cordon [NODE-NAME]
kubectl drain [NODE-NAME] --ignore-daemonsets --delete-emptydir-data

# Delete problematic nodes to force recreation
gcloud compute instances delete [INSTANCE-NAME] --zone=[ZONE]
```

### Option 3: Create New Node Pool (safest for critical workloads)
```bash
# Create new node pool with v1.32
gcloud container node-pools create [NEW-POOL-NAME] \
    --cluster=[CLUSTER-NAME] \
    --node-version=1.32 \
    --num-nodes=[COUNT] \
    --zone=[ZONE]

# Migrate workloads, then delete old pool
```

## Next Steps

1. **Complete the main pool upgrade** using one of the above methods
2. **Upgrade remaining pools** one at a time:
   ```bash
   gcloud container node-pools upgrade [POOL-NAME] \
       --cluster=[CLUSTER-NAME] \
       --node-version=1.32
   ```

3. **Monitor throughout**:
   ```bash
   watch kubectl get nodes
   kubectl get events --sort-by='.lastTimestamp'
   ```

What error message did you see when the upgrade failed? That will help determine the best recovery approach.
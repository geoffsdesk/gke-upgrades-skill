This is a recoverable situation. Here's your step-by-step recovery plan:

## Immediate Assessment
1. **Check cluster status**:
   ```bash
   kubectl get nodes -o wide
   ```
   Look for version mismatches and node readiness

2. **Identify the error**:
   - Check GKE console for specific failure message
   - Review operation logs in Cloud Logging
   - Common causes: resource quotas, zone availability, custom node configurations

## Recovery Options

### Option 1: Resume the Failed Upgrade (Recommended)
```bash
# Check the current operation status
gcloud container operations list --filter="TYPE:UPGRADE_NODES"

# If operation is stuck, try resuming
gcloud container clusters upgrade [CLUSTER-NAME] \
    --node-pool=[FAILED-POOL-NAME] \
    --cluster-version=1.32 \
    --zone=[YOUR-ZONE]
```

### Option 2: Rollback Strategy (If Resume Fails)
```bash
# Create a new node pool with 1.32
gcloud container node-pools create temp-pool-132 \
    --cluster=[CLUSTER-NAME] \
    --machine-type=[SAME-AS-ORIGINAL] \
    --num-nodes=[DESIRED-SIZE] \
    --node-version=1.32

# Cordon old mixed-version nodes
kubectl cordon [OLD-NODE-NAMES]

# Drain workloads to new nodes
kubectl drain [OLD-NODE] --ignore-daemonsets --delete-emptydir-data

# Delete old pool once workloads are migrated
gcloud container node-pools delete [FAILED-POOL-NAME]
```

## Before Proceeding
- **Backup check**: Ensure you have recent backups of critical data
- **Workload tolerance**: Verify your apps can handle the current mixed-version state temporarily
- **Resource quotas**: Check if you hit any limits (CPU, IP addresses, persistent disks)

## For the Untouched Pools
**Wait** until the main pool issue is resolved. Upgrading with a mixed/broken state could complicate recovery.

What specific error message are you seeing in the GKE console? This will help determine the best recovery approach.
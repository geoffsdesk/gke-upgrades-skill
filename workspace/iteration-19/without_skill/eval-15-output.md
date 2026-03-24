This is a recoverable situation. Here's your action plan:

## Immediate Assessment
1. **Check the failed upgrade status:**
   ```bash
   kubectl get nodes -o wide
   gcloud container node-pools describe [POOL-NAME] --cluster=[CLUSTER-NAME] --zone=[ZONE]
   ```

2. **Identify the specific error:**
   ```bash
   gcloud logging read "resource.type=gke_cluster AND resource.labels.cluster_name=[CLUSTER-NAME]" --limit=50 --format=json
   ```

## Recovery Options

### Option 1: Resume the Failed Upgrade
```bash
# Try to resume the upgrade
gcloud container node-pools upgrade [POOL-NAME] \
  --cluster=[CLUSTER-NAME] \
  --zone=[ZONE] \
  --node-version=1.32.x
```

### Option 2: Manual Node-by-Node Recovery
If the bulk upgrade won't resume:
```bash
# List nodes in the pool
kubectl get nodes -l cloud.google.com/gke-nodepool=[POOL-NAME]

# Manually upgrade remaining nodes
gcloud container node-pools upgrade [POOL-NAME] \
  --cluster=[CLUSTER-NAME] \
  --zone=[ZONE] \
  --node-version=1.32.x \
  --max-surge-upgrade=1 \
  --max-unavailable-upgrade=0
```

### Option 3: Create New Node Pool (Safest)
```bash
# Create new pool with 1.32
gcloud container node-pools create [NEW-POOL-NAME] \
  --cluster=[CLUSTER-NAME] \
  --zone=[ZONE] \
  --node-version=1.32.x \
  --num-nodes=[DESIRED-COUNT]

# Migrate workloads, then delete old pool
```

## Common Failure Causes & Solutions
- **Insufficient quota**: Check compute quotas in the region
- **Pod disruption budgets**: Temporarily relax PDBs if safe
- **Node cordoning issues**: Manually uncordon stuck nodes
- **Resource constraints**: Increase max-surge-upgrade settings

## For the Other Node Pools
Wait until the main pool is stable, then upgrade them one at a time with conservative settings:
```bash
--max-surge-upgrade=1 --max-unavailable-upgrade=0
```

What specific error are you seeing in the logs? That will help determine the best recovery approach.
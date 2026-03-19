Yes, you have several options to work around the quota constraint. Here's how to proceed:

## Option 1: Blue-Green Upgrade (Recommended)

Instead of surge, create a new node pool at the target version within your existing quota, then migrate workloads.

```bash
# 1. Cancel the stuck surge upgrade
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE
# Note the operation ID, then let it complete its current node and stop

# 2. Create new node pool with target version
gcloud container node-pools create POOL_NAME-v2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION \
  --num-nodes NUM_NODES \
  --machine-type MACHINE_TYPE \
  --disk-size DISK_SIZE

# 3. Cordon old nodes to prevent new pods
kubectl cordon -l cloud.google.com/gke-nodepool=OLD_POOL_NAME

# 4. Drain old nodes gradually (respects PDBs)
for node in $(kubectl get nodes -l cloud.google.com/gke-nodepool=OLD_POOL_NAME -o name); do
  kubectl drain $node --ignore-daemonsets --delete-emptydir-data --force --grace-period=60
  sleep 30  # Brief pause between nodes
done

# 5. Delete old pool once workloads migrated
gcloud container node-pools delete OLD_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE
```

## Option 2: Scale Down, Then Surge

Temporarily reduce your cluster size to free quota for surge nodes.

```bash
# 1. Scale down non-critical workloads
kubectl scale deployment NON_CRITICAL_APP --replicas=0 -n NAMESPACE

# 2. Or reduce node pool size temporarily
gcloud container node-pools resize NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --num-nodes REDUCED_COUNT

# 3. Configure conservative surge settings
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# 4. Resume upgrade
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION

# 5. Scale back up after upgrade completes
```

## Option 3: Rolling Upgrade with maxUnavailable

Accept some downtime in exchange for no additional quota usage.

```bash
# Configure to upgrade in-place without surge
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1

# This upgrades nodes one at a time without creating extras
```

⚠️ **Important considerations:**

- **Option 1 (Blue-Green)** is safest — instant rollback by switching traffic back
- **Option 2** requires identifying truly non-critical workloads
- **Option 3** will cause pod disruptions as nodes upgrade in-place

**For stateful workloads or production clusters, strongly recommend Option 1.** The blue-green approach gives you full control over the migration timing and an easy rollback path.

Which option fits your environment best? I can provide more detailed commands once you choose your approach.
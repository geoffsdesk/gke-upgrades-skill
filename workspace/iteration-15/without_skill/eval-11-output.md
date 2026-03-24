I'll walk you through a safe GKE upgrade strategy for your Elasticsearch cluster. Given your setup with separate node pools, we can do a rolling upgrade with minimal impact.

## Pre-Upgrade Preparation

### 1. Backup Your Data
```bash
# Create a snapshot repository (if not already configured)
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_snapshot/gcs-backup" -H 'Content-Type: application/json' -d'
{
  "type": "gcs",
  "settings": {
    "bucket": "your-backup-bucket"
  }
}'

# Create a full cluster snapshot
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_snapshot/gcs-backup/pre-upgrade-$(date +%Y%m%d)" -H 'Content-Type: application/json' -d'
{
  "indices": "*",
  "ignore_unavailable": true,
  "include_global_state": true
}'
```

### 2. Verify Cluster Health
```bash
# Check cluster status
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"

# Ensure all shards are allocated
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/shards?v&h=index,shard,prirep,state,unassigned.reason"
```

### 3. Configure Elasticsearch for Maintenance
```bash
# Disable shard allocation to prevent rebalancing during node restarts
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'

# Optional: Stop indexing if possible during upgrade
kubectl exec -it es-master-0 -- curl -X POST "localhost:9200/_flush/synced"
```

## Rolling Upgrade Strategy

### Phase 1: Upgrade Coordinating Nodes (Least Impact)
```bash
# Get coordinating node pool name
COORD_POOL=$(kubectl get nodes -l node-type=coordinating -o jsonpath='{.items[0].metadata.labels.cloud\.google\.com/gke-nodepool}')

# Upgrade coordinating node pool
gcloud container node-pools upgrade $COORD_POOL \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32

# Wait for completion and verify
kubectl get nodes -l node-type=coordinating
kubectl get pods -l component=elasticsearch-coordinating -o wide
```

### Phase 2: Upgrade Data Nodes (One by One)
```bash
# Get data node pool
DATA_POOL=$(kubectl get nodes -l node-type=data -o jsonpath='{.items[0].metadata.labels.cloud\.google\.com/gke-nodepool}')

# For data nodes, we'll do a more controlled upgrade
# First, cordon and drain one node at a time
for node in $(kubectl get nodes -l node-type=data -o jsonpath='{.items[*].metadata.name}'); do
  echo "Upgrading node: $node"
  
  # Cordon the node
  kubectl cordon $node
  
  # Check cluster health before proceeding
  kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health" | jq '.status'
  
  # Drain the node (this will trigger pod rescheduling)
  kubectl drain $node --ignore-daemonsets --delete-emptydir-data --force --grace-period=300
  
  # Wait for Elasticsearch to stabilize
  sleep 60
  
  # Verify cluster is still functional
  kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health?wait_for_status=yellow&timeout=5m"
  
  echo "Node $node drained successfully"
done

# Now upgrade the entire data node pool
gcloud container node-pools upgrade $DATA_POOL \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32
```

### Phase 3: Upgrade Master Nodes (Most Critical)
```bash
# Get master node pool
MASTER_POOL=$(kubectl get nodes -l node-type=master -o jsonpath='{.items[0].metadata.labels.cloud\.google\.com/gke-nodepool}')

# Enable shard allocation before master upgrade
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "all"
  }
}'

# Wait for cluster to be green
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health?wait_for_status=green&timeout=10m"

# Upgrade master node pool
gcloud container node-pools upgrade $MASTER_POOL \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32
```

## Post-Upgrade Verification

### 1. Verify All Nodes and Pods
```bash
# Check node versions
kubectl get nodes -o wide

# Check all ES pods are running
kubectl get pods -l app=elasticsearch -o wide

# Check StatefulSet status
kubectl get statefulsets
```

### 2. Verify Elasticsearch Cluster Health
```bash
# Comprehensive cluster check
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/nodes?v"
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/indices?v"

# Check for any unassigned shards
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/shards?h=index,shard,prirep,state,unassigned.reason" | grep UNASSIGNED
```

### 3. Re-enable Normal Operations
```bash
# Ensure shard allocation is enabled
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "all"
  }
}'

# Resume indexing operations if they were paused
```

## Emergency Rollback Plan

If issues occur during upgrade:

```bash
# Rollback a node pool
gcloud container node-pools rollback $NODE_POOL_NAME \
  --cluster=your-cluster-name \
  --zone=your-zone

# Restore from snapshot if data corruption occurs
kubectl exec -it es-master-0 -- curl -X POST "localhost:9200/_snapshot/gcs-backup/pre-upgrade-YYYYMMDD/_restore" -H 'Content-Type: application/json' -d'
{
  "indices": "*",
  "ignore_unavailable": true,
  "include_global_state": true
}'
```

## Key Considerations

1. **Regional PD-SSD**: Your data persists across the upgrade since PVs are independent of nodes
2. **Master Quorum**: With 3 masters, you maintain quorum during rolling restarts
3. **Data Availability**: 5 data nodes provide redundancy during individual node upgrades
4. **Coordinating Nodes**: These are stateless, so they're safest to upgrade first

The entire process should take 2-4 hours depending on your cluster size and shard rebalancing time. Monitor cluster health closely throughout the process.
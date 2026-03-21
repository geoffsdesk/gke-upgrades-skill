I'll walk you through a zero-downtime upgrade strategy for your Elasticsearch cluster on GKE. This approach minimizes risk by upgrading one node pool at a time while maintaining cluster availability.

## Pre-Upgrade Preparation

### 1. Verify Cluster Health
```bash
# Check Elasticsearch cluster health
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"

# Verify all nodes are operational
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/nodes?v"

# Check shard allocation
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/shards?v"
```

### 2. Backup Critical Data
```bash
# Create snapshot repository (if not already configured)
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_snapshot/gcs_backup" -H 'Content-Type: application/json' -d'
{
  "type": "gcs",
  "settings": {
    "bucket": "your-backup-bucket",
    "base_path": "elasticsearch-snapshots"
  }
}'

# Create full cluster snapshot
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_snapshot/gcs_backup/pre-upgrade-$(date +%Y%m%d)" -H 'Content-Type: application/json' -d'
{
  "indices": "*",
  "ignore_unavailable": true,
  "include_global_state": true
}'
```

### 3. Configure Elasticsearch for Upgrade
```bash
# Disable shard allocation to prevent rebalancing during upgrade
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'

# Increase recovery settings for faster rebalancing later
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "transient": {
    "cluster.routing.allocation.cluster_concurrent_rebalance": "4",
    "cluster.routing.allocation.node_concurrent_recoveries": "4",
    "indices.recovery.max_bytes_per_sec": "100mb"
  }
}'
```

## Upgrade Strategy: Coordinating → Data → Master

### Phase 1: Upgrade Coordinating Nodes
Coordinating nodes are stateless and safest to upgrade first.

```bash
# Get current node pool version
gcloud container node-pools describe coordinating-pool \
  --cluster=your-cluster-name \
  --zone=your-zone

# Upgrade coordinating node pool
gcloud container node-pools upgrade coordinating-pool \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32.x-gke.xxxx

# Monitor the upgrade
kubectl get nodes -l node-pool=coordinating-pool -w
```

Wait for coordinating nodes to be ready before proceeding.

### Phase 2: Upgrade Data Nodes (One by One)
Data nodes require careful sequential upgrading to maintain data availability.

```bash
# Upgrade data node pool
gcloud container node-pools upgrade data-pool \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32.x-gke.xxxx \
  --max-surge-upgrade=1 \
  --max-unavailable-upgrade=0
```

Monitor each data node upgrade:
```bash
# Watch node status
kubectl get nodes -l node-pool=data-pool -w

# Monitor Elasticsearch cluster health during upgrade
watch "kubectl exec -it es-master-0 -- curl -s 'localhost:9200/_cluster/health?pretty'"

# Check that shards remain available
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/shards?v&h=index,shard,prirep,state,unassigned.reason"
```

### Phase 3: Upgrade Master Nodes (One by One)
Master nodes are most critical - upgrade one at a time with extra caution.

```bash
# Upgrade master node pool with minimal disruption
gcloud container node-pools upgrade master-pool \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32.x-gke.xxxx \
  --max-surge-upgrade=1 \
  --max-unavailable-upgrade=0
```

Monitor master election during upgrade:
```bash
# Watch master election
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/master?v"

# Monitor cluster state
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/state/master_node?pretty"
```

## Post-Upgrade Verification

### 1. Re-enable Shard Allocation
```bash
# Re-enable full shard allocation
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "all"
  }
}'
```

### 2. Verify Cluster Health
```bash
# Wait for green status
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?wait_for_status=green&timeout=300s&pretty"

# Verify all nodes are on new Kubernetes version
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,POOL:.metadata.labels.cloud\.google\.com/gke-nodepool

# Verify all Elasticsearch nodes are healthy
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/nodes?v&h=name,heap.percent,ram.percent,cpu,load_1m,node.role,master"
```

### 3. Performance Validation
```bash
# Test indexing performance
kubectl exec -it es-master-0 -- curl -X POST "localhost:9200/test-index/_doc" -H 'Content-Type: application/json' -d'
{
  "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%S.000Z)'",
  "message": "upgrade test"
}'

# Test search performance
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_search?pretty"

# Clean up test
kubectl exec -it es-master-0 -- curl -X DELETE "localhost:9200/test-index"
```

## Rollback Plan

If issues occur during upgrade:

```bash
# Emergency: Disable shard allocation if cluster is unstable
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "none"
  }
}'

# Rollback node pool (if within rollback window)
gcloud container node-pools rollback data-pool \
  --cluster=your-cluster-name \
  --zone=your-zone

# Restore from snapshot if needed
kubectl exec -it es-master-0 -- curl -X POST "localhost:9200/_snapshot/gcs_backup/pre-upgrade-YYYYMMDD/_restore"
```

## Monitoring Throughout Upgrade

Keep these commands running in separate terminals:
```bash
# Terminal 1: Node status
watch "kubectl get nodes -o custom-columns=NAME:.metadata.name,STATUS:.status.conditions[3].type,VERSION:.status.nodeInfo.kubeletVersion"

# Terminal 2: Pod status
watch "kubectl get pods -o wide"

# Terminal 3: ES cluster health
watch "kubectl exec -it es-master-0 -- curl -s localhost:9200/_cluster/health?pretty"

# Terminal 4: ES nodes
watch "kubectl exec -it es-master-0 -- curl -s localhost:9200/_cat/nodes?v"
```

## Key Success Factors

1. **Timing**: Perform during low-traffic periods
2. **Patience**: Wait for each phase to complete fully before proceeding
3. **Monitoring**: Continuously monitor both Kubernetes and Elasticsearch health
4. **Regional PVs**: Your regional pd-ssd volumes will automatically reattach to new nodes
5. **StatefulSet**: Will handle pod recreation with proper PV attachment

The entire upgrade should take 2-4 hours depending on your cluster size, with minimal to zero downtime for your Elasticsearch cluster.
I'll walk you through a safe GKE cluster upgrade strategy for your Elasticsearch deployment. Given your multi-node-pool setup with StatefulSets, we need to be methodical to maintain data integrity and availability.

## Pre-Upgrade Preparation

### 1. Create Full Backup
```bash
# Create snapshot repository (if not already configured)
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_snapshot/gcs-backup" -H 'Content-Type: application/json' -d'
{
  "type": "gcs",
  "settings": {
    "bucket": "your-es-backup-bucket"
  }
}'

# Create full cluster snapshot
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

# Verify all nodes are visible
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/nodes?v"

# Check shard allocation
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/shards?v&h=index,shard,prirep,state,node"
```

### 3. Disable Shard Allocation
```bash
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'
```

## Upgrade Strategy: Node Pool by Node Pool

### Phase 1: Upgrade Coordinating Nodes First
Coordinating nodes are safest to start with as they don't hold data.

```bash
# List current node pools
gcloud container node-pools list --cluster=your-cluster --zone=your-zone

# Upgrade coordinating node pool
gcloud container clusters upgrade your-cluster \
  --node-pool=coordinating-pool \
  --cluster-version=1.30 \
  --zone=your-zone
```

Wait for completion and verify:
```bash
kubectl get nodes -l node-pool=coordinating-pool
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/nodes?v"
```

### Phase 2: Upgrade Master Nodes (One at a time)
```bash
# First, identify which master is currently active
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/master?v"

# Upgrade master node pool
gcloud container clusters upgrade your-cluster \
  --node-pool=master-pool \
  --cluster-version=1.30 \
  --zone=your-zone \
  --max-surge-upgrade=1 \
  --max-unavailable-upgrade=0
```

Monitor master election during the process:
```bash
# Watch master changes
watch 'kubectl exec -it es-master-0 -- curl -s -X GET "localhost:9200/_cat/master?v"'
```

### Phase 3: Upgrade Data Nodes (Carefully)
This is the most critical phase. We'll do a rolling upgrade with careful monitoring.

```bash
# Set max unavailable to 1 to ensure gradual replacement
gcloud container clusters upgrade your-cluster \
  --node-pool=data-pool \
  --cluster-version=1.30 \
  --zone=your-zone \
  --max-surge-upgrade=1 \
  --max-unavailable-upgrade=1
```

Monitor shard recovery between each node replacement:
```bash
# Monitor cluster health during upgrade
watch 'kubectl exec -it es-master-0 -- curl -s -X GET "localhost:9200/_cluster/health" | jq .'

# Watch shard recovery
watch 'kubectl exec -it es-master-0 -- curl -s -X GET "localhost:9200/_cat/recovery?active_only&v"'
```

### Phase 4: Re-enable Shard Allocation
After all nodes are upgraded:

```bash
# Re-enable full shard allocation
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "all"
  }
}'
```

## Post-Upgrade Verification

### 1. Verify All Nodes
```bash
# Check Kubernetes nodes
kubectl get nodes -o wide

# Check Elasticsearch cluster
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/nodes?v&h=name,node.role,version"
```

### 2. Verify Data Integrity
```bash
# Check cluster health
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"

# Verify all indices are healthy
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/indices?v&health=yellow,red"

# Check shard allocation
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/allocation?v"
```

### 3. Functional Testing
```bash
# Test search functionality
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_search?q=*&size=1&pretty"

# Test indexing (if safe to do so)
kubectl exec -it es-master-0 -- curl -X POST "localhost:9200/test-index/_doc" -H 'Content-Type: application/json' -d'
{
  "test": "upgrade-verification",
  "timestamp": "'$(date)'"
}'
```

## Rollback Plan (If Needed)

If issues arise during the upgrade:

```bash
# Emergency: Scale down problematic StatefulSet
kubectl scale statefulset es-data --replicas=0

# Restore from backup if data corruption occurs
kubectl exec -it es-master-0 -- curl -X POST "localhost:9200/_snapshot/gcs-backup/pre-upgrade-YYYYMMDD/_restore" -H 'Content-Type: application/json' -d'
{
  "indices": "*",
  "ignore_unavailable": true,
  "include_global_state": true
}'
```

## Key Monitoring Points

Throughout the upgrade, monitor:
- **PV attachment**: Ensure PVs reattach correctly to new nodes
- **StatefulSet pod startup**: Watch for any pods stuck in pending/init states
- **Elasticsearch cluster state**: Ensure quorum is maintained
- **Shard recovery**: Monitor recovery progress between node replacements

## Additional Considerations

1. **Maintenance Window**: Plan for 2-4 hours depending on data size
2. **Network Policies**: Verify connectivity between new nodes
3. **Resource Limits**: Ensure new nodes have adequate resources
4. **Elasticsearch Version**: Consider if ES version is compatible with K8s 1.30
5. **Monitoring**: Have your monitoring dashboards ready to track the process

This approach minimizes risk by upgrading non-data nodes first, maintaining Elasticsearch quorum, and ensuring data availability throughout the process.
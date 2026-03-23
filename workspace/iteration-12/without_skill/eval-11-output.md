I'll walk you through a safe GKE cluster upgrade strategy for your Elasticsearch setup. Given your multi-node architecture, we can maintain availability throughout the process.

## Pre-Upgrade Preparation

### 1. Backup Your Data
```bash
# Create a snapshot repository (if not already configured)
curl -X PUT "localhost:9200/_snapshot/gcs-backup" -H 'Content-Type: application/json' -d'
{
  "type": "gcs",
  "settings": {
    "bucket": "your-backup-bucket",
    "base_path": "elasticsearch-snapshots"
  }
}'

# Create a full cluster snapshot
curl -X PUT "localhost:9200/_snapshot/gcs-backup/pre-upgrade-$(date +%Y%m%d)" -H 'Content-Type: application/json' -d'
{
  "indices": "*",
  "ignore_unavailable": true,
  "include_global_state": true
}'
```

### 2. Verify Cluster Health
```bash
# Check cluster status
kubectl exec -it elasticsearch-master-0 -- curl -s "localhost:9200/_cluster/health?pretty"

# Verify all nodes are visible
kubectl exec -it elasticsearch-master-0 -- curl -s "localhost:9200/_cat/nodes?v"

# Check for any unassigned shards
kubectl exec -it elasticsearch-master-0 -- curl -s "localhost:9200/_cat/shards?h=index,shard,prirep,state,unassigned.reason" | grep UNASSIGNED
```

### 3. Disable Shard Allocation (temporarily)
```bash
kubectl exec -it elasticsearch-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'
```

## Upgrade Strategy: Rolling Node Pool Updates

### Phase 1: Upgrade Coordinating Nodes (Lowest Risk)
```bash
# Get current node pool version
gcloud container node-pools describe coordinating-pool \
  --cluster=your-cluster-name \
  --zone=your-zone

# Upgrade coordinating node pool
gcloud container node-pools upgrade coordinating-pool \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32.x-gke.xxx
```

**Monitor during upgrade:**
```bash
# Watch pod status
kubectl get pods -l role=coordinating -w

# Verify Elasticsearch connectivity
kubectl exec -it elasticsearch-master-0 -- curl -s "localhost:9200/_cluster/health"
```

### Phase 2: Upgrade Data Nodes (One by One)
```bash
# Before each data node upgrade, ensure cluster is green
kubectl exec -it elasticsearch-master-0 -- curl -s "localhost:9200/_cluster/health"

# Upgrade data node pool
gcloud container node-pools upgrade data-pool \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32.x-gke.xxx \
  --max-surge-upgrade=1 \
  --max-unavailable-upgrade=0
```

**Between each data node:**
```bash
# Wait for cluster to return to green
while true; do
  STATUS=$(kubectl exec -it elasticsearch-master-0 -- curl -s "localhost:9200/_cluster/health" | jq -r '.status')
  echo "Cluster status: $STATUS"
  if [ "$STATUS" = "green" ]; then
    break
  fi
  sleep 30
done
```

### Phase 3: Upgrade Master Nodes (Most Critical)
```bash
# Verify you have 3 healthy masters before starting
kubectl get pods -l role=master

# Upgrade master node pool (one at a time is crucial)
gcloud container node-pools upgrade master-pool \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32.x-gke.xxx \
  --max-surge-upgrade=1 \
  --max-unavailable-upgrade=0
```

**Critical monitoring for masters:**
```bash
# Check master election status
kubectl exec -it elasticsearch-master-0 -- curl -s "localhost:9200/_cat/master?v"

# Verify cluster can still accept writes
kubectl exec -it elasticsearch-master-0 -- curl -X POST "localhost:9200/test-index/_doc" -H 'Content-Type: application/json' -d'{"test": "connectivity", "timestamp": "'$(date)'"}'
```

## Post-Upgrade Steps

### 1. Re-enable Shard Allocation
```bash
kubectl exec -it elasticsearch-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "all"
  }
}'
```

### 2. Wait for Full Recovery
```bash
# Monitor shard allocation
watch 'kubectl exec -it elasticsearch-master-0 -- curl -s "localhost:9200/_cat/recovery?v&active_only=true"'

# Wait for green status
kubectl exec -it elasticsearch-master-0 -- curl -s "localhost:9200/_cluster/health?wait_for_status=green&timeout=10m"
```

### 3. Verification
```bash
# Verify all nodes are on new version
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion

# Check Elasticsearch cluster health
kubectl exec -it elasticsearch-master-0 -- curl -s "localhost:9200/_cluster/health?pretty"

# Verify all expected nodes are present
kubectl exec -it elasticsearch-master-0 -- curl -s "localhost:9200/_cat/nodes?v"

# Test functionality
kubectl exec -it elasticsearch-master-0 -- curl -s "localhost:9200/_cat/indices?v"
```

## Rollback Plan (if needed)

If issues arise:

```bash
# Emergency: Scale down problematic StatefulSet
kubectl scale statefulset elasticsearch-data --replicas=4

# Rollback node pool (if within rollback window)
gcloud container node-pools rollback data-pool \
  --cluster=your-cluster-name \
  --zone=your-zone

# Restore from snapshot if data corruption
curl -X POST "localhost:9200/_snapshot/gcs-backup/pre-upgrade-YYYYMMDD/_restore"
```

## Key Safety Considerations

1. **Never upgrade more than one master at a time** - This could break quorum
2. **Monitor PV attachment** - Regional PD-SSD should reattach automatically, but verify
3. **Check resource quotas** - Ensure surge capacity doesn't exceed limits
4. **Network policies** - Verify they don't block communication during node replacement
5. **Keep snapshots** - Don't delete pre-upgrade snapshots until fully verified

The entire process should take 2-4 hours depending on your data size and replication settings. Your regional PD-SSD volumes will automatically reattach to new nodes, preserving all data.
I'll walk you through a safe upgrade strategy for your Elasticsearch cluster on GKE. Given your multi-node-pool setup with StatefulSets, we need to be methodical to maintain both data integrity and availability.

## Pre-Upgrade Preparation

### 1. Backup Your Data
```bash
# Create a snapshot repository (if not already configured)
kubectl exec -it elasticsearch-master-0 -- curl -X PUT "localhost:9200/_snapshot/gcs-backup" -H 'Content-Type: application/json' -d'
{
  "type": "gcs",
  "settings": {
    "bucket": "your-backup-bucket",
    "base_path": "elasticsearch-snapshots"
  }
}'

# Create a full cluster snapshot
kubectl exec -it elasticsearch-master-0 -- curl -X PUT "localhost:9200/_snapshot/gcs-backup/pre-upgrade-$(date +%Y%m%d)" -H 'Content-Type: application/json' -d'
{
  "indices": "*",
  "include_global_state": true
}'
```

### 2. Verify Cluster Health
```bash
# Check cluster status
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"

# Verify all nodes are present
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cat/nodes?v"

# Check shard allocation
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cat/shards?v&s=index"
```

### 3. Disable Shard Allocation
```bash
kubectl exec -it elasticsearch-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'
```

## Node Pool Upgrade Strategy

### Phase 1: Upgrade Coordinating Nodes First
Since coordinating nodes don't hold data, they're safest to upgrade first.

```bash
# Upgrade coordinating node pool
gcloud container node-pools upgrade COORDINATING_POOL_NAME \
  --cluster=YOUR_CLUSTER_NAME \
  --zone=YOUR_ZONE \
  --node-version=1.30

# Wait for completion and verify
kubectl get nodes -l node-pool=coordinating-pool
```

### Phase 2: Upgrade Data Nodes (One at a Time)
```bash
# Get list of data node pools
gcloud container node-pools list --cluster=YOUR_CLUSTER_NAME --zone=YOUR_ZONE

# For each data node pool:
for pool in data-pool-1 data-pool-2 data-pool-3 data-pool-4 data-pool-5; do
  echo "Upgrading $pool..."
  
  # Upgrade the node pool
  gcloud container node-pools upgrade $pool \
    --cluster=YOUR_CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --node-version=1.30
  
  # Wait for the upgrade to complete
  echo "Waiting for $pool upgrade to complete..."
  while [[ $(gcloud container node-pools describe $pool --cluster=YOUR_CLUSTER_NAME --zone=YOUR_ZONE --format="value(status)") != "RUNNING" ]]; do
    sleep 30
  done
  
  # Verify cluster health before proceeding
  kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cluster/health?wait_for_status=yellow&timeout=5m"
  
  echo "$pool upgraded successfully"
  sleep 60  # Brief pause between upgrades
done
```

### Phase 3: Upgrade Master Nodes (One at a Time)
Master nodes require extra care due to quorum requirements.

```bash
# Upgrade master node pools one by one
for pool in master-pool-1 master-pool-2 master-pool-3; do
  echo "Upgrading master $pool..."
  
  # Upgrade the node pool
  gcloud container node-pools upgrade $pool \
    --cluster=YOUR_CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --node-version=1.30
  
  # Wait for upgrade completion
  while [[ $(gcloud container node-pools describe $pool --cluster=YOUR_CLUSTER_NAME --zone=YOUR_ZONE --format="value(status)") != "RUNNING" ]]; do
    sleep 30
  done
  
  # Verify cluster has master and is healthy
  kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cluster/health?wait_for_status=yellow&timeout=5m"
  
  # Ensure we have master quorum
  master_count=$(kubectl exec -it elasticsearch-master-0 -- curl -s -X GET "localhost:9200/_cat/nodes?h=node.role" | grep -c "m")
  if [[ $master_count -ge 2 ]]; then
    echo "Master quorum maintained: $master_count masters available"
  else
    echo "WARNING: Master quorum may be at risk!"
    exit 1
  fi
  
  sleep 120  # Longer pause for master stability
done
```

## Post-Upgrade Tasks

### 1. Re-enable Shard Allocation
```bash
kubectl exec -it elasticsearch-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "all"
  }
}'
```

### 2. Wait for Cluster Recovery
```bash
# Wait for green status
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cluster/health?wait_for_status=green&timeout=10m&pretty"

# Monitor shard recovery
watch 'kubectl exec -it elasticsearch-master-0 -- curl -s -X GET "localhost:9200/_cat/recovery?active_only&v"'
```

### 3. Final Verification
```bash
# Verify all nodes are on new Kubernetes version
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion

# Check Elasticsearch cluster status
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cat/nodes?v&h=name,node.role,version,master"

# Verify data integrity
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cat/indices?v"

# Test a sample query
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_search?size=1&pretty"
```

## Important Considerations

### Regional PD-SSD Behavior
- Your regional pd-ssd volumes will automatically reattach to new nodes
- StatefulSet pods will maintain their identity and storage
- No manual PV/PVC intervention needed

### Timing Expectations
- Coordinating nodes: 10-15 minutes per pool
- Data nodes: 15-25 minutes per pool (depends on data size)
- Master nodes: 15-20 minutes per pool

### Rollback Plan
If issues occur:
```bash
# Re-enable allocation first
kubectl exec -it elasticsearch-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{"persistent": {"cluster.routing.allocation.enable": "all"}}'

# Rollback node pool (if within rollback window)
gcloud container node-pools rollback POOL_NAME \
  --cluster=YOUR_CLUSTER_NAME \
  --zone=YOUR_ZONE
```

### Monitoring During Upgrade
```bash
# Monitor pod status
watch 'kubectl get pods -o wide'

# Monitor cluster health
watch 'kubectl exec -it elasticsearch-master-0 -- curl -s -X GET "localhost:9200/_cluster/health" | jq .'
```

This approach ensures zero data loss and minimal downtime by leveraging Elasticsearch's built-in resilience and GKE's rolling upgrade capabilities.
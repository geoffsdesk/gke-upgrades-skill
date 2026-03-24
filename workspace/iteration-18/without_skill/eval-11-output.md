I'll walk you through a safe upgrade strategy for your GKE Elasticsearch cluster. Given your setup with separate node pools, we can leverage rolling upgrades to maintain availability.

## Pre-Upgrade Preparation

### 1. Backup Your Data
```bash
# Create a snapshot repository (if not already configured)
curl -X PUT "localhost:9200/_snapshot/gcs_backup" -H 'Content-Type: application/json' -d'
{
  "type": "gcs",
  "settings": {
    "bucket": "your-backup-bucket",
    "base_path": "elasticsearch-snapshots"
  }
}'

# Create a pre-upgrade snapshot
curl -X PUT "localhost:9200/_snapshot/gcs_backup/pre-upgrade-$(date +%Y%m%d)" -H 'Content-Type: application/json' -d'
{
  "indices": "*",
  "ignore_unavailable": true,
  "include_global_state": true
}'
```

### 2. Verify Cluster Health
```bash
# Check cluster health
kubectl exec -it es-master-0 -- curl -s localhost:9200/_cluster/health

# Verify all nodes are present
kubectl exec -it es-master-0 -- curl -s localhost:9200/_cat/nodes?v

# Check for any ongoing operations
kubectl exec -it es-master-0 -- curl -s localhost:9200/_cat/recovery?active_only=true
```

### 3. Disable Shard Allocation (Temporary)
```bash
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'
```

## Upgrade Strategy: Coordinating → Data → Master

### Phase 1: Upgrade Coordinating Nodes

```bash
# Update the coordinating node pool
gcloud container node-pools upgrade coordinating-pool \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32

# Monitor the upgrade
kubectl get nodes -l node-pool=coordinating-pool
kubectl get pods -l component=elasticsearch-coordinating
```

Wait for coordinating nodes to be ready before proceeding.

### Phase 2: Upgrade Data Nodes (One by One)

```bash
# Get list of data node pools
kubectl get nodes -l node-pool=data-pool

# Upgrade data nodes with max-surge=1, max-unavailable=0 for safety
gcloud container node-pools update data-pool \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --max-surge=1 \
  --max-unavailable=0

gcloud container node-pools upgrade data-pool \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32
```

Monitor each data node upgrade:
```bash
# Watch pod status
kubectl get pods -l component=elasticsearch-data -w

# Monitor cluster health during upgrade
watch "kubectl exec -it es-master-0 -- curl -s localhost:9200/_cluster/health"
```

### Phase 3: Upgrade Master Nodes (Critical Phase)

```bash
# Ensure cluster is stable before master upgrade
kubectl exec -it es-master-0 -- curl -s localhost:9200/_cluster/health

# Upgrade master node pool
gcloud container node-pools upgrade master-pool \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32
```

**Critical**: Monitor master election during this phase:
```bash
# Watch master nodes
kubectl get pods -l component=elasticsearch-master -w

# Monitor cluster state
kubectl exec -it es-master-0 -- curl -s localhost:9200/_cat/master
```

## Post-Upgrade Steps

### 1. Re-enable Shard Allocation
```bash
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "all"
  }
}'
```

### 2. Verify Cluster Recovery
```bash
# Check cluster health
kubectl exec -it es-master-0 -- curl -s localhost:9200/_cluster/health

# Verify all shards are allocated
kubectl exec -it es-master-0 -- curl -s localhost:9200/_cat/shards?h=index,shard,prirep,state,node

# Check node versions
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion
```

### 3. Performance Validation
```bash
# Test indexing performance
kubectl exec -it es-master-0 -- curl -X POST "localhost:9200/test-index/_doc" -H 'Content-Type: application/json' -d'
{
  "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
  "message": "Post-upgrade test"
}'

# Test search performance
kubectl exec -it es-master-0 -- curl -s localhost:9200/_search?size=1
```

## Monitoring During Upgrade

Create a monitoring script:
```bash
#!/bin/bash
# monitor-upgrade.sh

while true; do
  echo "=== $(date) ==="
  echo "Cluster Health:"
  kubectl exec -it es-master-0 -- curl -s localhost:9200/_cluster/health | jq .
  
  echo "Node Status:"
  kubectl get nodes --no-headers | awk '{print $1, $2}'
  
  echo "Pod Status:"
  kubectl get pods -l app=elasticsearch --no-headers | awk '{print $1, $3}'
  
  echo "---"
  sleep 30
done
```

## Rollback Plan (If Needed)

If issues arise during master upgrade:

```bash
# Emergency: Scale down problematic pods
kubectl scale statefulset es-master --replicas=2

# Rollback node pool (if nodes are the issue)
gcloud container node-pools rollback master-pool \
  --cluster=your-cluster-name \
  --zone=your-zone
```

## Expected Downtime
- **Coordinating nodes**: ~5-10 minutes (no data loss, some client connection resets)
- **Data nodes**: ~15-30 minutes total (rolling upgrade, no downtime with proper replication)
- **Master nodes**: ~10-15 minutes (brief leadership transitions)

## Key Safety Notes

1. **Never upgrade all masters simultaneously**
2. **Keep shard allocation disabled during data node upgrades**
3. **Ensure cluster is GREEN before each phase**
4. **Your regional pd-ssd volumes will persist through the upgrade**
5. **Monitor master quorum (you need 2/3 masters available)**

Would you like me to elaborate on any specific phase or create more detailed monitoring scripts for your upgrade?
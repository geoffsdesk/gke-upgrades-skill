I'll walk you through a safe GKE upgrade strategy for your Elasticsearch cluster. Given your setup with separate node pools and regional pd-ssd, we can maintain availability throughout the process.

## Pre-Upgrade Preparation

### 1. Backup and Health Check
```bash
# Check cluster health
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"

# Disable shard allocation (prevents unnecessary shard movement)
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'

# Take a snapshot (if you have snapshot repository configured)
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_snapshot/backup/pre-upgrade-$(date +%Y%m%d)"
```

### 2. Document Current State
```bash
# Save current node pool configurations
gcloud container node-pools list --cluster=YOUR_CLUSTER_NAME --region=YOUR_REGION

# Save StatefulSet configurations
kubectl get statefulsets -o yaml > elasticsearch-statefulsets-backup.yaml
```

## Upgrade Strategy: Node Pool by Node Pool

### Phase 1: Upgrade Coordinating Nodes (Safest First)
```bash
# Upgrade coordinating node pool
gcloud container node-pools upgrade COORDINATING_POOL_NAME \
  --cluster=YOUR_CLUSTER_NAME \
  --region=YOUR_REGION \
  --node-version=1.32.x-gke.y
```

**Why coordinating nodes first?** They don't store data and have the least impact on cluster stability.

### Phase 2: Upgrade Master Nodes (One at a Time)
```bash
# Check Elasticsearch master nodes
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/master?v"

# Upgrade master node pool
gcloud container node-pools upgrade MASTER_POOL_NAME \
  --cluster=YOUR_CLUSTER_NAME \
  --region=YOUR_REGION \
  --node-version=1.32.x-gke.y
```

**Monitor between each master node restart:**
```bash
# Ensure master election is stable
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/master?v"
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"
```

### Phase 3: Upgrade Data Nodes (Most Critical)
```bash
# Before upgrading data nodes, ensure cluster is healthy
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?wait_for_status=green&timeout=30s"

# Upgrade data node pool
gcloud container node-pools upgrade DATA_POOL_NAME \
  --cluster=YOUR_CLUSTER_NAME \
  --region=YOUR_REGION \
  --node-version=1.32.x-gke.y
```

## Advanced: Rolling Upgrade with Manual Control

If you want more control, use this approach:

### 1. Upgrade with Max Surge/Unavailable Settings
```bash
# Configure upgrade strategy to minimize impact
gcloud container node-pools update DATA_POOL_NAME \
  --cluster=YOUR_CLUSTER_NAME \
  --region=YOUR_REGION \
  --max-surge=1 \
  --max-unavailable=0

# Then upgrade
gcloud container node-pools upgrade DATA_POOL_NAME \
  --cluster=YOUR_CLUSTER_NAME \
  --region=YOUR_REGION \
  --node-version=1.32.x-gke.y
```

### 2. Monitor Shard Relocation
```bash
# Monitor shard movement during upgrade
watch 'kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/shards?v" | grep -E "(RELOCATING|INITIALIZING|UNASSIGNED)"'
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

### 2. Wait for Cluster Recovery
```bash
# Wait for green status
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?wait_for_status=green&timeout=300s&pretty"

# Check all shards are active
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/shards?v" | grep -v STARTED | wc -l
```

### 3. Verify All Services
```bash
# Check all pods are running
kubectl get pods -l app=elasticsearch

# Verify Elasticsearch cluster
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/nodes?v"
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/stats?pretty"
```

## Emergency Rollback Plan

If issues arise:

```bash
# Rollback node pool (if within rollback window)
gcloud container node-pools rollback POOL_NAME \
  --cluster=YOUR_CLUSTER_NAME \
  --region=YOUR_REGION

# Or restore from snapshot
kubectl exec -it es-master-0 -- curl -X POST "localhost:9200/_snapshot/backup/pre-upgrade-YYYYMMDD/_restore"
```

## Key Monitoring Points

Throughout the upgrade, monitor:
- Elasticsearch cluster health status
- Pod readiness and restart counts
- PVC attachment status
- Network connectivity between nodes
- Resource utilization

The regional pd-ssd volumes will automatically reattach to new nodes, ensuring no data loss. The upgrade should take 30-60 minutes depending on your cluster size and Elasticsearch startup times.
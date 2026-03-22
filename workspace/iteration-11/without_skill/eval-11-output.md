I'll walk you through a safe GKE cluster upgrade strategy for your Elasticsearch deployment. Given your setup with multiple node pools and regional SSDs, we can achieve zero-downtime with careful planning.

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
# Ensure cluster is green and all shards are allocated
kubectl exec -it elasticsearch-master-0 -- curl -s "localhost:9200/_cluster/health?pretty"
kubectl exec -it elasticsearch-master-0 -- curl -s "localhost:9200/_cat/shards?v"
```

### 3. Disable Shard Allocation (Temporarily)
```bash
kubectl exec -it elasticsearch-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'
```

## Upgrade Strategy: Node Pool by Node Pool

### Phase 1: Upgrade Control Plane
```bash
# Upgrade the control plane first
gcloud container clusters upgrade CLUSTER_NAME \
    --master \
    --cluster-version=1.32.x \
    --zone=YOUR_ZONE
```

### Phase 2: Upgrade Coordinating Nodes (Lowest Risk)
```bash
# Upgrade coordinating node pool
gcloud container node-pools upgrade COORDINATING_POOL_NAME \
    --cluster=CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --node-version=1.32.x

# Monitor during upgrade
kubectl get nodes -l node-pool=coordinating
kubectl get pods -l component=elasticsearch-coordinating -o wide
```

### Phase 3: Upgrade Data Nodes (One at a Time)
```bash
# First, re-enable shard allocation
kubectl exec -it elasticsearch-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "all"
  }
}'

# Set replica count to ensure data safety
kubectl exec -it elasticsearch-master-0 -- curl -X PUT "localhost:9200/_all/_settings" -H 'Content-Type: application/json' -d'
{
  "index": {
    "number_of_replicas": 1
  }
}'

# Upgrade data node pool with surge settings for gradual rollout
gcloud container node-pools update DATA_POOL_NAME \
    --cluster=CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --max-surge=1 \
    --max-unavailable=0

gcloud container node-pools upgrade DATA_POOL_NAME \
    --cluster=CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --node-version=1.32.x
```

### Phase 4: Upgrade Master Nodes (Most Critical)
```bash
# Ensure cluster is stable before master upgrade
kubectl exec -it elasticsearch-master-0 -- curl -s "localhost:9200/_cluster/health?wait_for_status=green&timeout=300s"

# Upgrade master node pool (GKE will handle master quorum automatically)
gcloud container node-pools update MASTER_POOL_NAME \
    --cluster=CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --max-surge=1 \
    --max-unavailable=0

gcloud container node-pools upgrade MASTER_POOL_NAME \
    --cluster=CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --node-version=1.32.x
```

## Monitoring Script

Create this script to monitor throughout the upgrade:

```bash
#!/bin/bash
# monitor-es-upgrade.sh

echo "=== Elasticsearch Cluster Status ==="
kubectl exec -it elasticsearch-master-0 -- curl -s "localhost:9200/_cluster/health?pretty"

echo -e "\n=== Node Status ==="
kubectl get nodes -o wide

echo -e "\n=== Pod Status ==="
kubectl get pods -l app=elasticsearch -o wide

echo -e "\n=== Shard Status ==="
kubectl exec -it elasticsearch-master-0 -- curl -s "localhost:9200/_cat/shards?v" | head -20

echo -e "\n=== Unassigned Shards ==="
kubectl exec -it elasticsearch-master-0 -- curl -s "localhost:9200/_cat/shards?h=index,shard,prirep,state,unassigned.reason" | grep UNASSIGNED
```

## Post-Upgrade Verification

### 1. Verify Cluster Health
```bash
# Wait for green status
kubectl exec -it elasticsearch-master-0 -- curl -s "localhost:9200/_cluster/health?wait_for_status=green&timeout=600s&pretty"

# Check all nodes are visible
kubectl exec -it elasticsearch-master-0 -- curl -s "localhost:9200/_cat/nodes?v"

# Verify indices
kubectl exec -it elasticsearch-master-0 -- curl -s "localhost:9200/_cat/indices?v"
```

### 2. Performance Test
```bash
# Run a simple search to verify functionality
kubectl exec -it elasticsearch-master-0 -- curl -s "localhost:9200/_search?size=1&pretty"
```

### 3. Re-enable Full Allocation (if disabled)
```bash
kubectl exec -it elasticsearch-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "all"
  }
}'
```

## Key Safety Measures

1. **PV Safety**: Regional pd-ssd volumes will persist through node replacements
2. **Gradual Rollout**: Using max-surge=1, max-unavailable=0 ensures gradual replacement
3. **Order Matters**: Coordinating → Data → Masters minimizes risk
4. **Quorum Maintenance**: With 3 masters, you'll maintain quorum throughout
5. **Monitoring**: Run the monitoring script every few minutes during upgrade

## Rollback Plan

If issues arise:
```bash
# Rollback specific node pool
gcloud container node-pools rollback POOL_NAME \
    --cluster=CLUSTER_NAME \
    --zone=YOUR_ZONE

# Restore from snapshot if needed
curl -X POST "localhost:9200/_snapshot/gcs-backup/pre-upgrade-YYYYMMDD/_restore"
```

This approach should give you zero-downtime upgrade with your current architecture. The regional SSDs and multiple replicas provide data durability throughout the process.
I'll walk you through a safe GKE upgrade strategy for your Elasticsearch cluster. This approach minimizes risk by upgrading components incrementally while maintaining quorum and data availability.

## Pre-Upgrade Preparation

### 1. Backup and Health Check
```bash
# Check cluster health
kubectl get pods -l app=elasticsearch
kubectl logs -l app=elasticsearch-master --tail=50

# Verify Elasticsearch cluster health
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"

# Take snapshot backup
kubectl exec -it elasticsearch-master-0 -- curl -X PUT "localhost:9200/_snapshot/backup_repo/pre_upgrade_snapshot?wait_for_completion=true"
```

### 2. Disable Elasticsearch Shard Allocation
```bash
# Prevent shard rebalancing during upgrade
kubectl exec -it elasticsearch-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'
```

## Upgrade Strategy: Node Pool by Node Pool

### Phase 1: Upgrade Master Control Plane
```bash
# Upgrade control plane first (no downtime)
gcloud container clusters upgrade CLUSTER_NAME \
    --master \
    --cluster-version=1.30.x-gke.x \
    --zone=YOUR_ZONE
```

### Phase 2: Upgrade Coordinating Nodes (Lowest Risk)
```bash
# Get current node pool version
gcloud container node-pools describe coordinating-pool \
    --cluster=CLUSTER_NAME \
    --zone=YOUR_ZONE

# Upgrade coordinating node pool
gcloud container node-pools upgrade coordinating-pool \
    --cluster=CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --cluster-version=1.30.x-gke.x
```

**Monitor during upgrade:**
```bash
kubectl get pods -l app=elasticsearch-coordinating -w
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cluster/health"
```

### Phase 3: Upgrade Data Nodes (One by One)
This is the most critical phase. We'll upgrade one data node at a time.

```bash
# For each data node, cordon and drain gracefully
kubectl cordon NODE_NAME
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --force --grace-period=300

# Upgrade single node pool (if you have separate pools per data node)
# OR upgrade the entire data node pool with max-surge=1, max-unavailable=0
gcloud container node-pools upgrade data-pool \
    --cluster=CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --cluster-version=1.30.x-gke.x \
    --max-surge-upgrade=1 \
    --max-unavailable-upgrade=0
```

**Between each data node upgrade:**
```bash
# Wait for cluster to return to green
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cluster/health?wait_for_status=green&timeout=10m"

# Check shard allocation
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cat/shards?v"
```

### Phase 4: Upgrade Master Nodes (Most Critical)
Upgrade masters one at a time to maintain quorum (you have 3, so you can afford 1 down).

```bash
# Set max-unavailable to 1 to ensure quorum
gcloud container node-pools upgrade master-pool \
    --cluster=CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --cluster-version=1.30.x-gke.x \
    --max-surge-upgrade=1 \
    --max-unavailable-upgrade=1
```

**Monitor master upgrade closely:**
```bash
kubectl get pods -l app=elasticsearch-master -w
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cluster/stats?pretty"
```

## Post-Upgrade Tasks

### 1. Re-enable Shard Allocation
```bash
kubectl exec -it elasticsearch-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": null
  }
}'
```

### 2. Verify Cluster Health
```bash
# Wait for green status
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cluster/health?wait_for_status=green&timeout=15m&pretty"

# Check all nodes are visible
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cat/nodes?v"

# Verify shard distribution
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cat/shards?v&h=index,shard,prirep,state,node&s=index,shard"
```

### 3. Performance Verification
```bash
# Test indexing and search
kubectl exec -it elasticsearch-master-0 -- curl -X POST "localhost:9200/test-index/_doc" -H 'Content-Type: application/json' -d'{"test": "upgrade-verification", "timestamp": "'$(date)'"}'

kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/test-index/_search?pretty"
```

## Alternative: Blue-Green Approach (If Maximum Safety Required)

If you need zero-downtime and have the resources:

```bash
# Create new node pools with 1.30
gcloud container node-pools create master-pool-v130 \
    --cluster=CLUSTER_NAME \
    --machine-type=e2-standard-4 \
    --num-nodes=3 \
    --node-version=1.30.x-gke.x

# Gradually migrate Elasticsearch pods using node selectors
# Update StatefulSets to prefer new nodes
# Once all migrated, delete old node pools
```

## Monitoring Throughout the Process

```bash
# Watch pods continuously
watch kubectl get pods -l app=elasticsearch

# Monitor Elasticsearch logs
kubectl logs -f elasticsearch-master-0

# Check persistent volumes
kubectl get pv,pvc
```

## Rollback Plan

If issues occur:
```bash
# Rollback node pool (if within rollback window)
gcloud container node-pools rollback NODE_POOL_NAME \
    --cluster=CLUSTER_NAME \
    --zone=YOUR_ZONE

# Restore from snapshot if data corruption
kubectl exec -it elasticsearch-master-0 -- curl -X POST "localhost:9200/_snapshot/backup_repo/pre_upgrade_snapshot/_restore"
```

## Key Safety Points

1. **Never upgrade more than 1 master at a time** - maintain quorum
2. **Monitor shard allocation** between each data node upgrade
3. **Keep shard allocation disabled** until all nodes are upgraded
4. **Your regional pd-ssd PVs will persist** through node replacements
5. **Test the upgrade process in staging first**

The entire process should take 2-4 hours depending on your data size and replication settings. Your Elasticsearch cluster should remain available throughout with this approach.
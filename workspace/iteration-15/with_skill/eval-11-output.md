# Elasticsearch GKE Upgrade Plan: 1.31 → 1.32

This upgrade plan prioritizes Elasticsearch data safety and cluster availability during the GKE upgrade process.

## Pre-Upgrade Preparation

### 1. Elasticsearch Cluster Health Check
```bash
# Check cluster health
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"
# Verify all shards are active
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/shards?v&h=index,shard,prirep,state,unassigned.reason"

# Disable shard allocation (prevents rebalancing during upgrade)
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" \
  -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'
```

### 2. Backup Strategy
```bash
# Create snapshot repository (if not already configured)
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_snapshot/gcs-backup" \
  -H 'Content-Type: application/json' -d'
{
  "type": "gcs",
  "settings": {
    "bucket": "YOUR_BACKUP_BUCKET",
    "base_path": "elasticsearch-snapshots"
  }
}'

# Take full cluster snapshot
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_snapshot/gcs-backup/pre-upgrade-$(date +%Y%m%d)" \
  -H 'Content-Type: application/json' -d'
{
  "indices": "*",
  "ignore_unavailable": true,
  "include_global_state": true
}'
```

### 3. GKE Cluster Validation
```bash
# Check current versions and channel
gcloud container clusters describe YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --format="table(name, currentMasterVersion, releaseChannel.channel, nodePools[].name:label=POOL, nodePools[].version:label=VERSION)"

# Verify 1.32 is available in your release channel
gcloud container get-server-config --zone YOUR_ZONE \
  --format="yaml(channels)"

# Check for deprecated API usage
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
```

## Upgrade Strategy: Conservative Approach

Given Elasticsearch's sensitivity to node disruptions, we'll use **BLUE-GREEN upgrade strategy** with minimal concurrent disruptions.

### Step 1: Configure Node Pool Upgrade Settings

```bash
# Configure coordinating nodes (least critical) - upgrade first
gcloud container node-pools update es-coordinating-pool \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --strategy=BLUE_GREEN \
  --node-pool-soak-duration=1800s \
  --standard-rollout-policy=batch-node-count=1,batch-soak-duration=300s

# Configure data nodes (most critical) - conservative settings
gcloud container node-pools update es-data-pool \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --strategy=BLUE_GREEN \
  --node-pool-soak-duration=3600s \
  --standard-rollout-policy=batch-node-count=1,batch-soak-duration=600s

# Configure master nodes (critical for quorum) - very conservative
gcloud container node-pools update es-master-pool \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --strategy=BLUE_GREEN \
  --node-pool-soak-duration=3600s \
  --standard-rollout-policy=batch-node-count=1,batch-soak-duration=900s
```

### Step 2: Set Maintenance Window
```bash
# Set maintenance window during off-peak hours (example: Saturday 2-6 AM)
gcloud container clusters update YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --maintenance-window-start "2024-12-21T02:00:00Z" \
  --maintenance-window-end "2024-12-21T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## Upgrade Execution

### Step 1: Upgrade Control Plane
```bash
# Upgrade control plane to 1.32
gcloud container clusters upgrade YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --master \
  --cluster-version 1.32

# Monitor progress (control plane upgrade ~5-15 minutes)
gcloud container operations list --cluster YOUR_CLUSTER_NAME --zone YOUR_ZONE --limit=1

# Verify control plane version
gcloud container clusters describe YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --format="value(currentMasterVersion)"
```

### Step 2: Upgrade Node Pools in Sequence

**Phase 1: Coordinating Nodes (lowest risk)**
```bash
gcloud container node-pools upgrade es-coordinating-pool \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --cluster-version 1.32

# Monitor Elasticsearch cluster health during upgrade
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"
kubectl get pods -l role=coordinating -o wide
```

**Phase 2: Data Nodes (high risk - one at a time)**
```bash
# Before data node upgrade, ensure cluster is green
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?wait_for_status=green&timeout=5m"

gcloud container node-pools upgrade es-data-pool \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --cluster-version 1.32

# Monitor shard allocation during upgrade
watch 'kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/shards?v&h=index,shard,prirep,state,node" | grep -E "RELOCATING|INITIALIZING|UNASSIGNED"'
```

**Phase 3: Master Nodes (critical - maintain quorum)**
```bash
# Verify cluster health before master upgrade
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?wait_for_status=green&timeout=5m"

gcloud container node-pools upgrade es-master-pool \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --cluster-version 1.32

# Monitor master election during upgrade
kubectl get pods -l role=master -o wide
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/master?v"
```

## Critical Monitoring Commands

Use these during the upgrade to ensure Elasticsearch stability:

```bash
# Cluster health check
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"

# Active master verification
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/master?v"

# Shard allocation status
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/allocation?v"

# Node status
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/nodes?v&h=name,role,master,cpu,ram.percent,disk.used_percent"

# Check for red/yellow indices
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/indices?v&health=red"
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/indices?v&health=yellow"
```

## Post-Upgrade Recovery

### 1. Re-enable Shard Allocation
```bash
# Re-enable full shard allocation after all upgrades complete
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" \
  -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "all"
  }
}'

# Wait for cluster to rebalance
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?wait_for_status=green&timeout=10m"
```

### 2. Validation Checklist
```bash
# ✓ All nodes upgraded
gcloud container node-pools list --cluster YOUR_CLUSTER_NAME --zone YOUR_ZONE

# ✓ All pods running
kubectl get pods -o wide | grep -E "es-master|es-data|es-coord"

# ✓ Elasticsearch cluster green
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"

# ✓ All shards active
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/shards?v" | grep -c STARTED

# ✓ No unassigned shards
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/shards?v" | grep UNASSIGNED | wc -l
```

## Emergency Rollback Plan

If Elasticsearch cluster becomes unhealthy during upgrade:

### 1. Immediate Actions
```bash
# Cancel ongoing node pool upgrade
gcloud container operations list --cluster YOUR_CLUSTER_NAME --zone YOUR_ZONE
# Note the operation ID and cancel if needed

# Re-enable shard allocation if disabled
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" \
  -H 'Content-Type: application/json' -d'{"persistent": {"cluster.routing.allocation.enable": "all"}}'
```

### 2. Restore from Snapshot (if data loss)
```bash
# List available snapshots
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_snapshot/gcs-backup/_all?pretty"

# Restore from pre-upgrade snapshot
kubectl exec -it es-master-0 -- curl -X POST "localhost:9200/_snapshot/gcs-backup/pre-upgrade-YYYYMMDD/_restore" \
  -H 'Content-Type: application/json' -d'{"indices": "*", "ignore_unavailable": true}'
```

## Key Elasticsearch-Specific Considerations

1. **Regional PD-SSD is ideal** - provides durability across zones, reduces PV attachment issues during node migration
2. **Blue-green strategy chosen** - avoids local SSD data loss, provides rollback path, worth the 2x resource cost for data safety
3. **Conservative batch sizes** - Single-node batches prevent multiple simultaneous disruptions to Elasticsearch quorum
4. **Shard allocation disabled** - Prevents unnecessary shard movement during node transitions
5. **Extended soak periods** - Allows time to validate Elasticsearch stability before proceeding

## Timeline Expectations

- **Control plane upgrade**: 10-15 minutes
- **Coordinating nodes** (2 nodes): ~45 minutes (includes soak time)
- **Data nodes** (5 nodes): ~3 hours (includes soak time)  
- **Master nodes** (3 nodes): ~2 hours (includes soak time)
- **Total duration**: ~6 hours

The extended timeline prioritizes data safety over speed. For a production Elasticsearch cluster, this conservative approach minimizes risk of data loss or cluster split-brain scenarios.
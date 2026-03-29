I'll walk you through a safe GKE cluster upgrade strategy for your Elasticsearch setup. Given your multi-node pool architecture, we'll use a rolling approach to maintain availability.

## Pre-Upgrade Preparation

### 1. Backup and Health Checks
```bash
# Check cluster health
kubectl get nodes
kubectl get pods -n <elasticsearch-namespace>

# Verify Elasticsearch cluster health
curl -X GET "http://<es-endpoint>:9200/_cluster/health?pretty"
curl -X GET "http://<es-endpoint>:9200/_cat/nodes?v"

# Ensure all shards are allocated
curl -X GET "http://<es-endpoint>:9200/_cat/shards?v&h=index,shard,prirep,state,unassigned.reason"
```

### 2. Disable Shard Allocation (Temporary)
```bash
# Disable automatic shard reallocation during upgrade
curl -X PUT "http://<es-endpoint>:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'
```

### 3. Create Snapshots
```bash
# Create a snapshot before upgrade
curl -X PUT "http://<es-endpoint>:9200/_snapshot/backup-repo/pre-upgrade-snapshot?wait_for_completion=true"
```

## Upgrade Strategy: Node Pool by Node Pool

### Phase 1: Upgrade Coordinating Nodes First
Coordinating nodes are stateless and safest to upgrade first.

```bash
# Get current node pool versions
gcloud container node-pools list --cluster=<cluster-name> --zone=<zone>

# Upgrade coordinating node pool
gcloud container node-pools upgrade <coordinating-node-pool> \
  --cluster=<cluster-name> \
  --zone=<zone> \
  --node-version=1.32.x-gke.xxxx
```

**Monitor during upgrade:**
```bash
# Watch pod redistribution
kubectl get pods -n <elasticsearch-namespace> -o wide --watch

# Check ES cluster remains accessible
curl -X GET "http://<es-endpoint>:9200/_cluster/health"
```

### Phase 2: Upgrade Master Nodes
Upgrade master nodes one at a time to maintain quorum.

```bash
# First, check master node distribution
kubectl get pods -l role=master -o wide

# Upgrade master node pool
gcloud container node-pools upgrade <master-node-pool> \
  --cluster=<cluster-name> \
  --zone=<zone> \
  --node-version=1.32.x-gke.xxxx \
  --max-surge=1 \
  --max-unavailable=0
```

**Critical monitoring:**
```bash
# Ensure master quorum is maintained (should always have 2+ masters)
curl -X GET "http://<es-endpoint>:9200/_cat/master?v"
curl -X GET "http://<es-endpoint>:9200/_cat/nodes?v&h=name,master"

# Check cluster state
curl -X GET "http://<es-endpoint>:9200/_cluster/health?level=cluster&pretty"
```

### Phase 3: Upgrade Data Nodes (Most Critical)
Data nodes require the most careful approach due to persistent volumes.

```bash
# Before starting, verify all shards are healthy
curl -X GET "http://<es-endpoint>:9200/_cat/allocation?v"

# Upgrade data node pool with conservative settings
gcloud container node-pools upgrade <data-node-pool> \
  --cluster=<cluster-name> \
  --zone=<zone> \
  --node-version=1.32.x-gke.xxxx \
  --max-surge=0 \
  --max-unavailable=1
```

**Per-node monitoring during data node upgrade:**
```bash
# Watch for pod scheduling on new nodes
kubectl get pods -n <elasticsearch-namespace> -l role=data -o wide

# Monitor shard recovery
curl -X GET "http://<es-endpoint>:9200/_recovery?active_only=true&pretty"

# Check for unassigned shards
curl -X GET "http://<es-endpoint>:9200/_cat/shards?v&h=index,shard,prirep,state,node&s=state"
```

### Phase 4: Upgrade Control Plane
```bash
# Upgrade the GKE control plane
gcloud container clusters upgrade <cluster-name> \
  --master \
  --cluster-version=1.32.x-gke.xxxx \
  --zone=<zone>
```

## Post-Upgrade Recovery

### 1. Re-enable Shard Allocation
```bash
# Re-enable full shard allocation
curl -X PUT "http://<es-endpoint>:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "all"
  }
}'
```

### 2. Verify Complete Recovery
```bash
# Wait for green cluster status
curl -X GET "http://<es-endpoint>:9200/_cluster/health?wait_for_status=green&timeout=300s"

# Verify all nodes are present
curl -X GET "http://<es-endpoint>:9200/_cat/nodes?v"

# Check shard distribution
curl -X GET "http://<es-endpoint>:9200/_cat/allocation?v"
```

## Emergency Rollback Procedure

If issues arise:

```bash
# Quick rollback of a node pool
gcloud container node-pools rollback <node-pool-name> \
  --cluster=<cluster-name> \
  --zone=<zone>

# Re-disable shard allocation if needed
curl -X PUT "http://<es-endpoint>:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'

# Restore from snapshot if necessary
curl -X POST "http://<es-endpoint>:9200/_snapshot/backup-repo/pre-upgrade-snapshot/_restore"
```

## Key Monitoring Points

Throughout the upgrade, monitor:
- Elasticsearch cluster health status
- Master node quorum (always ≥2)
- Shard allocation and recovery progress
- PV attachment status
- Application connectivity

## Expected Timeline
- Coordinating nodes: 10-15 minutes
- Master nodes: 15-20 minutes  
- Data nodes: 30-45 minutes (varies by data volume)
- Control plane: 10-15 minutes

The regional pd-ssd volumes will automatically reattach to new nodes, but allow extra time for large data sets to sync and recover.

Would you like me to elaborate on any specific phase or provide additional monitoring commands?
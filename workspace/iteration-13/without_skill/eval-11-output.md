I'll walk you through a zero-downtime upgrade strategy for your Elasticsearch cluster on GKE. This approach prioritizes data safety and availability.

## Pre-Upgrade Preparation

### 1. Backup and Validation
```bash
# Create a snapshot repository (if not already configured)
PUT _snapshot/gcs-backup
{
  "type": "gcs",
  "settings": {
    "bucket": "your-backup-bucket",
    "base_path": "elasticsearch-snapshots"
  }
}

# Take a full cluster snapshot
PUT _snapshot/gcs-backup/pre-upgrade-snapshot
{
  "indices": "*",
  "ignore_unavailable": true,
  "include_global_state": true
}

# Verify cluster health
GET _cluster/health
GET _cat/nodes?v
GET _cat/indices?v
```

### 2. Disable Shard Allocation
```bash
# Temporarily disable shard reallocation
PUT _cluster/settings
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}
```

## Upgrade Strategy: Rolling Update by Node Pool

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
  --node-version=1.32.x
```

**Wait for coordinating nodes to be healthy before proceeding.**

### Phase 2: Upgrade Data Nodes (One at a Time)
```bash
# List data node pool instances
kubectl get nodes -l node-pool=data-pool

# Upgrade data nodes with surge settings to minimize disruption
gcloud container node-pools update data-pool \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --max-surge-upgrade=1 \
  --max-unavailable-upgrade=0

gcloud container node-pools upgrade data-pool \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32.x
```

**Monitor after each data node upgrade:**
```bash
# Check cluster health after each node
GET _cluster/health
GET _cat/recovery?v

# Ensure no relocating shards before next node
GET _cat/shards?v | grep RELOCATING
```

### Phase 3: Upgrade Master Nodes (Most Critical)
```bash
# Upgrade master nodes with minimal disruption
gcloud container node-pools update master-pool \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --max-surge-upgrade=1 \
  --max-unavailable-upgrade=0

gcloud container node-pools upgrade master-pool \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32.x
```

## Post-Upgrade Validation

### 1. Re-enable Shard Allocation
```bash
# Re-enable full shard allocation
PUT _cluster/settings
{
  "persistent": {
    "cluster.routing.allocation.enable": "all"
  }
}
```

### 2. Comprehensive Health Check
```bash
# Verify cluster state
GET _cluster/health
GET _cat/nodes?v
GET _cat/indices?v&health=red
GET _cluster/stats

# Check for any issues
GET _cat/pending_tasks?v
GET _cat/thread_pool/write?v&h=node_name,active,queue,rejected
```

## Monitoring Throughout the Process

### Key Metrics to Watch
```bash
# Continuous monitoring commands
watch "kubectl get pods -o wide | grep elasticsearch"
watch "curl -s 'http://your-es-service:9200/_cat/nodes?v'"
watch "curl -s 'http://your-es-service:9200/_cluster/health?pretty'"
```

### StatefulSet-Specific Considerations
```yaml
# Ensure your StatefulSet has proper pod disruption budget
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-master-pdb
spec:
  minAvailable: 2  # For 3 master nodes
  selector:
    matchLabels:
      app: elasticsearch-master
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-data-pdb
spec:
  minAvailable: 4  # For 5 data nodes
  selector:
    matchLabels:
      app: elasticsearch-data
```

## Emergency Rollback Plan

If issues arise:
```bash
# Quick rollback command for each node pool
gcloud container node-pools rollback [NODE_POOL_NAME] \
  --cluster=your-cluster-name \
  --zone=your-zone

# Restore from snapshot if data corruption occurs
POST _snapshot/gcs-backup/pre-upgrade-snapshot/_restore
{
  "indices": "*",
  "ignore_unavailable": true,
  "include_global_state": true
}
```

## Critical Success Factors

1. **Timing**: Perform during low-traffic periods
2. **Patience**: Wait for green cluster status between each phase
3. **Monitoring**: Keep multiple terminal windows open for real-time monitoring
4. **Communication**: Inform stakeholders about the maintenance window
5. **Validation**: Test application connectivity after each phase

## Expected Timeline
- Coordinating nodes: 10-15 minutes
- Data nodes: 45-60 minutes (depending on data volume)
- Master nodes: 15-20 minutes
- **Total**: 70-95 minutes

The regional pd-ssd volumes will automatically reattach to new nodes, and StatefulSets will maintain pod identity throughout the upgrade process.
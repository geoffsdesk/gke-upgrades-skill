I'll walk you through a safe GKE cluster upgrade strategy for your Elasticsearch setup. Given your multi-node pool architecture, we'll use a rolling upgrade approach to maintain availability.

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

# Create a pre-upgrade snapshot
curl -X PUT "localhost:9200/_snapshot/gcs-backup/pre-upgrade-$(date +%Y%m%d)" -H 'Content-Type: application/json' -d'
{
  "indices": "*",
  "ignore_unavailable": true,
  "include_global_state": true
}'
```

### 2. Verify Cluster Health
```bash
# Check cluster health
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health?pretty"

# Verify all nodes are present
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/nodes?v"

# Check shard allocation
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/shards?v&h=index,shard,prirep,state,node"
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

## Upgrade Strategy

### Phase 1: Upgrade Coordinating Nodes First
Coordinating nodes are stateless and safest to upgrade first.

```bash
# Get current node pool version
gcloud container node-pools describe coordinating-pool \
  --cluster=your-cluster-name \
  --zone=your-zone

# Upgrade the coordinating node pool
gcloud container node-pools upgrade coordinating-pool \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32.x-gke.y
```

Monitor the upgrade:
```bash
# Watch pod status during upgrade
kubectl get pods -l role=coordinating -w

# Verify coordinating nodes are healthy
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/nodes?v&h=name,node.role,version"
```

### Phase 2: Upgrade Data Nodes
Data nodes require careful handling due to StatefulSet nature.

```bash
# First, ensure cluster is stable
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health?wait_for_status=yellow&timeout=30s"

# Upgrade data node pool
gcloud container node-pools upgrade data-pool \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32.x-gke.y
```

Monitor data node upgrades carefully:
```bash
# Watch StatefulSet rollout
kubectl rollout status statefulset/es-data

# Check shard status during upgrade
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/shards?v&h=index,shard,prirep,state,node" | grep -E "(RELOCATING|INITIALIZING|UNASSIGNED)"
```

### Phase 3: Upgrade Master Nodes (Most Critical)
Master nodes require the most careful approach.

```bash
# Verify cluster stability before master upgrade
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health?pretty"

# Check master election stability
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/master?v"

# Upgrade master node pool
gcloud container node-pools upgrade master-pool \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32.x-gke.y
```

Monitor master upgrades closely:
```bash
# Watch master StatefulSet
kubectl rollout status statefulset/es-master

# Monitor master elections
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/master?v"

# Check cluster state
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/state/master_node?pretty"
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
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health?wait_for_status=green&timeout=10m&pretty"

# Verify all shards are allocated
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/shards?v" | grep -c UNASSIGNED
```

### 3. Final Validation
```bash
# Verify all nodes are on new Kubernetes version
kubectl get nodes -o wide

# Check Elasticsearch cluster composition
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/nodes?v&h=name,node.role,version,ip"

# Test indexing and searching
kubectl exec -it es-master-0 -- curl -X POST "localhost:9200/test-upgrade/_doc" -H 'Content-Type: application/json' -d'{"timestamp": "'$(date)'", "test": "post-upgrade"}'

kubectl exec -it es-master-0 -- curl -s "localhost:9200/test-upgrade/_search?pretty"
```

## Monitoring During Upgrade

Create a monitoring script to run during the upgrade:

```bash
#!/bin/bash
# monitor-upgrade.sh

while true; do
  echo "=== $(date) ==="
  
  # Cluster health
  kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health" | jq '.status, .number_of_nodes, .active_shards, .relocating_shards, .unassigned_shards'
  
  # Node status
  echo "Kubernetes nodes ready:"
  kubectl get nodes --no-headers | grep -c " Ready "
  
  # Pod status
  echo "ES pods running:"
  kubectl get pods -l app=elasticsearch --no-headers | grep -c " Running "
  
  echo "---"
  sleep 30
done
```

## Rollback Strategy

If issues arise, you can rollback:

```bash
# Rollback node pool (if upgrade fails)
gcloud container node-pools rollback <pool-name> \
  --cluster=your-cluster-name \
  --zone=your-zone

# If data corruption, restore from snapshot
curl -X POST "localhost:9200/_snapshot/gcs-backup/pre-upgrade-YYYYMMDD/_restore"
```

## Key Considerations

1. **Timing**: Perform during maintenance windows
2. **PodDisruptionBudgets**: Ensure they're properly configured for your StatefulSets
3. **Resource Monitoring**: Watch for memory/CPU spikes during upgrade
4. **Network Policies**: Verify they don't interfere with pod rescheduling
5. **Storage**: Regional PD-SSD will maintain data across zone failures

This approach minimizes downtime by upgrading stateless nodes first, then carefully handling stateful components while maintaining quorum and data integrity.
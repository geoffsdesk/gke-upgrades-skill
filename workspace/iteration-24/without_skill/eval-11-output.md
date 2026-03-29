I'll walk you through a safe GKE cluster upgrade strategy that maintains your Elasticsearch cluster availability and data integrity.

## Pre-Upgrade Preparation

### 1. Backup Strategy
```bash
# Create a snapshot repository (if not already configured)
curl -X PUT "elasticsearch-service:9200/_snapshot/gcs-backup" -H 'Content-Type: application/json' -d'
{
  "type": "gcs",
  "settings": {
    "bucket": "your-backup-bucket",
    "base_path": "elasticsearch-snapshots"
  }
}'

# Create a full cluster snapshot
curl -X PUT "elasticsearch-service:9200/_snapshot/gcs-backup/pre-upgrade-$(date +%Y%m%d)" -H 'Content-Type: application/json' -d'
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

# Verify all shards are allocated
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/shards?v&h=index,shard,prirep,state,unassigned.reason"

# Check node roles and status
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/nodes?v&h=name,node.role,master"
```

## Upgrade Strategy: Rolling Node Pool Upgrade

### Phase 1: Upgrade Coordinating Nodes (Least Disruptive)

```bash
# Disable shard allocation temporarily
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'

# Upgrade coordinating node pool
gcloud container node-pools upgrade coordinating-pool \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32 \
  --max-surge=1 \
  --max-unavailable=0

# Re-enable shard allocation
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "all"
  }
}'
```

### Phase 2: Upgrade Master Nodes (One at a Time)

```bash
# Set discovery.zen.minimum_master_nodes to 2 (for 3-node master setup)
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "discovery.zen.minimum_master_nodes": "2"
  }
}'

# For each master node, cordon and drain carefully
for i in 0 1 2; do
  echo "Upgrading master node $i"
  
  # Get the node name
  NODE_NAME=$(kubectl get pod es-master-$i -o jsonpath='{.spec.nodeName}')
  
  # Cordon the node
  kubectl cordon $NODE_NAME
  
  # Gracefully shutdown the ES node
  kubectl exec es-master-$i -- curl -X POST "localhost:9200/_cluster/nodes/_local/_shutdown"
  
  # Delete the pod (StatefulSet will recreate)
  kubectl delete pod es-master-$i
  
  # Upgrade the node
  gcloud container node-pools upgrade master-pool \
    --cluster=your-cluster-name \
    --zone=your-zone \
    --node-version=1.32 \
    --max-surge=0 \
    --max-unavailable=1
  
  # Uncordon and wait for pod to be ready
  kubectl uncordon $NODE_NAME
  kubectl wait --for=condition=ready pod/es-master-$i --timeout=300s
  
  # Verify cluster health before proceeding
  kubectl exec -it es-master-$i -- curl -s "localhost:9200/_cluster/health?wait_for_status=green&timeout=300s"
  
  sleep 60
done
```

### Phase 3: Upgrade Data Nodes (Most Critical)

```bash
# Increase recovery settings for faster rebalancing
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.cluster_concurrent_rebalance": "4",
    "cluster.routing.allocation.node_concurrent_recoveries": "4",
    "indices.recovery.max_bytes_per_sec": "100mb"
  }
}'

# Upgrade data nodes one by one
for i in 0 1 2 3 4; do
  echo "Upgrading data node $i"
  
  # Disable shard allocation
  kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
  {
    "persistent": {
      "cluster.routing.allocation.enable": "primaries"
    }
  }'
  
  # Perform synced flush
  kubectl exec -it es-master-0 -- curl -X POST "localhost:9200/_flush/synced"
  
  # Get node name and cordon
  NODE_NAME=$(kubectl get pod es-data-$i -o jsonpath='{.spec.nodeName}')
  kubectl cordon $NODE_NAME
  
  # Graceful shutdown
  kubectl exec es-data-$i -- curl -X POST "localhost:9200/_cluster/nodes/_local/_shutdown"
  
  # Delete pod
  kubectl delete pod es-data-$i
  
  # Upgrade the node pool (one node at a time)
  gcloud container node-pools upgrade data-pool \
    --cluster=your-cluster-name \
    --zone=your-zone \
    --node-version=1.32 \
    --max-surge=0 \
    --max-unavailable=1
  
  # Wait for pod to be ready
  kubectl wait --for=condition=ready pod/es-data-$i --timeout=600s
  
  # Re-enable allocation
  kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
  {
    "persistent": {
      "cluster.routing.allocation.enable": "all"
    }
  }'
  
  # Wait for cluster to be green before next node
  kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health?wait_for_status=green&timeout=1800s"
  
  echo "Data node $i upgrade complete, waiting before next node..."
  sleep 120
done
```

## Post-Upgrade Verification

### 1. Upgrade Control Plane
```bash
# Finally upgrade the control plane
gcloud container clusters upgrade your-cluster-name \
  --master \
  --cluster-version=1.32 \
  --zone=your-zone
```

### 2. Reset Cluster Settings
```bash
# Reset recovery settings to defaults
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.cluster_concurrent_rebalance": null,
    "cluster.routing.allocation.node_concurrent_recoveries": null,
    "indices.recovery.max_bytes_per_sec": null,
    "discovery.zen.minimum_master_nodes": null
  }
}'
```

### 3. Final Health Checks
```bash
# Comprehensive health check
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health?pretty"
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/nodes?v"
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/indices?v"

# Verify all PVs are still attached
kubectl get pv,pvc -o wide
```

## Monitoring During Upgrade

```bash
# Monitor in separate terminals
watch kubectl get pods -o wide
watch kubectl get nodes
kubectl exec -it es-master-0 -- watch curl -s "localhost:9200/_cat/health?v"
```

## Rollback Plan

If issues arise:

```bash
# Emergency snapshot restore (if needed)
curl -X POST "elasticsearch-service:9200/_snapshot/gcs-backup/pre-upgrade-$(date +%Y%m%d)/_restore"

# Node pool rollback
gcloud container node-pools rollback POOL_NAME \
  --cluster=your-cluster-name \
  --zone=your-zone
```

## Key Points

1. **Order matters**: Coordinating → Master → Data nodes
2. **One node at a time** for data nodes to prevent data loss
3. **Monitor cluster health** between each node upgrade
4. **PVs are preserved** since they're regional persistent disks
5. **Total downtime**: Minimal (seconds per coordinating/master node restart)
6. **Expected duration**: 2-4 hours depending on data size and rebalancing

This approach ensures zero data loss and minimal service disruption during the upgrade process.
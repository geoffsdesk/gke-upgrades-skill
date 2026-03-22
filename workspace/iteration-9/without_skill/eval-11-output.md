I'll walk you through a safe GKE cluster upgrade strategy for your Elasticsearch setup. Given your multi-node pool architecture, we'll use a rolling approach to maintain availability.

## Pre-Upgrade Preparation

### 1. Backup Your Data
```bash
# Create a snapshot repository (if not already configured)
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_snapshot/gcs-backup" -H 'Content-Type: application/json' -d'
{
  "type": "gcs",
  "settings": {
    "bucket": "your-backup-bucket"
  }
}'

# Create a snapshot
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_snapshot/gcs-backup/pre-upgrade-$(date +%Y%m%d)" -H 'Content-Type: application/json' -d'
{
  "indices": "*",
  "ignore_unavailable": true,
  "include_global_state": false
}'
```

### 2. Verify Cluster Health
```bash
# Check ES cluster status
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health?pretty"

# Ensure all shards are allocated
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/shards?h=index,shard,prirep,state,node&s=index"
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
```bash
# Get current node pool versions
kubectl get nodes -l node-pool=coordinating-pool -o wide

# Upgrade coordinating node pool
gcloud container node-pools upgrade coordinating-pool \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32.x-gke.xxxx

# Wait for completion and verify
kubectl get nodes -l node-pool=coordinating-pool
```

### Phase 2: Upgrade Data Nodes (One by One)
```bash
# List data node pools
kubectl get nodes -l node-pool=data-pool

# For each data node, cordon and drain safely
for node in $(kubectl get nodes -l node-pool=data-pool -o name); do
  echo "Processing $node"
  
  # Cordon the node
  kubectl cordon $node
  
  # Wait for ES to rebalance (check cluster health)
  kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health?wait_for_status=green&timeout=300s"
  
  # Drain the node (this will trigger pod rescheduling)
  kubectl drain $node --ignore-daemonsets --delete-emptydir-data --force --grace-period=300
  
  # Wait for ES pod to be rescheduled and ready
  kubectl wait --for=condition=ready pod -l component=data --timeout=600s
  
  # Verify cluster health before proceeding
  kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health?pretty"
done

# Upgrade the data node pool
gcloud container node-pools upgrade data-pool \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32.x-gke.xxxx
```

### Phase 3: Upgrade Master Nodes (Most Critical)
```bash
# Re-enable shard allocation before master upgrade
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "all"
  }
}'

# Wait for green status
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health?wait_for_status=green&timeout=300s"

# Upgrade master nodes one at a time
for i in 0 1 2; do
  echo "Upgrading es-master-$i"
  
  # Scale down the specific master pod
  kubectl patch statefulset es-master --type='merge' -p='{"spec":{"replicas":2}}'
  kubectl delete pod es-master-$i --grace-period=60
  
  # Wait for cluster to stabilize with 2 masters
  sleep 60
  
  # Scale back up
  kubectl patch statefulset es-master --type='merge' -p='{"spec":{"replicas":3}}'
  
  # Wait for pod to be ready
  kubectl wait --for=condition=ready pod/es-master-$i --timeout=600s
  
  # Verify cluster health
  kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health?pretty"
  
  # Wait between master node upgrades
  sleep 120
done

# Upgrade master node pool
gcloud container node-pools upgrade master-pool \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32.x-gke.xxxx
```

### Phase 4: Upgrade Control Plane
```bash
# Finally upgrade the control plane
gcloud container clusters upgrade your-cluster-name \
  --master \
  --zone=your-zone \
  --cluster-version=1.32.x-gke.xxxx
```

## Post-Upgrade Validation

### 1. Verify All Components
```bash
# Check node versions
kubectl get nodes -o wide

# Check pod status
kubectl get pods -o wide

# Verify ES cluster health
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health?pretty"

# Check all nodes are visible to ES
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/nodes?v"
```

### 2. Re-enable Full Shard Allocation
```bash
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "all"
  }
}'
```

### 3. Performance Test
```bash
# Run a simple indexing test
kubectl exec -it es-master-0 -- curl -X POST "localhost:9200/test-index/_doc" -H 'Content-Type: application/json' -d'
{
  "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)'",
  "message": "upgrade test"
}'

# Test search
kubectl exec -it es-master-0 -- curl -s "localhost:9200/test-index/_search?pretty"
```

## Rollback Plan

If issues arise:

```bash
# 1. Check snapshot status
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_snapshot/gcs-backup/pre-upgrade-$(date +%Y%m%d)"

# 2. If needed, restore from snapshot
kubectl exec -it es-master-0 -- curl -X POST "localhost:9200/_snapshot/gcs-backup/pre-upgrade-$(date +%Y%m%d)/_restore"

# 3. Downgrade node pools if necessary
gcloud container node-pools upgrade pool-name \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.31.x-gke.xxxx
```

## Key Considerations

- **Timing**: Plan for a 2-4 hour maintenance window
- **Monitoring**: Keep ES monitoring dashboards open throughout
- **Regional PD**: Your regional pd-ssd volumes will persist through node replacements
- **Master Quorum**: Never upgrade more than one master node simultaneously
- **Data Safety**: The regional PVs ensure data persistence even if nodes are replaced

This approach minimizes downtime by maintaining quorum and avoiding simultaneous disruption of critical components.
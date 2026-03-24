I'll walk you through a comprehensive upgrade strategy for your GKE Elasticsearch cluster. Given your setup with separate node pools, we can perform a rolling upgrade to maintain availability.

## Pre-Upgrade Preparation

### 1. Backup and Validation
```bash
# Create Elasticsearch snapshot
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_snapshot/my-backup/pre-upgrade-snapshot?wait_for_completion=true"

# Verify cluster health
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health"

# Document current state
kubectl get nodes --show-labels
kubectl get pods -o wide
kubectl get pvc
```

### 2. Disable Shard Allocation
```bash
# Temporarily disable shard allocation to prevent rebalancing during upgrade
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H "Content-Type: application/json" -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'
```

## Upgrade Strategy: Node Pool by Node Pool

### Phase 1: Upgrade Coordinating Nodes First
Coordinating nodes are stateless and safest to start with.

```bash
# Upgrade coordinating node pool
gcloud container node-pools upgrade coordinating-pool \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32 \
  --max-surge-upgrade=1 \
  --max-unavailable-upgrade=0

# Monitor the upgrade
kubectl get nodes -l node-pool=coordinating-pool
kubectl get pods -l role=coordinating -o wide
```

### Phase 2: Upgrade Data Nodes (Most Critical)
Data nodes require careful handling due to persistent volumes.

```bash
# For each data node, cordon and drain gracefully
for node in $(kubectl get nodes -l node-pool=data-pool -o name); do
  kubectl cordon $node
  
  # Get the pod running on this node
  POD=$(kubectl get pods -l role=data -o wide | grep $(basename $node) | awk '{print $1}')
  
  # Gracefully stop Elasticsearch on this node
  kubectl exec $POD -- curl -X POST "localhost:9200/_cluster/nodes/_local/_shutdown"
  
  # Wait for pod to terminate gracefully
  kubectl delete pod $POD --grace-period=300
  
  # Drain the node
  kubectl drain $node --ignore-daemonsets --delete-emptydir-data --force --grace-period=300
done

# Upgrade data node pool
gcloud container node-pools upgrade data-pool \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32 \
  --max-surge-upgrade=1 \
  --max-unavailable-upgrade=1

# Monitor data pod recovery
kubectl get pods -l role=data -o wide
kubectl get pvc  # Verify PVCs reattached correctly
```

### Phase 3: Upgrade Master Nodes (Most Delicate)
Master nodes maintain cluster state and require sequential upgrade.

```bash
# Upgrade master nodes one by one
gcloud container node-pools upgrade master-pool \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32 \
  --max-surge-upgrade=1 \
  --max-unavailable-upgrade=0  # Critical: No unavailability for masters

# Monitor master election and cluster state
kubectl logs -f es-master-0 | grep -i "master\|election"
```

## During Each Phase: Monitoring Commands

```bash
# Continuous cluster health monitoring
watch -n 30 'kubectl exec es-master-0 -- curl -s "localhost:9200/_cluster/health?pretty"'

# Monitor pod status
watch -n 10 'kubectl get pods -o wide'

# Check PV attachment status
kubectl get pv | grep -E "Bound|Available"

# Verify Elasticsearch cluster formation
kubectl exec es-master-0 -- curl -X GET "localhost:9200/_cat/nodes?v"
```

## Post-Upgrade Recovery

### 1. Re-enable Shard Allocation
```bash
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H "Content-Type: application/json" -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "all"
  }
}'
```

### 2. Verify Cluster Recovery
```bash
# Wait for green status
kubectl exec es-master-0 -- curl -X GET "localhost:9200/_cluster/health?wait_for_status=green&timeout=300s"

# Verify all nodes are present
kubectl exec es-master-0 -- curl -X GET "localhost:9200/_cat/nodes?v"

# Check shard distribution
kubectl exec es-master-0 -- curl -X GET "localhost:9200/_cat/shards?v"

# Verify data integrity
kubectl exec es-master-0 -- curl -X GET "localhost:9200/_cat/indices?v"
```

## Rollback Plan (If Needed)

```bash
# If issues arise, rollback the node pool
gcloud container node-pools rollback data-pool \
  --cluster=your-cluster-name \
  --zone=your-zone

# Restore from snapshot if data issues
kubectl exec -it es-master-0 -- curl -X POST "localhost:9200/_snapshot/my-backup/pre-upgrade-snapshot/_restore"
```

## Key Safety Measures

1. **Upgrade Order**: Coordinating → Data → Master nodes
2. **PV Safety**: Regional pd-ssd volumes will reattach automatically
3. **Graceful Shutdown**: Always use Elasticsearch's shutdown API
4. **Monitoring**: Continuous health checks between each phase
5. **Max Unavailable**: Keep at 0 for masters, 1 for data nodes
6. **Backup**: Always have recent snapshots before starting

## Expected Downtime
- **Coordinating nodes**: ~5-10 minutes (non-critical for reads/writes)
- **Data nodes**: Rolling upgrade, no downtime if replicas > 0
- **Master nodes**: <30 seconds per master during failover

This approach ensures data safety while maintaining cluster availability throughout the upgrade process.
I'll walk you through a comprehensive upgrade strategy for your Elasticsearch cluster on GKE. This approach minimizes risk while maintaining data integrity and availability.

## Pre-Upgrade Assessment & Preparation

### 1. Backup Strategy
```bash
# Create a snapshot repository if not already configured
curl -X PUT "localhost:9200/_snapshot/gcs-backup" -H 'Content-Type: application/json' -d'
{
  "type": "gcs",
  "settings": {
    "bucket": "your-backup-bucket",
    "base_path": "elasticsearch-snapshots"
  }
}'

# Take a full cluster snapshot
curl -X PUT "localhost:9200/_snapshot/gcs-backup/pre-upgrade-$(date +%Y%m%d)" -H 'Content-Type: application/json' -d'
{
  "indices": "*",
  "ignore_unavailable": true,
  "include_global_state": true
}'
```

### 2. Verify Cluster Health
```bash
# Check cluster status
kubectl exec -it es-master-0 -- curl -s localhost:9200/_cluster/health?pretty

# Verify all shards are allocated
kubectl exec -it es-master-0 -- curl -s localhost:9200/_cat/shards?v | grep -i unassigned

# Check node roles and distribution
kubectl exec -it es-master-0 -- curl -s localhost:9200/_cat/nodes?v&h=name,node.role,master
```

## Rolling Upgrade Strategy

### Phase 1: Upgrade Coordinating Nodes (Lowest Risk)

```bash
# 1. Cordon and drain first coordinating node pool
kubectl cordon gke-cluster-coord-pool-node-1
kubectl drain gke-cluster-coord-pool-node-1 --ignore-daemonsets --delete-emptydir-data

# 2. Upgrade the node pool
gcloud container node-pools upgrade coord-pool \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32 \
  --max-surge-upgrade=1 \
  --max-unavailable-upgrade=0

# 3. Verify coordinating nodes are healthy
kubectl get pods -l role=coordinating -o wide
kubectl logs es-coordinating-0 | tail -20
```

### Phase 2: Upgrade Data Nodes (Critical - Handle with Care)

```bash
# 1. Disable shard allocation to prevent rebalancing
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'

# 2. Upgrade data node pools one at a time
for pool in data-pool-1 data-pool-2; do
  echo "Upgrading $pool..."
  
  # Upgrade with conservative settings
  gcloud container node-pools upgrade $pool \
    --cluster=your-cluster-name \
    --zone=your-zone \
    --node-version=1.32 \
    --max-surge-upgrade=1 \
    --max-unavailable-upgrade=1
  
  # Wait and verify after each pool
  kubectl wait --for=condition=Ready pods -l role=data --timeout=600s
  
  # Check cluster health before proceeding
  kubectl exec -it es-master-0 -- curl -s localhost:9200/_cluster/health?wait_for_status=yellow&timeout=300s
  
  sleep 60  # Brief pause between pools
done

# 3. Re-enable shard allocation
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "all"
  }
}'
```

### Phase 3: Upgrade Master Nodes (Most Critical)

```bash
# 1. Verify cluster is stable before master upgrade
kubectl exec -it es-master-0 -- curl -s localhost:9200/_cluster/health?pretty

# 2. Upgrade master node pool with minimal disruption
gcloud container node-pools upgrade master-pool \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32 \
  --max-surge-upgrade=1 \
  --max-unavailable-upgrade=1

# 3. Monitor master election process
kubectl logs -f es-master-0 | grep -i "master\|election"
```

## Monitoring & Validation Scripts

### Real-time Health Monitoring
```bash
#!/bin/bash
# monitor-upgrade.sh
while true; do
  echo "=== $(date) ==="
  
  # Cluster health
  HEALTH=$(kubectl exec -it es-master-0 -- curl -s localhost:9200/_cluster/health | jq -r '.status')
  echo "Cluster Health: $HEALTH"
  
  # Node count
  NODES=$(kubectl exec -it es-master-0 -- curl -s localhost:9200/_cat/nodes?h=name | wc -l)
  echo "Active Nodes: $NODES"
  
  # Unassigned shards
  UNASSIGNED=$(kubectl exec -it es-master-0 -- curl -s localhost:9200/_cat/shards | grep UNASSIGNED | wc -l)
  echo "Unassigned Shards: $UNASSIGNED"
  
  # Pod status
  kubectl get pods -l app=elasticsearch --no-headers | awk '{print $1, $3}' | grep -v Running
  
  echo "---"
  sleep 30
done
```

### Post-Upgrade Validation
```bash
# Comprehensive health check
kubectl exec -it es-master-0 -- curl -s localhost:9200/_cluster/health?pretty

# Verify all expected nodes are present
kubectl exec -it es-master-0 -- curl -s localhost:9200/_cat/nodes?v&h=name,node.role,version

# Check index integrity
kubectl exec -it es-master-0 -- curl -s localhost:9200/_cat/indices?v&health=red

# Test basic functionality
kubectl exec -it es-master-0 -- curl -X POST "localhost:9200/test-index/_doc" -H 'Content-Type: application/json' -d'{"test": "post-upgrade", "timestamp": "'$(date)'"}'
```

## Rollback Strategy

If issues arise during upgrade:

```bash
# 1. Stop the upgrade process
gcloud container operations cancel OPERATION_ID

# 2. If data corruption is suspected, restore from snapshot
curl -X POST "localhost:9200/_snapshot/gcs-backup/pre-upgrade-YYYYMMDD/_restore" -H 'Content-Type: application/json' -d'
{
  "indices": "*",
  "ignore_unavailable": true,
  "include_global_state": true
}'

# 3. Scale down problematic StatefulSets if necessary
kubectl scale statefulset es-data --replicas=0
# Then scale back up after resolving issues
kubectl scale statefulset es-data --replicas=5
```

## Key Safety Considerations

1. **Timing**: Perform during low-traffic periods
2. **Monitoring**: Keep multiple monitoring windows open
3. **Communication**: Have your team on standby
4. **Testing**: Validate in a staging environment first
5. **Documentation**: Log each step with timestamps

## Expected Timeline
- Coordinating nodes: 15-20 minutes
- Data nodes: 45-60 minutes (most time-consuming)
- Master nodes: 20-30 minutes
- Validation: 15-20 minutes
- **Total: 2-3 hours**

This approach prioritizes data safety over speed. The regional pd-ssd volumes will persist through the node replacements, and the gradual approach ensures your Elasticsearch cluster maintains quorum and data availability throughout the process.
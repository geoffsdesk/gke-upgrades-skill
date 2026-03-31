I'll walk you through a comprehensive upgrade strategy for your GKE Elasticsearch cluster from 1.31 to 1.32 while maintaining data integrity and availability.

## Pre-Upgrade Preparation

### 1. Create Complete Backup
```bash
# Create snapshot repository (if not already configured)
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_snapshot/gcs-backup" -H 'Content-Type: application/json' -d'
{
  "type": "gcs",
  "settings": {
    "bucket": "your-backup-bucket",
    "base_path": "elasticsearch-snapshots"
  }
}'

# Create full cluster snapshot
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_snapshot/gcs-backup/pre-upgrade-$(date +%Y%m%d)" -H 'Content-Type: application/json' -d'
{
  "indices": "*",
  "ignore_unavailable": true,
  "include_global_state": true
}'
```

### 2. Verify Cluster Health
```bash
# Check cluster status
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health?pretty"
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/nodes?v"
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/shards?v&h=index,shard,prirep,state,unassigned.reason"

# Ensure all shards are active
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health" | jq '.status'  # Should be "green"
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

## Rolling Upgrade Strategy

### Phase 1: Upgrade Coordinating Nodes
Coordinating nodes can be upgraded first as they don't store data.

```bash
# Create new node pool for coordinating nodes with 1.32
gcloud container node-pools create coordinating-nodes-132 \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32.x \
  --num-nodes=2 \
  --machine-type=e2-standard-4 \
  --disk-type=pd-ssd \
  --disk-size=50GB \
  --node-labels=node-type=coordinating \
  --node-taints=node-type=coordinating:NoSchedule

# Update coordinating StatefulSet to use new nodes
kubectl patch statefulset es-coordinating -p '
{
  "spec": {
    "template": {
      "spec": {
        "nodeSelector": {
          "node-type": "coordinating"
        },
        "tolerations": [
          {
            "key": "node-type",
            "value": "coordinating",
            "effect": "NoSchedule"
          }
        ]
      }
    }
  }
}'

# Rolling restart coordinating nodes
kubectl rollout restart statefulset/es-coordinating
kubectl rollout status statefulset/es-coordinating --timeout=600s

# Verify coordinating nodes are healthy
kubectl exec -it es-coordinating-0 -- curl -s "localhost:9200/_cat/nodes?v"

# Delete old coordinating node pool
gcloud container node-pools delete coordinating-nodes-old --cluster=your-cluster-name
```

### Phase 2: Upgrade Data Nodes (One by One)
```bash
# Create new node pool for data nodes
gcloud container node-pools create data-nodes-132 \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32.x \
  --num-nodes=5 \
  --machine-type=e2-highmem-8 \
  --disk-type=pd-ssd \
  --disk-size=100GB \
  --node-labels=node-type=data \
  --node-taints=node-type=data:NoSchedule

# Upgrade data nodes one by one
for i in {0..4}; do
  echo "Upgrading data node es-data-$i"
  
  # Cordon the specific node hosting this pod
  NODE=$(kubectl get pod es-data-$i -o jsonpath='{.spec.nodeName}')
  kubectl cordon $NODE
  
  # Delete the pod (StatefulSet will recreate on new node pool)
  kubectl delete pod es-data-$i
  
  # Wait for pod to be ready on new node
  kubectl wait --for=condition=Ready pod/es-data-$i --timeout=600s
  
  # Verify node joined cluster
  kubectl exec -it es-data-$i -- curl -s "localhost:9200/_cat/nodes?v"
  
  # Wait for cluster to stabilize
  kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health?wait_for_status=yellow&timeout=300s"
  
  echo "Data node es-data-$i upgraded successfully"
  sleep 30
done

# Re-enable shard allocation after all data nodes are upgraded
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "all"
  }
}'

# Wait for green status
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health?wait_for_status=green&timeout=600s"
```

### Phase 3: Upgrade Master Nodes (One by One)
Master nodes require the most care to maintain cluster stability.

```bash
# Create new node pool for master nodes
gcloud container node-pools create master-nodes-132 \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32.x \
  --num-nodes=3 \
  --machine-type=e2-standard-4 \
  --disk-type=pd-ssd \
  --disk-size=50GB \
  --node-labels=node-type=master \
  --node-taints=node-type=master:NoSchedule

# Upgrade master nodes one by one (start with non-active master)
for i in {1,2,0}; do  # Start with non-active masters first
  echo "Upgrading master node es-master-$i"
  
  # Check which node is the active master
  ACTIVE_MASTER=$(kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/master" | awk '{print $4}')
  echo "Current active master: $ACTIVE_MASTER"
  
  # Cordon the node
  NODE=$(kubectl get pod es-master-$i -o jsonpath='{.spec.nodeName}')
  kubectl cordon $NODE
  
  # Delete the pod
  kubectl delete pod es-master-$i
  
  # Wait for pod to be ready
  kubectl wait --for=condition=Ready pod/es-master-$i --timeout=600s
  
  # Verify cluster has proper master
  kubectl exec -it es-master-$i -- curl -s "localhost:9200/_cluster/health?timeout=60s"
  
  echo "Master node es-master-$i upgraded successfully"
  sleep 60  # Longer wait between master upgrades
done
```

## Post-Upgrade Verification

### 1. Comprehensive Health Check
```bash
# Check cluster health
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health?pretty"

# Verify all nodes are present
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/nodes?v"

# Check shard allocation
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/shards?v&h=index,shard,prirep,state,node"

# Verify indices are accessible
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/indices?v"

# Test search functionality
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_search?size=1&pretty"
```

### 2. Performance Test
```bash
# Run a sample query to ensure performance
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/stats?pretty"
```

### 3. Clean Up Old Resources
```bash
# Only after confirming everything works
gcloud container node-pools delete data-nodes-old --cluster=your-cluster-name
gcloud container node-pools delete master-nodes-old --cluster=your-cluster-name
```

## Rollback Plan (If Needed)

If issues arise during upgrade:

```bash
# 1. Restore from snapshot
kubectl exec -it es-master-0 -- curl -X POST "localhost:9200/_snapshot/gcs-backup/pre-upgrade-$(date +%Y%m%d)/_restore" -H 'Content-Type: application/json' -d'
{
  "indices": "*",
  "ignore_unavailable": true,
  "include_global_state": true
}'

# 2. Scale back to old node pools if needed
# Keep old node pools until upgrade is fully verified
```

## Key Considerations

1. **PV Binding**: Regional PD-SSD volumes will automatically bind to pods on new nodes in the same region
2. **DNS**: Internal Kubernetes DNS should handle service discovery during the transition
3. **Monitoring**: Watch cluster metrics throughout the process
4. **Timing**: Perform during low-traffic periods
5. **Validation**: Test application connectivity after each phase

This approach ensures minimal downtime while maintaining data integrity throughout the upgrade process.
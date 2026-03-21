I'll walk you through a safe GKE upgrade strategy for your Elasticsearch cluster. Given your setup with separate node pools, we can use a rolling approach to maintain availability.

## Pre-Upgrade Preparation

### 1. Backup Your Data
```bash
# Create a snapshot repository (if not already configured)
curl -X PUT "localhost:9200/_snapshot/gcs_backup" -H 'Content-Type: application/json' -d'
{
  "type": "gcs",
  "settings": {
    "bucket": "your-backup-bucket",
    "base_path": "elasticsearch-snapshots"
  }
}'

# Create a full cluster snapshot
curl -X PUT "localhost:9200/_snapshot/gcs_backup/pre-upgrade-$(date +%Y%m%d)" -H 'Content-Type: application/json' -d'
{
  "indices": "*",
  "include_global_state": true
}'
```

### 2. Verify Cluster Health
```bash
# Check cluster status
kubectl exec -it elasticsearch-master-0 -- curl -s localhost:9200/_cluster/health?pretty

# Verify all shards are allocated
kubectl exec -it elasticsearch-master-0 -- curl -s localhost:9200/_cat/shards?v
```

### 3. Disable Shard Allocation (Temporary)
```bash
kubectl exec -it elasticsearch-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'
```

## Upgrade Strategy: Node Pool by Node Pool

### Step 1: Upgrade Coordinating Nodes First
Coordinating nodes are stateless and safest to start with.

```bash
# Upgrade the coordinating node pool
gcloud container node-pools upgrade coordinating-pool \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32

# Monitor the upgrade
kubectl get nodes -l node-pool=coordinating-pool
```

### Step 2: Upgrade Data Nodes (One by One)
Data nodes require careful handling due to StatefulSets.

```bash
# For each data node, cordon and drain carefully
for i in {0..4}; do
  echo "Processing elasticsearch-data-${i}"
  
  # Get the node name
  NODE_NAME=$(kubectl get pod elasticsearch-data-${i} -o jsonpath='{.spec.nodeName}')
  
  # Cordon the node
  kubectl cordon $NODE_NAME
  
  # Delete the pod (StatefulSet will reschedule)
  kubectl delete pod elasticsearch-data-${i}
  
  # Wait for the pod to be ready on the new node
  kubectl wait --for=condition=ready pod/elasticsearch-data-${i} --timeout=600s
  
  # Verify cluster health before proceeding
  kubectl exec -it elasticsearch-master-0 -- curl -s localhost:9200/_cluster/health?wait_for_status=yellow&timeout=5m
  
  echo "Node elasticsearch-data-${i} upgraded successfully"
  sleep 30
done
```

Alternative approach using node pool upgrade:
```bash
# Upgrade data node pool (this will handle the rolling update)
gcloud container node-pools upgrade data-pool \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32 \
  --max-surge-upgrade=1 \
  --max-unavailable-upgrade=0
```

### Step 3: Upgrade Master Nodes (Most Critical)
Master nodes require special care to maintain quorum.

```bash
# Upgrade master nodes one at a time
for i in {0..2}; do
  echo "Processing elasticsearch-master-${i}"
  
  NODE_NAME=$(kubectl get pod elasticsearch-master-${i} -o jsonpath='{.spec.nodeName}')
  kubectl cordon $NODE_NAME
  
  # Delete the master pod
  kubectl delete pod elasticsearch-master-${i}
  
  # Wait for pod to be ready
  kubectl wait --for=condition=ready pod/elasticsearch-master-${i} --timeout=600s
  
  # Verify cluster has master and quorum
  kubectl exec -it elasticsearch-master-${i} -- curl -s localhost:9200/_cat/master
  kubectl exec -it elasticsearch-master-${i} -- curl -s localhost:9200/_cluster/health?wait_for_status=yellow&timeout=5m
  
  echo "Master node ${i} upgraded successfully"
  sleep 60  # Give more time between master upgrades
done
```

## Post-Upgrade Steps

### 1. Re-enable Shard Allocation
```bash
kubectl exec -it elasticsearch-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "all"
  }
}'
```

### 2. Verify Cluster Health
```bash
# Wait for green status
kubectl exec -it elasticsearch-master-0 -- curl -s "localhost:9200/_cluster/health?wait_for_status=green&timeout=10m&pretty"

# Check all nodes are visible
kubectl exec -it elasticsearch-master-0 -- curl -s localhost:9200/_cat/nodes?v

# Verify all shards are allocated
kubectl exec -it elasticsearch-master-0 -- curl -s localhost:9200/_cat/shards?h=index,shard,prirep,state,node | grep -v STARTED || echo "All shards started"
```

### 3. Performance Check
```bash
# Run a simple query to test functionality
kubectl exec -it elasticsearch-master-0 -- curl -s "localhost:9200/_search?pretty" -H 'Content-Type: application/json' -d'
{
  "query": {
    "match_all": {}
  },
  "size": 1
}'
```

## Monitoring During Upgrade

Create a monitoring script to track the upgrade:

```bash
#!/bin/bash
# monitor-upgrade.sh

while true; do
  echo "=== $(date) ==="
  echo "Cluster Health:"
  kubectl exec -it elasticsearch-master-0 -- curl -s localhost:9200/_cluster/health?pretty | grep -E "(status|number_of_nodes)"
  
  echo -e "\nNode Status:"
  kubectl get nodes --no-headers | awk '{print $1, $2}' | grep -E "(Ready|NotReady)"
  
  echo -e "\nPod Status:"
  kubectl get pods -l app=elasticsearch --no-headers | awk '{print $1, $3}'
  
  echo "========================"
  sleep 30
done
```

## Rollback Plan

If issues occur:

```bash
# Emergency rollback of node pool
gcloud container node-pools rollback data-pool \
  --cluster=your-cluster-name \
  --zone=your-zone

# Restore from snapshot if needed
curl -X POST "localhost:9200/_snapshot/gcs_backup/pre-upgrade-YYYYMMDD/_restore"
```

## Key Considerations

1. **PV Safety**: Regional pd-ssd volumes will persist through node upgrades
2. **Quorum**: Never upgrade more than 1 master node at a time
3. **Timing**: Plan for 2-4 hours depending on data size and cluster recovery time
4. **Monitoring**: Keep the monitoring script running throughout
5. **Network Policies**: Ensure they don't block pod-to-pod communication during rescheduling

Would you like me to elaborate on any of these steps or discuss specific concerns about your cluster configuration?
I'll walk you through a comprehensive upgrade strategy for your Elasticsearch cluster on GKE from 1.31 to 1.32 while maintaining data integrity and availability.

## Pre-Upgrade Preparation

### 1. Backup and Health Check
```bash
# Check cluster health
kubectl get pods -n <elasticsearch-namespace>
curl -X GET "elasticsearch-service:9200/_cluster/health?pretty"

# Verify all shards are allocated
curl -X GET "elasticsearch-service:9200/_cat/shards?v&h=index,shard,prirep,state,unassigned.reason"

# Create backup (if you have snapshot repository configured)
curl -X PUT "elasticsearch-service:9200/_snapshot/my_backup/upgrade_backup_$(date +%Y%m%d)" \
  -H 'Content-Type: application/json' -d'{"indices": "*"}'
```

### 2. Disable Shard Allocation
```bash
# Temporarily disable shard rebalancing during upgrade
curl -X PUT "elasticsearch-service:9200/_cluster/settings" \
  -H 'Content-Type: application/json' -d'{
    "persistent": {
      "cluster.routing.allocation.enable": "primaries"
    }
  }'
```

## Upgrade Strategy: Rolling Node Pool Updates

### Phase 1: Upgrade Coordinating Nodes First
Coordinating nodes are stateless and safest to upgrade first.

```bash
# Get current node pool info
gcloud container node-pools describe coordinating-pool \
  --cluster=your-cluster-name --zone=your-zone

# Create new node pool with 1.32
gcloud container node-pools create coordinating-pool-132 \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32.x \
  --num-nodes=2 \
  --machine-type=your-machine-type \
  --disk-size=your-disk-size \
  --node-labels=elasticsearch.role=coordinating

# Update coordinating node StatefulSet to use new nodes
kubectl patch statefulset coordinating-nodes -p '{
  "spec": {
    "template": {
      "spec": {
        "nodeSelector": {
          "cloud.google.com/gke-nodepool": "coordinating-pool-132"
        }
      }
    }
  }
}'

# Wait for pods to be rescheduled and healthy
kubectl rollout status statefulset/coordinating-nodes
```

### Phase 2: Upgrade Data Nodes (Most Critical)
Use a careful one-by-one approach for data nodes.

```bash
# Create new data node pool
gcloud container node-pools create data-pool-132 \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32.x \
  --num-nodes=5 \
  --machine-type=your-data-machine-type \
  --disk-size=your-data-disk-size \
  --node-labels=elasticsearch.role=data

# Upgrade data nodes one by one
for i in {0..4}; do
  echo "Upgrading data node $i"
  
  # Gracefully exclude the node from allocation
  DATA_NODE_IP=$(kubectl get pod data-$i -o jsonpath='{.status.podIP}')
  curl -X PUT "elasticsearch-service:9200/_cluster/settings" \
    -H 'Content-Type: application/json' -d"{
      \"transient\": {
        \"cluster.routing.allocation.exclude._ip\": \"$DATA_NODE_IP\"
      }
    }"
  
  # Wait for shards to move away
  while true; do
    SHARD_COUNT=$(curl -s "elasticsearch-service:9200/_cat/shards" | grep $DATA_NODE_IP | wc -l)
    if [ "$SHARD_COUNT" -eq "0" ]; then
      break
    fi
    echo "Waiting for $SHARD_COUNT shards to relocate..."
    sleep 30
  done
  
  # Delete the specific pod to trigger recreation on new node pool
  kubectl delete pod data-$i
  
  # Wait for pod to be healthy on new node
  kubectl wait --for=condition=Ready pod/data-$i --timeout=300s
  
  # Clear the exclusion
  curl -X PUT "elasticsearch-service:9200/_cluster/settings" \
    -H 'Content-Type: application/json' -d'{
      "transient": {
        "cluster.routing.allocation.exclude._ip": null
      }
    }'
  
  # Wait for cluster to stabilize
  sleep 60
done
```

### Phase 3: Upgrade Master Nodes
Master nodes require special care to maintain quorum.

```bash
# Create new master node pool
gcloud container node-pools create master-pool-132 \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32.x \
  --num-nodes=3 \
  --machine-type=your-master-machine-type \
  --node-labels=elasticsearch.role=master

# Upgrade masters one at a time, never losing quorum
for i in {0..2}; do
  echo "Upgrading master node $i"
  
  # Delete one master pod
  kubectl delete pod master-$i
  
  # Wait for it to come back healthy
  kubectl wait --for=condition=Ready pod/master-$i --timeout=300s
  
  # Verify cluster has quorum and is stable
  curl -X GET "elasticsearch-service:9200/_cluster/health?wait_for_status=yellow&timeout=60s"
  
  sleep 30
done
```

## Post-Upgrade Tasks

### 1. Re-enable Shard Allocation
```bash
curl -X PUT "elasticsearch-service:9200/_cluster/settings" \
  -H 'Content-Type: application/json' -d'{
    "persistent": {
      "cluster.routing.allocation.enable": "all"
    }
  }'
```

### 2. Verify Cluster Health
```bash
# Check overall cluster health
curl -X GET "elasticsearch-service:9200/_cluster/health?pretty"

# Verify all nodes are visible
curl -X GET "elasticsearch-service:9200/_cat/nodes?v"

# Check shard allocation
curl -X GET "elasticsearch-service:9200/_cat/allocation?v"

# Test basic functionality
curl -X GET "elasticsearch-service:9200/_cat/indices?v"
```

### 3. Clean Up Old Node Pools
```bash
# Only after confirming everything works
gcloud container node-pools delete coordinating-pool --cluster=your-cluster-name
gcloud container node-pools delete data-pool --cluster=your-cluster-name  
gcloud container node-pools delete master-pool --cluster=your-cluster-name
```

## Alternative Approach: In-Place Node Pool Upgrade

If you prefer less control plane changes:

```bash
# Upgrade each pool in sequence
gcloud container node-pools upgrade coordinating-pool \
  --cluster=your-cluster-name --node-version=1.32.x

gcloud container node-pools upgrade data-pool \
  --cluster=your-cluster-name --node-version=1.32.x --max-unavailable=1

gcloud container node-pools upgrade master-pool \
  --cluster=your-cluster-name --node-version=1.32.x --max-unavailable=1
```

## Monitoring During Upgrade

```bash
# Monitor cluster health continuously
watch 'curl -s "elasticsearch-service:9200/_cluster/health" | jq'

# Monitor pod status
watch 'kubectl get pods -o wide'

# Monitor shard allocation
watch 'curl -s "elasticsearch-service:9200/_cat/shards?v&h=index,shard,prirep,state"'
```

## Rollback Plan

If issues occur:
1. Keep old node pools until upgrade is confirmed successful
2. Have backup snapshots ready for restoration
3. Document original configuration for quick rollback

This approach ensures minimal downtime (usually just brief disruptions during individual pod restarts) while maintaining data integrity through Elasticsearch's native resilience mechanisms.
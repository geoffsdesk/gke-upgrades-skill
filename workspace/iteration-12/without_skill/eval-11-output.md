I'll walk you through a safe GKE upgrade strategy for your Elasticsearch cluster. Given your setup with separate node pools, we can do a rolling upgrade while maintaining availability.

## Pre-Upgrade Checklist

### 1. Backup Your Data
```bash
# Create a snapshot repository (if not already configured)
curl -X PUT "localhost:9200/_snapshot/gcs-repository" -H 'Content-Type: application/json' -d'
{
  "type": "gcs",
  "settings": {
    "bucket": "your-backup-bucket",
    "base_path": "elasticsearch-snapshots"
  }
}'

# Create a snapshot
curl -X PUT "localhost:9200/_snapshot/gcs-repository/pre-upgrade-snapshot" -d'
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
```

### 3. Disable Shard Allocation (Temporary)
```bash
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'
```

## Upgrade Strategy

### Phase 1: Upgrade Control Plane
```bash
# Upgrade the GKE control plane first
gcloud container clusters upgrade YOUR_CLUSTER_NAME \
  --master \
  --cluster-version=1.32.x-gke.y \
  --zone=YOUR_ZONE \
  --async
```

### Phase 2: Upgrade Coordinating Nodes First
```bash
# Upgrade coordinating node pool (least critical for data)
gcloud container node-pools upgrade coordinating-pool \
  --cluster=YOUR_CLUSTER_NAME \
  --zone=YOUR_ZONE \
  --node-version=1.32.x-gke.y
```

Wait for coordinating nodes to be ready:
```bash
kubectl get nodes -l node-pool=coordinating-pool
kubectl get pods -l app=elasticsearch,role=coordinating
```

### Phase 3: Upgrade Data Nodes (One at a Time)
```bash
# For each data node, we'll cordon, drain, and upgrade
for i in {0..4}; do
  echo "Processing data node $i"
  
  # Get the node name
  NODE_NAME=$(kubectl get pod es-data-$i -o jsonpath='{.spec.nodeName}')
  
  # Cordon the node
  kubectl cordon $NODE_NAME
  
  # Gracefully shutdown Elasticsearch on this node
  kubectl exec es-data-$i -- curl -X POST "localhost:9200/_cluster/nodes/$NODE_NAME/_shutdown"
  
  # Scale down the specific pod
  kubectl delete pod es-data-$i --grace-period=300
  
  # Upgrade the node (you might need to do this per node or in small batches)
  gcloud container node-pools upgrade data-pool \
    --cluster=YOUR_CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --node-version=1.32.x-gke.y \
    --max-surge=1 \
    --max-unavailable=0
  
  # Wait for pod to be running
  kubectl wait --for=condition=Ready pod/es-data-$i --timeout=600s
  
  # Verify node rejoined cluster
  kubectl exec es-master-0 -- curl -s "localhost:9200/_cat/nodes?v"
  
  # Wait for cluster to stabilize
  sleep 60
done
```

### Phase 4: Upgrade Master Nodes (One at a Time)
```bash
# Masters need special care - upgrade one at a time
for i in {0..2}; do
  echo "Processing master node $i"
  
  NODE_NAME=$(kubectl get pod es-master-$i -o jsonpath='{.spec.nodeName}')
  
  # Cordon node
  kubectl cordon $NODE_NAME
  
  # Delete the pod gracefully
  kubectl delete pod es-master-$i --grace-period=300
  
  # Upgrade node
  gcloud container node-pools upgrade master-pool \
    --cluster=YOUR_CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --node-version=1.32.x-gke.y \
    --max-surge=1 \
    --max-unavailable=0
  
  # Wait for master to rejoin
  kubectl wait --for=condition=Ready pod/es-master-$i --timeout=600s
  
  # Verify cluster has quorum
  kubectl exec es-master-$i -- curl -s "localhost:9200/_cluster/health"
  
  # Wait before next master
  sleep 120
done
```

## Post-Upgrade Steps

### 1. Re-enable Shard Allocation
```bash
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": null
  }
}'
```

### 2. Monitor Cluster Recovery
```bash
# Watch cluster health
watch 'kubectl exec es-master-0 -- curl -s "localhost:9200/_cluster/health?pretty"'

# Monitor shard allocation
kubectl exec es-master-0 -- curl -s "localhost:9200/_cat/recovery?v&active_only=true"
```

### 3. Verify Everything is Working
```bash
# Check all nodes
kubectl exec es-master-0 -- curl -s "localhost:9200/_cat/nodes?v"

# Check indices
kubectl exec es-master-0 -- curl -s "localhost:9200/_cat/indices?v"

# Test a query
kubectl exec es-master-0 -- curl -s "localhost:9200/_search?pretty&size=1"
```

## Alternative Safer Approach: Blue-Green Deployment

If you want zero downtime and have the resources:

1. **Create a new cluster** with k8s 1.32
2. **Set up cross-cluster replication** from old to new
3. **Switch traffic** when replication is caught up
4. **Decommission old cluster**

```yaml
# Cross-cluster replication setup
apiVersion: v1
kind: ConfigMap
metadata:
  name: es-remote-cluster-config
data:
  elasticsearch.yml: |
    cluster.remote:
      old_cluster:
        seeds: ["old-es-cluster:9300"]
```

## Monitoring During Upgrade

Keep these commands handy:
```bash
# Quick health check
kubectl exec es-master-0 -- curl -s "localhost:9200/_cluster/health" | jq '.status'

# Check for relocating shards
kubectl exec es-master-0 -- curl -s "localhost:9200/_cat/shards" | grep -E "(RELOCATING|INITIALIZING|UNASSIGNED)"

# Monitor pod status
kubectl get pods -l app=elasticsearch -o wide
```

## Rollback Plan

If issues arise:
1. **Scale back to problematic nodes** to previous version
2. **Restore from snapshot** if data corruption occurs
3. **Keep the old node pool** until you're confident in the upgrade

The key is patience - don't rush the master node upgrades, and always verify cluster health between each step.
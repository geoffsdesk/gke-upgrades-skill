I'll walk you through a comprehensive upgrade strategy for your GKE Elasticsearch cluster from 1.31 to 1.32. Given your setup with StatefulSets and the critical nature of Elasticsearch data, we'll follow a careful approach.

## Pre-Upgrade Preparation

### 1. Create a Complete Backup
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

# Create a full cluster snapshot
curl -X PUT "localhost:9200/_snapshot/gcs-backup/pre-upgrade-snapshot" -H 'Content-Type: application/json' -d'
{
  "indices": "*",
  "ignore_unavailable": true,
  "include_global_state": true
}'

# Monitor snapshot progress
curl -X GET "localhost:9200/_snapshot/gcs-backup/pre-upgrade-snapshot/_status"
```

### 2. Verify Cluster Health
```bash
# Check cluster health
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"

# Check shard allocation
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/shards?v&h=index,shard,prirep,state,unassigned.reason"

# Document current settings
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/settings?pretty"
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

## Node Pool Upgrade Strategy

### 4. Create New Node Pools for Each Role

```bash
# Create new master node pool
gcloud container node-pools create es-master-132 \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --machine-type=e2-standard-4 \
  --num-nodes=3 \
  --disk-size=50GB \
  --disk-type=pd-ssd \
  --node-labels=elasticsearch-role=master \
  --node-taints=elasticsearch-role=master:NoSchedule \
  --enable-autoscaling \
  --min-nodes=3 \
  --max-nodes=3

# Create new data node pool
gcloud container node-pools create es-data-132 \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --machine-type=e2-standard-8 \
  --num-nodes=5 \
  --disk-size=100GB \
  --disk-type=pd-ssd \
  --node-labels=elasticsearch-role=data \
  --node-taints=elasticsearch-role=data:NoSchedule \
  --enable-autoscaling \
  --min-nodes=5 \
  --max-nodes=5

# Create new coordinating node pool
gcloud container node-pools create es-coordinating-132 \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --machine-type=e2-standard-4 \
  --num-nodes=2 \
  --disk-size=50GB \
  --disk-type=pd-ssd \
  --node-labels=elasticsearch-role=coordinating \
  --node-taints=elasticsearch-role=coordinating:NoSchedule \
  --enable-autoscaling \
  --min-nodes=2 \
  --max-nodes=2
```

### 5. Update Node Selectors and Tolerations

Prepare updated manifests for your StatefulSets to target the new node pools:

```yaml
# es-master-statefulset.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: es-master
spec:
  template:
    spec:
      nodeSelector:
        elasticsearch-role: master
        # Add node pool selector if needed
      tolerations:
      - key: elasticsearch-role
        operator: Equal
        value: master
        effect: NoSchedule
      # ... rest of your spec
```

## Rolling Upgrade Process

### 6. Upgrade Coordinating Nodes First

```bash
# Apply updated manifests to migrate coordinating nodes
kubectl patch statefulset es-coordinating -p '{"spec":{"template":{"spec":{"nodeSelector":{"cloud.google.com/gke-nodepool":"es-coordinating-132"}}}}}'

# Wait for coordinating nodes to be ready
kubectl rollout status statefulset/es-coordinating --timeout=600s

# Verify coordinating nodes joined cluster
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/nodes?v&h=name,node.role,ip"
```

### 7. Upgrade Master Nodes (One by One)

```bash
# Exclude one master node from cluster temporarily
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/voting_config_exclusions?node_names=es-master-2"

# Scale down one master node
kubectl patch statefulset es-master -p '{"spec":{"replicas":2}}'

# Update node selector for master StatefulSet
kubectl patch statefulset es-master -p '{"spec":{"template":{"spec":{"nodeSelector":{"cloud.google.com/gke-nodepool":"es-master-132"}}}}}'

# Scale back up
kubectl patch statefulset es-master -p '{"spec":{"replicas":3}}'

# Wait for master nodes to be ready
kubectl rollout status statefulset/es-master --timeout=600s

# Clear voting config exclusions
kubectl exec -it es-master-0 -- curl -X DELETE "localhost:9200/_cluster/voting_config_exclusions"

# Verify master nodes
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/nodes?v&h=name,node.role,master,ip"
```

### 8. Upgrade Data Nodes (Rolling Restart)

```bash
# Re-enable shard allocation for primaries
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'

# Update data node StatefulSet
kubectl patch statefulset es-data -p '{"spec":{"template":{"spec":{"nodeSelector":{"cloud.google.com/gke-nodepool":"es-data-132"}}}}}'

# Perform rolling restart of data nodes
for i in {0..4}; do
  echo "Upgrading es-data-$i"
  
  # Delete the pod to trigger recreation on new node pool
  kubectl delete pod es-data-$i
  
  # Wait for pod to be ready
  kubectl wait --for=condition=ready pod/es-data-$i --timeout=600s
  
  # Wait for node to rejoin cluster
  while true; do
    status=$(kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/nodes?h=name" | grep "es-data-$i" || echo "")
    if [[ -n "$status" ]]; then
      echo "es-data-$i rejoined cluster"
      break
    fi
    echo "Waiting for es-data-$i to rejoin cluster..."
    sleep 30
  done
  
  # Wait for shards to stabilize
  sleep 60
done
```

### 9. Final Health Checks and Cleanup

```bash
# Re-enable full shard allocation
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": null
  }
}'

# Wait for cluster to reach green status
while true; do
  status=$(kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health" | jq -r '.status')
  if [[ "$status" == "green" ]]; then
    echo "Cluster is green"
    break
  fi
  echo "Cluster status: $status, waiting..."
  sleep 30
done

# Verify all nodes are present
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/nodes?v"

# Check shard allocation
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/shards?v&h=index,shard,prirep,state,node"
```

### 10. Clean Up Old Node Pools

```bash
# Delete old node pools
gcloud container node-pools delete es-master-131 --cluster=your-cluster-name --zone=your-zone
gcloud container node-pools delete es-data-131 --cluster=your-cluster-name --zone=your-zone  
gcloud container node-pools delete es-coordinating-131 --cluster=your-cluster-name --zone=your-zone
```

## Rollback Plan

If issues arise during the upgrade:

```bash
# 1. Restore from snapshot if data corruption occurs
curl -X POST "localhost:9200/_snapshot/gcs-backup/pre-upgrade-snapshot/_restore"

# 2. Revert StatefulSet nodeSelector changes
kubectl patch statefulset es-master -p '{"spec":{"template":{"spec":{"nodeSelector":{"cloud.google.com/gke-nodepool":"es-master-131"}}}}}'
kubectl patch statefulset es-data -p '{"spec":{"template":{"spec":{"nodeSelector":{"cloud.google.com/gke-nodepool":"es-data-131"}}}}}'
kubectl patch statefulset es-coordinating -p '{"spec":{"template":{"spec":{"nodeSelector":{"cloud.google.com/gke-nodepool":"es-coordinating-131"}}}}}'

# 3. Scale StatefulSets to trigger pod recreation on old nodes
kubectl rollout restart statefulset/es-master
kubectl rollout restart statefulset/es-data  
kubectl rollout restart statefulset/es-coordinating
```

## Key Points

- **Data Safety**: Regional pd-ssd volumes persist across node changes
- **Availability**: Rolling upgrade maintains cluster quorum
- **Monitoring**: Watch cluster health at each step
- **Timing**: Allow adequate time for shard reallocation
- **Testing**: Test this process in a staging environment first

This approach ensures minimal downtime while safely migrating your Elasticsearch cluster to GKE 1.32.
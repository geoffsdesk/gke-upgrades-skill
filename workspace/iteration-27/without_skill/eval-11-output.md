I'll walk you through a comprehensive upgrade strategy for your Elasticsearch cluster on GKE Standard. This approach prioritizes data safety and maintains availability throughout the process.

## Pre-Upgrade Preparation

### 1. Create a Complete Backup
```bash
# Create a snapshot repository (if not already configured)
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_snapshot/gcs-backup" -H 'Content-Type: application/json' -d'
{
  "type": "gcs",
  "settings": {
    "bucket": "your-backup-bucket",
    "base_path": "elasticsearch-snapshots"
  }
}'

# Create a full cluster snapshot
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_snapshot/gcs-backup/pre-upgrade-$(date +%Y%m%d)" -H 'Content-Type: application/json' -d'
{
  "indices": "*",
  "ignore_unavailable": true,
  "include_global_state": true
}'
```

### 2. Verify Cluster Health
```bash
# Check cluster health
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"

# Disable shard allocation (prevent rebalancing during upgrade)
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'
```

### 3. Document Current State
```bash
# Save current node pool configurations
kubectl get nodes -o wide > pre-upgrade-nodes.txt
kubectl get statefulsets -o yaml > pre-upgrade-statefulsets.yaml
kubectl get pvc > pre-upgrade-pvcs.txt
```

## Upgrade Strategy: Rolling Node Pool Updates

### Phase 1: Upgrade Coordinating Nodes (Lowest Risk)

```bash
# Create new node pool for coordinating nodes
gcloud container node-pools create coord-nodes-132 \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --machine-type=e2-standard-4 \
  --num-nodes=2 \
  --node-version=1.32 \
  --disk-size=100GB \
  --node-labels=role=coordinating

# Cordon old coordinating nodes
kubectl cordon gke-cluster-coord-nodes-old-xxx
kubectl cordon gke-cluster-coord-nodes-old-yyy

# Update StatefulSet node affinity to prefer new nodes
kubectl patch statefulset es-coordinating -p '
{
  "spec": {
    "template": {
      "spec": {
        "affinity": {
          "nodeAffinity": {
            "preferredDuringSchedulingIgnoredDuringExecution": [{
              "weight": 100,
              "preference": {
                "matchExpressions": [{
                  "key": "role",
                  "operator": "In",
                  "values": ["coordinating"]
                }]
              }
            }]
          }
        }
      }
    }
  }
}'

# Delete coordinating pods one by one to trigger rescheduling
kubectl delete pod es-coordinating-0
# Wait for pod to be ready before proceeding
kubectl wait --for=condition=Ready pod/es-coordinating-0 --timeout=300s

kubectl delete pod es-coordinating-1
kubectl wait --for=condition=Ready pod/es-coordinating-1 --timeout=300s
```

### Phase 2: Upgrade Data Nodes (Most Critical)

```bash
# Create new node pool for data nodes
gcloud container node-pools create data-nodes-132 \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --machine-type=e2-standard-8 \
  --num-nodes=5 \
  --node-version=1.32 \
  --disk-size=100GB \
  --node-labels=role=data

# For each data node, perform controlled migration
for i in {0..4}; do
  echo "Upgrading data node $i"
  
  # Exclude the node from shard allocation
  NODE_IP=$(kubectl get pod es-data-$i -o jsonpath='{.status.podIP}')
  kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d"
  {
    \"transient\": {
      \"cluster.routing.allocation.exclude._ip\": \"$NODE_IP\"
    }
  }"
  
  # Wait for shards to move away from this node
  while true; do
    SHARD_COUNT=$(kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/allocation?h=shards&format=json" | jq ".[].shards | select(. != null)")
    if [[ "$SHARD_COUNT" == "0" ]] || [[ -z "$SHARD_COUNT" ]]; then
      echo "Shards evacuated from node $i"
      break
    fi
    echo "Waiting for shards to evacuate... Current count: $SHARD_COUNT"
    sleep 30
  done
  
  # Delete the pod to trigger rescheduling on new node
  kubectl delete pod es-data-$i
  
  # Wait for pod to be ready
  kubectl wait --for=condition=Ready pod/es-data-$i --timeout=600s
  
  # Clear the exclusion
  kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
  {
    "transient": {
      "cluster.routing.allocation.exclude._ip": null
    }
  }'
  
  # Wait for cluster to be green before proceeding
  while true; do
    HEALTH=$(kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health" | jq -r '.status')
    if [[ "$HEALTH" == "green" ]]; then
      echo "Cluster is green, proceeding to next node"
      break
    fi
    echo "Waiting for cluster to be green... Current status: $HEALTH"
    sleep 30
  done
done
```

### Phase 3: Upgrade Master Nodes (High Coordination)

```bash
# Create new node pool for master nodes
gcloud container node-pools create master-nodes-132 \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --machine-type=e2-standard-4 \
  --num-nodes=3 \
  --node-version=1.32 \
  --disk-size=100GB \
  --node-labels=role=master

# Upgrade master nodes one by one (never more than one at a time)
for i in 0 1 2; do
  echo "Upgrading master node $i"
  
  # Delete the pod
  kubectl delete pod es-master-$i
  
  # Wait for pod to be ready
  kubectl wait --for=condition=Ready pod/es-master-$i --timeout=600s
  
  # Verify cluster can elect master
  while true; do
    MASTER=$(kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/master" | awk '{print $1}')
    if [[ ! -z "$MASTER" ]]; then
      echo "Master elected: $MASTER"
      break
    fi
    echo "Waiting for master election..."
    sleep 10
  done
  
  # Wait additional time for cluster stabilization
  sleep 60
done
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

### 2. Verify Cluster Health
```bash
# Check cluster health
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"

# Check all nodes are visible
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/nodes?v"

# Verify data integrity
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/indices?v"
```

### 3. Clean Up Old Node Pools
```bash
# Only after verifying everything works correctly
gcloud container node-pools delete coord-nodes-old --cluster=your-cluster-name
gcloud container node-pools delete data-nodes-old --cluster=your-cluster-name  
gcloud container node-pools delete master-nodes-old --cluster=your-cluster-name
```

## Monitoring During Upgrade

```bash
# Monitor cluster status
watch 'kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health" | jq .'

# Monitor shard allocation
watch 'kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/shards?v"'

# Monitor pods
watch 'kubectl get pods -o wide'
```

## Rollback Plan

If issues occur:

```bash
# Re-enable old node pools
gcloud container node-pools create coord-nodes-131 --node-version=1.31 ...

# Restore from snapshot if needed
kubectl exec -it es-master-0 -- curl -X POST "localhost:9200/_snapshot/gcs-backup/pre-upgrade-$(date +%Y%m%d)/_restore"

# Revert StatefulSet configurations
kubectl apply -f pre-upgrade-statefulsets.yaml
```

## Key Safety Considerations

1. **Never upgrade more than one master node at a time**
2. **Always wait for green cluster status between data node upgrades**
3. **Monitor shard allocation during the entire process**
4. **Keep old node pools until fully verified**
5. **Have snapshot restoration procedure ready**

This approach ensures zero data loss and maintains cluster availability throughout the upgrade process. The entire process typically takes 2-4 hours depending on data size and rebalancing time.
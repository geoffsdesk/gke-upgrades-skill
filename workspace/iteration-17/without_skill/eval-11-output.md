I'll walk you through a safe GKE upgrade strategy for your Elasticsearch cluster. Given your setup with multiple node types and StatefulSets, we need to be methodical to maintain availability.

## Pre-Upgrade Preparation

### 1. Backup and Health Check
```bash
# Check cluster health
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"

# Verify all shards are assigned
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/shards?v&h=index,shard,prirep,state,unassigned.reason"

# Create backup (if you have snapshot repository configured)
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_snapshot/backup/pre-upgrade-$(date +%Y%m%d)"
```

### 2. Disable Shard Allocation
```bash
# Temporarily disable shard reallocation to prevent unnecessary moves during upgrade
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" \
  -H "Content-Type: application/json" \
  -d '{
    "persistent": {
      "cluster.routing.allocation.enable": "primaries"
    }
  }'
```

### 3. Check Node Pool Configurations
```bash
# List current node pools and their versions
gcloud container node-pools list --cluster=YOUR_CLUSTER_NAME --zone=YOUR_ZONE

# Verify your regional PD setup
kubectl get pv -o wide
```

## Upgrade Strategy

### Phase 1: Upgrade Coordinating Nodes First
Coordinating nodes are safest to start with since they don't store data.

```bash
# Upgrade coordinating node pool
gcloud container node-pools upgrade coord-pool \
  --cluster=YOUR_CLUSTER_NAME \
  --zone=YOUR_ZONE \
  --node-version=1.32.x-gke.x

# Monitor the upgrade
kubectl get nodes -l node-type=coordinating -w

# Verify pods reschedule correctly
kubectl get pods -l component=elasticsearch-coord -o wide
```

### Phase 2: Upgrade Data Nodes (One by One)
This is the most critical phase. We'll use a rolling approach.

```bash
# First, ensure you have proper pod disruption budgets
kubectl apply -f - <<EOF
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: es-data-pdb
spec:
  minAvailable: 4  # Ensure at least 4 of 5 data nodes stay up
  selector:
    matchLabels:
      component: elasticsearch-data
EOF

# Upgrade data node pool with max-surge=1 and max-unavailable=1
gcloud container node-pools upgrade data-pool \
  --cluster=YOUR_CLUSTER_NAME \
  --zone=YOUR_ZONE \
  --node-version=1.32.x-gke.x \
  --max-surge-upgrade=1 \
  --max-unavailable-upgrade=1

# Monitor each node as it upgrades
watch 'kubectl get nodes -l node-type=data && echo "=== PODS ===" && kubectl get pods -l component=elasticsearch-data -o wide'
```

### Phase 3: Upgrade Master Nodes
Masters need special attention due to quorum requirements.

```bash
# Set up PDB for masters (allow only 1 to be down to maintain quorum)
kubectl apply -f - <<EOF
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: es-master-pdb
spec:
  minAvailable: 2  # Maintain quorum of 2 out of 3
  selector:
    matchLabels:
      component: elasticsearch-master
EOF

# Upgrade master node pool
gcloud container node-pools upgrade master-pool \
  --cluster=YOUR_CLUSTER_NAME \
  --zone=YOUR_ZONE \
  --node-version=1.32.x-gke.x \
  --max-surge-upgrade=1 \
  --max-unavailable-upgrade=1

# Monitor master election and cluster state
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/master?v"
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"
```

### Phase 4: Upgrade Control Plane
```bash
# Finally, upgrade the GKE control plane
gcloud container clusters upgrade YOUR_CLUSTER_NAME \
  --master \
  --zone=YOUR_ZONE \
  --cluster-version=1.32.x-gke.x
```

## Post-Upgrade Tasks

### 1. Re-enable Shard Allocation
```bash
# Re-enable full shard allocation
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" \
  -H "Content-Type: application/json" \
  -d '{
    "persistent": {
      "cluster.routing.allocation.enable": null
    }
  }'
```

### 2. Verify Cluster Health
```bash
# Check overall health
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?wait_for_status=green&timeout=30s&pretty"

# Verify all nodes are visible
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/nodes?v"

# Check shard distribution
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/shards?v&s=index,shard"
```

### 3. Performance Verification
```bash
# Test indexing and search performance
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/indices?v&s=store.size:desc"

# Check if any indices need attention
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/allocation/explain?pretty"
```

## Monitoring During Upgrade

Keep these commands running in separate terminals:

```bash
# Terminal 1: Node status
watch 'kubectl get nodes -o wide'

# Terminal 2: Pod status
watch 'kubectl get pods -l app=elasticsearch -o wide'

# Terminal 3: ES cluster health
watch 'kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health?pretty"'

# Terminal 4: Shard status
watch 'kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/shards?h=index,shard,prirep,state,node" | grep -v STARTED | head -20'
```

## Rollback Strategy

If issues arise:

```bash
# Rollback a specific node pool
gcloud container node-pools rollback POOL_NAME \
  --cluster=YOUR_CLUSTER_NAME \
  --zone=YOUR_ZONE

# Check if data recovery is needed
kubectl exec -it es-master-0 -- curl -X POST "localhost:9200/_cluster/reroute?retry_failed=true"
```

## Key Safety Points

1. **Never upgrade more than one master at a time** to maintain quorum
2. **Keep at least 80% of data nodes available** to maintain cluster stability  
3. **Monitor regional PD attachment** - pods may take longer to start due to disk attachment
4. **Verify StatefulSet pod ordering** - pods should come up in order (0, 1, 2, etc.)
5. **Check for split-brain scenarios** after master upgrades

The entire upgrade should take 1-2 hours depending on your cluster size and the time needed for regional PD reattachment. The key is patience and monitoring at each step.
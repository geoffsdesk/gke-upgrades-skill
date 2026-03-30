# GKE Elasticsearch Cluster Upgrade Plan (1.31 → 1.32)

## Cluster Configuration
- **Workload:** Elasticsearch StatefulSet (3 masters, 5 data, 2 coordinators)
- **Current:** GKE 1.31 → **Target:** 1.32
- **Storage:** Regional pd-ssd PVs (survive node replacement)
- **Mode:** Standard (full node pool control)

## Pre-Upgrade Checklist

### Elasticsearch Application Backup
```bash
# Create snapshot repository (if not already configured)
curl -X PUT "http://elasticsearch-service:9200/_snapshot/gcs_backup" -H 'Content-Type: application/json' -d'
{
  "type": "gcs",
  "settings": {
    "bucket": "your-backup-bucket",
    "base_path": "elasticsearch-snapshots"
  }
}'

# Take full cluster snapshot
curl -X PUT "http://elasticsearch-service:9200/_snapshot/gcs_backup/pre-upgrade-$(date +%Y%m%d)" -d'
{
  "indices": "*",
  "ignore_unavailable": true,
  "include_global_state": true
}'

# Verify snapshot completed successfully
curl -X GET "http://elasticsearch-service:9200/_snapshot/gcs_backup/_all"
```

### Cluster Health Verification
```bash
# Check cluster health
curl -X GET "http://elasticsearch-service:9200/_cluster/health?pretty"
# Must show: status: "green", relocating_shards: 0

# Verify all nodes are up
curl -X GET "http://elasticsearch-service:9200/_cat/nodes?v"

# Check for any stuck shards
curl -X GET "http://elasticsearch-service:9200/_cat/shards?h=index,shard,prirep,state,node&s=state" | grep -v STARTED
```

### Pod Disruption Budgets (Critical for Elasticsearch)
```bash
# Create/verify PDBs before upgrade
kubectl apply -f - <<EOF
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-master-pdb
  namespace: elasticsearch
spec:
  minAvailable: 2  # Allow 1 master to drain, keep quorum of 2
  selector:
    matchLabels:
      app: elasticsearch
      role: master
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-data-pdb
  namespace: elasticsearch
spec:
  minAvailable: 3  # Allow 2 data nodes to drain simultaneously
  selector:
    matchLabels:
      app: elasticsearch
      role: data
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-coordinator-pdb
  namespace: elasticsearch
spec:
  minAvailable: 1  # Keep at least 1 coordinator available
  selector:
    matchLabels:
      app: elasticsearch
      role: coordinator
EOF
```

### Version Compatibility Check
```bash
# Check available versions
gcloud container get-server-config --zone ZONE --format="yaml(validMasterVersions)"

# Verify no deprecated API usage
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Check current cluster info
gcloud container clusters describe CLUSTER_NAME --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"
```

## Upgrade Sequence (Control Plane → Coordinators → Data → Masters)

### Step 1: Control Plane Upgrade
```bash
# Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.X-gke.Y

# Wait for completion (10-15 minutes for regional clusters)
# Monitor: kubectl get pods -n kube-system
```

### Step 2: Coordinator Nodes (Lowest Risk First)
```bash
# Configure conservative surge settings for coordinators
gcloud container node-pools update coordinator-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade coordinator pool
gcloud container node-pools upgrade coordinator-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.X-gke.Y

# Monitor progress
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=coordinator-pool -o wide'

# Verify Elasticsearch can still serve queries
curl -X GET "http://elasticsearch-service:9200/_cluster/health"
```

### Step 3: Data Nodes (Shard Rebalancing Aware)
```bash
# Temporarily disable shard allocation to prevent unnecessary rebalancing
curl -X PUT "http://elasticsearch-service:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'

# Configure conservative surge for data nodes
gcloud container node-pools update data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade data pool
gcloud container node-pools upgrade data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.X-gke.Y

# Monitor data node upgrade
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=data-pool -o wide'

# Re-enable shard allocation after upgrade completes
curl -X PUT "http://elasticsearch-service:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "all"
  }
}'

# Wait for cluster to rebalance
curl -X GET "http://elasticsearch-service:9200/_cluster/health?wait_for_status=green&timeout=300s"
```

### Step 4: Master Nodes (Highest Risk Last)
```bash
# Masters are most critical - one at a time only
gcloud container node-pools update master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade master pool
gcloud container node-pools upgrade master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.X-gke.Y

# Monitor master upgrades closely
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=master-pool -o wide && echo "=== ES Cluster Status ===" && curl -s http://elasticsearch-service:9200/_cluster/health'
```

## Post-Upgrade Validation

### Cluster Health Check
```bash
# All nodes at target version
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE

# All pods running
kubectl get pods -n elasticsearch
kubectl get statefulsets -n elasticsearch

# Elasticsearch cluster health
curl -X GET "http://elasticsearch-service:9200/_cluster/health?pretty"
curl -X GET "http://elasticsearch-service:9200/_cat/nodes?v"
curl -X GET "http://elasticsearch-service:9200/_cat/shards?v" | grep -c STARTED
```

### Data Integrity Verification
```bash
# Verify all indices are healthy
curl -X GET "http://elasticsearch-service:9200/_cat/indices?v&health=red"
# Should return no red indices

# Test search functionality
curl -X GET "http://elasticsearch-service:9200/_search?q=*&size=1&pretty"

# Check document counts match pre-upgrade baseline
curl -X GET "http://elasticsearch-service:9200/_cat/count/*?v"
```

### Performance Validation
```bash
# Monitor query latency (compare to pre-upgrade baseline)
curl -X GET "http://elasticsearch-service:9200/_nodes/stats/indices/search"

# Check for any memory/CPU pressure
kubectl top nodes
kubectl top pods -n elasticsearch
```

## Rollback Plan (If Needed)

### For Node Pools Only (Control Plane Cannot Rollback)
```bash
# Create new node pool at previous version
gcloud container node-pools create POOL_NAME-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --node-version 1.31.X-gke.Y \
  --num-nodes NUM_NODES \
  --machine-type MACHINE_TYPE

# Cordon upgraded pool
kubectl cordon -l cloud.google.com/gke-nodepool=POOL_NAME

# Allow Elasticsearch to drain naturally
# PVs will reattach to new nodes automatically
```

## Key Elasticsearch-Specific Considerations

1. **Upgrade Order:** Coordinators → Data → Masters (risk-ascending order)
2. **Shard Allocation:** Disable during data node upgrades to prevent unnecessary rebalancing
3. **Master Quorum:** PDB ensures 2/3 masters always available (no split-brain)
4. **Storage Safety:** Regional PVs survive node replacement automatically
5. **Conservative Settings:** `maxSurge=1, maxUnavailable=0` for all pools to minimize disruption
6. **Extended Grace Period:** Elasticsearch pods may need `terminationGracePeriodSeconds: 120` for proper shutdown

## Timeline Estimate
- Control plane: 10-15 minutes
- Coordinator pool: 15-30 minutes
- Data pool: 30-60 minutes (depends on shard rebalancing)  
- Master pool: 20-30 minutes
- **Total:** ~2-3 hours including validation

## Monitoring During Upgrade
```bash
# Watch this command throughout the upgrade
watch 'echo "=== Node Status ===" && kubectl get nodes -o wide && echo "=== ES Health ===" && curl -s http://elasticsearch-service:9200/_cluster/health | jq .'
```

This plan prioritizes data safety and availability by leveraging PDBs, conservative surge settings, proper upgrade sequencing, and Elasticsearch-aware shard management. The regional PVs ensure your data survives node replacement seamlessly.
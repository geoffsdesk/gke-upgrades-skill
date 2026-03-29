# GKE Upgrade Plan: Elasticsearch Cluster (1.31 → 1.32)

## Cluster Overview
- **Current**: GKE 1.31 → **Target**: GKE 1.32 (single minor version jump ✓)
- **Workload**: Elasticsearch StatefulSet with 3 masters, 5 data, 2 coordinating nodes
- **Storage**: Regional pd-ssd PVs (survives node replacement ✓)
- **Node pools**: Separate pools for each Elasticsearch role

## Pre-Upgrade Preparation

### 1. Elasticsearch-Specific Readiness

```bash
# Check Elasticsearch cluster health
kubectl exec -it es-master-0 -n elasticsearch -- curl -X GET "localhost:9200/_cluster/health?pretty"
# Should show: status: "green", number_of_nodes: 10

# Disable shard allocation (prevents rebalancing during upgrade)
kubectl exec -it es-master-0 -n elasticsearch -- curl -X PUT "localhost:9200/_cluster/settings" \
  -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'

# Take snapshot backup
kubectl exec -it es-master-0 -n elasticsearch -- curl -X PUT "localhost:9200/_snapshot/backup/pre-upgrade-$(date +%Y%m%d)" \
  -H 'Content-Type: application/json' -d'
{
  "indices": "*",
  "ignore_unavailable": true,
  "include_global_state": true
}'
```

### 2. Configure PDBs for Safe Drain

```yaml
# pdb-elasticsearch-masters.yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-master-pdb
  namespace: elasticsearch
spec:
  minAvailable: 2  # Protects quorum (2 out of 3 masters)
  selector:
    matchLabels:
      app: elasticsearch
      role: master
---
# pdb-elasticsearch-data.yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-data-pdb
  namespace: elasticsearch
spec:
  minAvailable: 4  # Protects data availability (4 out of 5 data nodes)
  selector:
    matchLabels:
      app: elasticsearch
      role: data
---
# pdb-elasticsearch-coordinating.yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-coordinating-pdb
  namespace: elasticsearch
spec:
  minAvailable: 1  # Keeps at least 1 coordinator available
  selector:
    matchLabels:
      app: elasticsearch
      role: coordinating
```

```bash
kubectl apply -f pdb-elasticsearch-masters.yaml
kubectl apply -f pdb-elasticsearch-data.yaml
kubectl apply -f pdb-elasticsearch-coordinating.yaml
```

### 3. Verify PV Reclaim Policy

```bash
kubectl get pv -o custom-columns=NAME:.metadata.name,RECLAIM:.spec.persistentVolumeReclaimPolicy | grep -v Retain
# Any non-Retain volumes are at risk - change them:
kubectl patch pv PV_NAME -p '{"spec":{"persistentVolumeReclaimPolicy":"Retain"}}'
```

## Upgrade Execution

### Phase 1: Control Plane Upgrade

```bash
# Check available versions
gcloud container get-server-config --zone us-central1-a --format="yaml(channels)"

# Upgrade control plane (10-15 minutes)
gcloud container clusters upgrade elasticsearch-cluster \
  --zone us-central1-a \
  --master \
  --cluster-version 1.32.0-gke.1200

# Verify
gcloud container clusters describe elasticsearch-cluster \
  --zone us-central1-a \
  --format="value(currentMasterVersion)"
```

### Phase 2: Node Pool Upgrades (Conservative Strategy)

**Upgrade order**: Coordinating → Data → Masters (least critical to most critical)

#### Step 1: Coordinating Nodes (Lowest Risk)

```bash
# Configure conservative surge settings
gcloud container node-pools update elasticsearch-coordinating \
  --cluster elasticsearch-cluster \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade
gcloud container node-pools upgrade elasticsearch-coordinating \
  --cluster elasticsearch-cluster \
  --zone us-central1-a \
  --cluster-version 1.32.0-gke.1200

# Monitor progress
watch 'kubectl get nodes -l nodepool=elasticsearch-coordinating -o wide'

# Verify Elasticsearch sees all nodes
kubectl exec -it es-master-0 -n elasticsearch -- curl -X GET "localhost:9200/_cat/nodes?v"
```

#### Step 2: Data Nodes (Medium Risk - Contains Your Data)

```bash
# Configure conservative settings (one-at-a-time)
gcloud container node-pools update elasticsearch-data \
  --cluster elasticsearch-cluster \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Re-enable shard allocation before upgrading data nodes
kubectl exec -it es-master-0 -n elasticsearch -- curl -X PUT "localhost:9200/_cluster/settings" \
  -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "all"
  }
}'

# Upgrade data pool
gcloud container node-pools upgrade elasticsearch-data \
  --cluster elasticsearch-cluster \
  --zone us-central1-a \
  --cluster-version 1.32.0-gke.1200

# Monitor Elasticsearch health during upgrade
watch 'kubectl exec -it es-master-0 -n elasticsearch -- curl -s "localhost:9200/_cluster/health" | jq .'
```

**Expected during data node upgrade**: 
- Cluster status may briefly show `yellow` as shards rebalance
- Should return to `green` after each node upgrade completes

#### Step 3: Master Nodes (Highest Risk - Controls Cluster State)

```bash
# Configure ultra-conservative settings
gcloud container node-pools update elasticsearch-master \
  --cluster elasticsearch-cluster \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade master pool
gcloud container node-pools upgrade elasticsearch-master \
  --cluster elasticsearch-cluster \
  --zone us-central1-a \
  --cluster-version 1.32.0-gke.1200

# Monitor master election during upgrade
watch 'kubectl exec -it es-master-0 -n elasticsearch -- curl -s "localhost:9200/_cat/master?v"'
```

## Validation & Cleanup

### 1. Verify Elasticsearch Cluster Health

```bash
# Check all nodes present and healthy
kubectl exec -it es-master-0 -n elasticsearch -- curl -X GET "localhost:9200/_cat/nodes?v&h=name,node.role,master,heap.percent,cpu,load_1m"

# Verify cluster health is green
kubectl exec -it es-master-0 -n elasticsearch -- curl -X GET "localhost:9200/_cluster/health?pretty"

# Check shard allocation
kubectl exec -it es-master-0 -n elasticsearch -- curl -X GET "localhost:9200/_cat/shards?v&h=index,shard,prirep,state,unassigned.reason"
```

### 2. Verify All Nodes Upgraded

```bash
gcloud container node-pools list --cluster elasticsearch-cluster --zone us-central1-a
kubectl get nodes -o wide
```

### 3. Application Testing

```bash
# Test indexing
kubectl exec -it es-master-0 -n elasticsearch -- curl -X POST "localhost:9200/test-upgrade/_doc/" \
  -H 'Content-Type: application/json' -d'{"timestamp":"'$(date -Iseconds)'","test":"post-upgrade"}'

# Test search
kubectl exec -it es-master-0 -n elasticsearch -- curl -X GET "localhost:9200/test-upgrade/_search?pretty"

# Clean up test
kubectl exec -it es-master-0 -n elasticsearch -- curl -X DELETE "localhost:9200/test-upgrade"
```

### 4. Cleanup

```bash
# Remove PDBs if they were temporary
kubectl delete pdb elasticsearch-master-pdb elasticsearch-data-pdb elasticsearch-coordinating-pdb -n elasticsearch

# Take final snapshot
kubectl exec -it es-master-0 -n elasticsearch -- curl -X PUT "localhost:9200/_snapshot/backup/post-upgrade-$(date +%Y%m%d)"
```

## Rollback Plan (If Needed)

If issues arise after the upgrade:

```bash
# 1. Check what's failing
kubectl get pods -n elasticsearch
kubectl logs -f es-master-0 -n elasticsearch

# 2. Restore from snapshot if data corruption
kubectl exec -it es-master-0 -n elasticsearch -- curl -X POST "localhost:9200/_snapshot/backup/pre-upgrade-YYYYMMDD/_restore" \
  -H 'Content-Type: application/json' -d'{"indices":"*","ignore_unavailable":true}'

# 3. Node pool rollback requires creating new pools at old version
gcloud container node-pools create elasticsearch-data-rollback \
  --cluster elasticsearch-cluster \
  --zone us-central1-a \
  --cluster-version 1.31.x-gke.xxxx \
  --num-nodes 5

# Then migrate workloads manually
```

## Key Safeguards in This Plan

1. **PDBs protect quorum**: Masters (2/3), Data (4/5) always available
2. **Conservative surge**: `maxSurge=1, maxUnavailable=0` prevents multiple simultaneous drains
3. **Upgrade sequence**: Coordinating → Data → Masters (risk ascending)
4. **Regional PVs**: Data survives node replacement
5. **Pre/post snapshots**: Full backup before and validation after
6. **Shard allocation control**: Prevents unnecessary rebalancing during coordinating node upgrade

**Estimated total time**: 2-3 hours (15 min CP + ~45 min per node pool)

The key insight for Elasticsearch is that masters are your most critical component - upgrade them last, one at a time, with maximum protection. Regional PVs mean your data is safe during node replacement, but the cluster state and quorum management requires careful sequencing.
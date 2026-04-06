# GKE Upgrade Plan: Elasticsearch Cluster (1.31 → 1.32)

## Cluster Overview
- **Current**: GKE 1.31 → **Target**: 1.32 
- **Workload**: Elasticsearch StatefulSets (3 masters, 5 data, 2 coordinating nodes)
- **Storage**: Regional PD-SSD (survives node replacement)
- **Cluster mode**: Standard

## Pre-Upgrade Checklist

### Elasticsearch-Specific Preparation

```bash
# 1. Disable shard allocation (prevents rebalancing during upgrade)
curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'

# 2. Stop indexing temporarily (coordinate with application teams)
curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "transient": {
    "cluster.routing.allocation.enable": "none"
  }
}'

# 3. Perform synced flush
curl -X POST "localhost:9200/_flush/synced"

# 4. Take cluster snapshot backup
curl -X PUT "localhost:9200/_snapshot/gcs-backup/pre-upgrade-$(date +%Y%m%d)" -H 'Content-Type: application/json' -d'
{
  "indices": "*",
  "ignore_unavailable": true,
  "include_global_state": true
}'
```

### Configure PDBs for Elasticsearch

**Master nodes PDB (protect quorum):**
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-master-pdb
  namespace: elasticsearch
spec:
  minAvailable: 2  # Allows 1 master to drain while 2 maintain quorum
  selector:
    matchLabels:
      app: elasticsearch
      role: master
```

**Data nodes PDB (conservative):**
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-data-pdb
  namespace: elasticsearch
spec:
  minAvailable: 4  # Allows 1 data node to drain at a time
  selector:
    matchLabels:
      app: elasticsearch
      role: data
```

**Coordinating nodes PDB:**
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-coordinating-pdb
  namespace: elasticsearch
spec:
  minAvailable: 1  # Keeps 1 coordinator available
  selector:
    matchLabels:
      app: elasticsearch
      role: coordinating
```

Apply PDBs:
```bash
kubectl apply -f elasticsearch-pdbs.yaml
```

### Verify Current State

```bash
# Check cluster health
curl -X GET "localhost:9200/_cluster/health?pretty"
# Should show: status: green, number_of_nodes: 10

# Check node pools and versions
gcloud container node-pools list --cluster CLUSTER_NAME --region REGION

# Check PV reclaim policy (should be Retain)
kubectl get pv -o custom-columns=NAME:.metadata.name,RECLAIM:.spec.persistentVolumeReclaimPolicy | grep elasticsearch
```

## Upgrade Strategy

**Recommended approach**: Surge upgrade with conservative settings to minimize risk to stateful data.

### Node Pool Upgrade Settings

```bash
# Configure conservative surge settings for all pools
gcloud container node-pools update es-master-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

gcloud container node-pools update es-data-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

gcloud container node-pools update es-coordinating-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

## Step-by-Step Upgrade Process

### Phase 1: Control Plane Upgrade

```bash
# 1. Upgrade control plane
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version 1.32

# 2. Verify control plane (wait ~10-15 minutes)
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="value(currentMasterVersion)"

# Should show: 1.32.x-gke.xxxx
```

### Phase 2: Node Pool Upgrades (Order Matters)

**Upgrade order: Coordinating → Data → Masters (least critical to most critical)**

#### Step 1: Coordinating Nodes (Lowest Risk)

```bash
# Upgrade coordinating pool
gcloud container node-pools upgrade es-coordinating-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.32

# Monitor progress
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=es-coordinating-pool -o wide'

# Verify Elasticsearch sees all nodes
curl -X GET "localhost:9200/_cat/nodes?v"
```

#### Step 2: Data Nodes (Medium Risk - PVs Preserve Data)

```bash
# Upgrade data pool
gcloud container node-pools upgrade es-data-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.32

# Monitor data node replacement (this will take longest)
watch 'kubectl get pods -n elasticsearch -l role=data -o wide'

# Verify all data pods return to Running
kubectl get statefulset elasticsearch-data -n elasticsearch
```

**During data node upgrade:**
- Regional PD-SSD volumes will reattach to new nodes automatically
- Elasticsearch will show nodes leaving/joining the cluster
- Cluster status may briefly show yellow during node replacement

#### Step 3: Master Nodes (Highest Risk - Upgrade One at a Time)

```bash
# Upgrade master pool (PDB ensures only 1 master drains at a time)
gcloud container node-pools upgrade es-master-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.32

# Monitor master node replacement closely
watch 'kubectl get pods -n elasticsearch -l role=master -o wide'

# Verify quorum maintained during upgrade
curl -X GET "localhost:9200/_cluster/health?pretty"
# Should never drop below 2 master nodes
```

## Post-Upgrade Restoration

### Re-enable Elasticsearch Operations

```bash
# 1. Re-enable shard allocation
curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": null
  },
  "transient": {
    "cluster.routing.allocation.enable": null
  }
}'

# 2. Wait for cluster to return to green
watch 'curl -s localhost:9200/_cluster/health | jq .status'

# 3. Resume indexing (coordinate with application teams)
```

## Validation Checklist

```bash
# ✓ All nodes at target version
kubectl get nodes -o wide

# ✓ All Elasticsearch pods running
kubectl get pods -n elasticsearch

# ✓ Cluster health green with all nodes
curl -X GET "localhost:9200/_cluster/health?pretty"
curl -X GET "localhost:9200/_cat/nodes?v"

# ✓ All indices available
curl -X GET "localhost:9200/_cat/indices?v"

# ✓ Perform test query
curl -X GET "localhost:9200/_search?pretty" -H 'Content-Type: application/json' -d'
{
  "query": { "match_all": {} },
  "size": 1
}'

# ✓ PVs still attached correctly
kubectl get pvc -n elasticsearch
kubectl get pv | grep elasticsearch
```

## Rollback Plan (If Needed)

If critical issues arise:

```bash
# 1. Cordon nodes at new version
kubectl cordon -l kubernetes.io/version=v1.32.x

# 2. Create new node pools at 1.31
gcloud container node-pools create es-master-pool-rollback \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.31.x-gke.xxxx \
  --num-nodes 1 \
  --machine-type MACHINE_TYPE

# 3. Let StatefulSets reschedule to old version nodes
# 4. Regional PVs will reattach automatically
```

## Expected Timeline

- **Control plane**: 10-15 minutes
- **Coordinating nodes**: 15-20 minutes (2 nodes)
- **Data nodes**: 45-60 minutes (5 nodes, largest pool)
- **Master nodes**: 20-30 minutes (3 nodes, most critical)
- **Total estimated time**: 2-2.5 hours

## Key Safety Features

1. **PDBs protect quorum**: Only 1 master can be down at a time
2. **Regional PD-SSD**: Data persists through node replacement
3. **Conservative surge settings**: `maxSurge=1` minimizes concurrent disruption
4. **Upgrade order**: Least critical (coordinating) to most critical (masters)
5. **Backup available**: Pre-upgrade snapshot for disaster recovery

The regional PD-SSD volumes are the key to this being safe - your data persists through node replacement, and Elasticsearch will handle the temporary node unavailability as long as we respect the PDBs.
# Elasticsearch Cluster Upgrade Plan: 1.31 → 1.32

## Overview
- **Cluster**: StatefulSet-based Elasticsearch on GKE Standard
- **Current version**: 1.31
- **Target version**: 1.32
- **Architecture**: 3 masters, 5 data nodes, 2 coordinators (separate node pools)
- **Storage**: Regional PD-SSD PVs

## Pre-Upgrade Checklist

### Elasticsearch-Specific Preparation
- [ ] **Take application-level snapshot** using Elasticsearch `_snapshot` API:
  ```bash
  curl -X PUT "localhost:9200/_snapshot/my_backup/pre_upgrade_snapshot?wait_for_completion=true"
  ```
- [ ] **Disable shard allocation** to prevent rebalancing during upgrade:
  ```bash
  curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
  {
    "persistent": {
      "cluster.routing.allocation.enable": "primaries"
    }
  }'
  ```
- [ ] **Verify cluster health is GREEN**:
  ```bash
  curl -X GET "localhost:9200/_cluster/health?pretty"
  ```
- [ ] **Check for unassigned shards**:
  ```bash
  curl -X GET "localhost:9200/_cat/shards?h=index,shard,prirep,state,unassigned.reason&v"
  ```

### GKE-Specific Preparation
- [ ] **Verify PV reclaim policy is `Retain`**:
  ```bash
  kubectl get pv -o custom-columns=NAME:.metadata.name,RECLAIM:.spec.persistentVolumeReclaimPolicy | grep -v Retain
  ```
- [ ] **Configure PDBs for each StatefulSet** (critical for Elasticsearch):
  ```yaml
  # Master nodes PDB
  apiVersion: policy/v1
  kind: PodDisruptionBudget
  metadata:
    name: elasticsearch-master-pdb
  spec:
    minAvailable: 2  # Allow 1 master to drain, keep quorum of 2
    selector:
      matchLabels:
        app: elasticsearch
        role: master
  
  # Data nodes PDB
  apiVersion: policy/v1
  kind: PodDisruptionBudget
  metadata:
    name: elasticsearch-data-pdb
  spec:
    minAvailable: 3  # Keep majority of data nodes
    selector:
      matchLabels:
        app: elasticsearch
        role: data
  
  # Coordinator nodes PDB
  apiVersion: policy/v1
  kind: PodDisruptionBudget
  metadata:
    name: elasticsearch-coordinator-pdb
  spec:
    minAvailable: 1  # Keep at least 1 coordinator
    selector:
      matchLabels:
        app: elasticsearch
        role: coordinator
  ```
- [ ] **Set conservative surge settings** for all node pools:
  ```bash
  # For all Elasticsearch node pools: one-at-a-time replacement
  for POOL in elasticsearch-masters elasticsearch-data elasticsearch-coordinators; do
    gcloud container node-pools update $POOL \
      --cluster CLUSTER_NAME \
      --zone ZONE \
      --max-surge-upgrade 1 \
      --max-unavailable-upgrade 0
  done
  ```

## Upgrade Execution Steps

### Phase 1: Control Plane Upgrade

```bash
# 1. Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32

# 2. Wait for completion and verify
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"

# 3. Check system pods
kubectl get pods -n kube-system
```

### Phase 2: Node Pool Upgrades (Sequential Order)

**Order is critical for Elasticsearch**: Coordinators → Data → Masters (least to most critical)

#### Step 1: Upgrade Coordinator Nodes First
```bash
# Coordinators are stateless and lowest risk
gcloud container node-pools upgrade elasticsearch-coordinators \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor progress
watch 'kubectl get nodes -l nodepool=elasticsearch-coordinators -o wide'
```

**Validation after coordinators:**
```bash
# Check Elasticsearch cluster health
curl -X GET "localhost:9200/_cluster/health?pretty"

# Verify all coordinator pods are running
kubectl get pods -l role=coordinator
```

#### Step 2: Upgrade Data Nodes
```bash
gcloud container node-pools upgrade elasticsearch-data \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor progress (this will take longest due to PDB)
watch 'kubectl get nodes -l nodepool=elasticsearch-data -o wide'
```

**Critical monitoring during data node upgrade:**
```bash
# Watch for PDB violations in Cloud Logging or via events
kubectl get events -n elasticsearch --sort-by='.lastTimestamp' | grep -i pdb

# Monitor shard allocation
curl -X GET "localhost:9200/_cat/shards?h=index,shard,prirep,state,node&v"

# Check cluster health frequently
curl -X GET "localhost:9200/_cluster/health?level=shards&pretty"
```

#### Step 3: Upgrade Master Nodes Last
```bash
# Masters are most critical - upgrade last
gcloud container node-pools upgrade elasticsearch-masters \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor master election process
watch 'kubectl get pods -l role=master'
```

**Critical monitoring during master upgrade:**
```bash
# Watch for master election
curl -X GET "localhost:9200/_cat/master?v"

# Verify quorum maintained (should always show 2 of 3 masters available)
curl -X GET "localhost:9200/_cluster/health?pretty" | grep number_of_nodes
```

## Post-Upgrade Validation

### GKE Cluster Health
```bash
# Verify all nodes upgraded
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE

# Check all nodes Ready
kubectl get nodes

# Verify no stuck pods
kubectl get pods -A | grep -v Running | grep -v Completed
```

### Elasticsearch Cluster Health
```bash
# 1. Re-enable shard allocation
curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": null
  }
}'

# 2. Wait for GREEN status
curl -X GET "localhost:9200/_cluster/health?wait_for_status=green&timeout=10m&pretty"

# 3. Verify all shards allocated
curl -X GET "localhost:9200/_cat/shards?h=index,shard,prirep,state&v" | grep -v STARTED

# 4. Check master election stable
curl -X GET "localhost:9200/_cat/master?v"

# 5. Test search functionality
curl -X GET "localhost:9200/_search?pretty"

# 6. Verify data integrity with document count
curl -X GET "localhost:9200/_cat/indices?v&h=index,docs.count"
```

## Rollback Plan (Emergency Only)

If Elasticsearch cluster becomes unhealthy:

### Option 1: Restore from Snapshot
```bash
# 1. Stop indexing to cluster
# 2. Restore pre-upgrade snapshot
curl -X POST "localhost:9200/_snapshot/my_backup/pre_upgrade_snapshot/_restore"

# 3. Wait for restore completion
curl -X GET "localhost:9200/_snapshot/my_backup/pre_upgrade_snapshot/_status"
```

### Option 2: Node Pool Rollback (Complex)
```bash
# Create new node pool at 1.31 for the affected tier
gcloud container node-pools create elasticsearch-data-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31 \
  --machine-type n2-standard-4 \
  --num-nodes 5

# Cordon upgraded nodes and migrate StatefulSet
kubectl cordon -l nodepool=elasticsearch-data
```

## Timeline Expectations

- **Control plane**: ~10-15 minutes
- **Coordinator nodes**: ~20-30 minutes (2 nodes, low complexity)
- **Data nodes**: ~2-3 hours (5 nodes, PDB constraints, data safety)
- **Master nodes**: ~45-60 minutes (3 nodes, master election complexity)
- **Total upgrade window**: ~4-5 hours

## Key Safety Measures

1. **PDBs protect quorum** - Masters maintain 2/3 availability, data nodes maintain majority
2. **One-at-a-time replacement** - `maxSurge=1, maxUnavailable=0` prevents multiple simultaneous disruptions
3. **Shard allocation disabled** - Prevents unnecessary data movement during upgrade
4. **Application-level backup** - Full snapshot before any changes
5. **Sequential upgrade order** - Least critical (coordinators) to most critical (masters)
6. **Regional PD-SSD** - Storage survives node replacement automatically

This approach prioritizes **data safety and availability** over upgrade speed. The conservative settings and sequential order ensure your Elasticsearch cluster maintains quorum and data integrity throughout the upgrade process.
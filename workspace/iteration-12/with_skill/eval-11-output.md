# GKE Upgrade Plan: Elasticsearch Cluster (1.31 → 1.32)

## Cluster Overview
- **Mode:** Standard
- **Current:** 1.31 → **Target:** 1.32
- **Topology:** 3 masters + 5 data + 2 coordinating nodes (separate pools)
- **Storage:** Regional pd-ssd PVs
- **Critical requirements:** Zero data loss, maintain availability

## Pre-Upgrade Checklist

### Elasticsearch-Specific Preparation
```bash
# 1. Check cluster health
curl -X GET "localhost:9200/_cluster/health?pretty"
# Must be GREEN before proceeding

# 2. Disable shard allocation (prevents rebalancing during upgrade)
curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'

# 3. Perform synced flush
curl -X POST "localhost:9200/_flush/synced?pretty"

# 4. Back up cluster state and indices
curl -X PUT "localhost:9200/_snapshot/backup_repo/pre_upgrade_snapshot?wait_for_completion=true&pretty"
```

### GKE Compatibility Checks
```bash
# Verify target version available
gcloud container get-server-config --zone ZONE --format="yaml(channels)"

# Check for deprecated API usage
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Verify PV reclaim policies
kubectl get pv -o custom-columns=NAME:.metadata.name,RECLAIM:.spec.persistentVolumeReclaimPolicy | grep elasticsearch
```

### PDB Configuration
```yaml
# Ensure restrictive PDBs for each component
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-master-pdb
spec:
  minAvailable: 2  # Keep quorum (2 of 3)
  selector:
    matchLabels:
      app: elasticsearch
      role: master
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-data-pdb
spec:
  minAvailable: 4  # Keep most data nodes (4 of 5)
  selector:
    matchLabels:
      app: elasticsearch
      role: data
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-coordinating-pdb
spec:
  minAvailable: 1  # Keep at least 1 coordinator (1 of 2)
  selector:
    matchLabels:
      app: elasticsearch
      role: coordinating
```

## Upgrade Strategy

### Node Pool Upgrade Settings (Conservative for Stateful Workloads)
```bash
# Configure conservative surge settings for all pools
# Master nodes: 1 at a time, zero extra capacity
gcloud container node-pools update elasticsearch-master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Data nodes: 1 at a time, zero extra capacity  
gcloud container node-pools update elasticsearch-data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Coordinating nodes: 1 at a time, zero extra capacity
gcloud container node-pools update elasticsearch-coordinating-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

## Step-by-Step Upgrade Execution

### Step 1: Control Plane Upgrade
```bash
# Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32

# Monitor progress (~10-15 minutes)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"

# Verify system pods healthy
kubectl get pods -n kube-system
```

### Step 2: Coordinating Nodes (Least Critical)
```bash
# Start with coordinating pool - these handle client requests but no data
gcloud container node-pools upgrade elasticsearch-coordinating-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor Elasticsearch health after each node
watch 'curl -s "localhost:9200/_cluster/health" | jq'

# Verify coordinating pods rescheduled
kubectl get pods -l role=coordinating -o wide
```

**Wait for GREEN cluster status before proceeding.**

### Step 3: Master Nodes (Maintain Quorum)
```bash
# Upgrade master pool - PDB ensures 2/3 masters stay available
gcloud container node-pools upgrade elasticsearch-master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Critical: Monitor master quorum throughout
watch 'curl -s "localhost:9200/_cat/master" && curl -s "localhost:9200/_cluster/health"'

# Verify all masters rejoin cluster
kubectl get pods -l role=master -o wide
```

**Wait for GREEN cluster status and stable master election before proceeding.**

### Step 4: Data Nodes (Most Critical)
```bash
# Upgrade data pool last - PDB keeps 4/5 data nodes available
gcloud container node-pools upgrade elasticsearch-data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor shard health closely
watch 'curl -s "localhost:9200/_cluster/health" | jq && kubectl get pods -l role=data'

# Check PV attachment after each data node restart
kubectl get pvc -A | grep elasticsearch
```

### Step 5: Post-Upgrade Recovery
```bash
# Re-enable shard allocation
curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": null
  }
}'

# Wait for cluster to fully recover
watch 'curl -s "localhost:9200/_cluster/health"'

# Verify all shards allocated
curl -X GET "localhost:9200/_cat/shards?v&h=index,shard,prirep,state,node"
```

## Validation Checklist

```bash
# Cluster versions
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE

# All nodes at 1.32
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion

# Elasticsearch cluster GREEN
curl -X GET "localhost:9200/_cluster/health?pretty"

# All indices healthy  
curl -X GET "localhost:9200/_cat/indices?v&health=green"

# PVs still bound
kubectl get pvc -A | grep elasticsearch | grep Bound

# Data integrity check
curl -X GET "localhost:9200/_cat/count?v"
```

## Rollback Plan (If Needed)

If Elasticsearch cluster becomes unhealthy during upgrade:

```bash
# 1. Stop the upgrade operation
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE
# Note: Cannot cancel mid-node, but can prevent next nodes

# 2. Re-enable allocation immediately
curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": null
  }
}'

# 3. Restore from snapshot if data corruption
curl -X POST "localhost:9200/_snapshot/backup_repo/pre_upgrade_snapshot/_restore?pretty"

# 4. Create new node pools at 1.31 if needed
gcloud container node-pools create elasticsearch-data-pool-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x \
  --num-nodes 5 \
  --machine-type n1-standard-4
```

## Risk Mitigation

- **Regional PVs:** Your pd-ssd volumes can reattach to nodes in any zone - ✅ Good
- **PDB Protection:** Conservative settings prevent simultaneous node loss - ✅ 
- **Quorum Preserved:** Master PDB maintains 2/3 availability - ✅
- **Gradual Approach:** Coordinating → Masters → Data reduces blast radius - ✅
- **Shard Allocation Control:** Prevents unnecessary data movement during upgrade - ✅

## Timeline Estimate

- Control plane: ~15 minutes
- Coordinating pool: ~20 minutes (2 nodes × ~10 min each)
- Master pool: ~30 minutes (3 nodes × ~10 min each)  
- Data pool: ~50 minutes (5 nodes × ~10 min each)
- **Total: ~2 hours**

Schedule during low-traffic period. The cluster will remain available throughout, but performance may be reduced as nodes restart.
# GKE Upgrade Plan: Elasticsearch Cluster (1.31 → 1.32)

## Cluster Overview
- **Workload:** Elasticsearch StatefulSet cluster
- **Architecture:** 3 masters, 5 data nodes, 2 coordinators (separate node pools)
- **Storage:** Regional pd-ssd PVs
- **Current:** GKE 1.31 → **Target:** GKE 1.32
- **Mode:** Standard (node pool upgrade strategy required)

## Pre-Upgrade Checklist

```markdown
Pre-Upgrade Checklist - Elasticsearch on GKE
- [ ] Cluster health green: `curl -X GET "http://ELASTICSEARCH_SERVICE:9200/_cluster/health"`
- [ ] All shards allocated: `curl -X GET "http://ELASTICSEARCH_SERVICE:9200/_cat/shards?v&h=index,shard,prirep,state"`
- [ ] Elasticsearch snapshot completed and verified
- [ ] PV reclaim policies set to `Retain`: `kubectl get pv -o custom-columns=NAME:.metadata.name,RECLAIM:.spec.persistentVolumeReclaimPolicy`
- [ ] PDBs configured for each StatefulSet (recommended: masters minAvailable=2, data minAvailable=3, coordinators minAvailable=1)
- [ ] No deprecated APIs in use: `kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated`
- [ ] GKE 1.32 release notes reviewed for Elasticsearch compatibility
- [ ] Surge settings planned per node pool (conservative for stateful workloads)
```

## Elasticsearch-Specific PDB Configuration

Before upgrading, ensure proper PDBs protect quorum:

```bash
# Master nodes PDB (allows 1 master to drain, keeps quorum of 2)
kubectl apply -f - <<EOF
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-master-pdb
  namespace: elasticsearch
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: elasticsearch
      role: master
EOF

# Data nodes PDB (allows 2 data nodes to drain, keeps majority)
kubectl apply -f - <<EOF
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-data-pdb
  namespace: elasticsearch
spec:
  minAvailable: 3
  selector:
    matchLabels:
      app: elasticsearch
      role: data
EOF

# Coordinator nodes PDB (allows 1 coordinator to drain)
kubectl apply -f - <<EOF
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-coordinator-pdb
  namespace: elasticsearch
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: elasticsearch
      role: coordinator
EOF
```

## Pre-Upgrade Elasticsearch Backup

**Critical:** Take an Elasticsearch snapshot before starting:

```bash
# Create snapshot repository (if not exists)
curl -X PUT "http://ELASTICSEARCH_SERVICE:9200/_snapshot/backup_repository" -H 'Content-Type: application/json' -d'
{
  "type": "gcs",
  "settings": {
    "bucket": "YOUR_GCS_BUCKET",
    "base_path": "elasticsearch_snapshots"
  }
}'

# Create pre-upgrade snapshot
curl -X PUT "http://ELASTICSEARCH_SERVICE:9200/_snapshot/backup_repository/pre_upgrade_$(date +%Y%m%d_%H%M%S)" -H 'Content-Type: application/json' -d'
{
  "indices": "*",
  "ignore_unavailable": true,
  "include_global_state": true
}'

# Verify snapshot completion
curl -X GET "http://ELASTICSEARCH_SERVICE:9200/_snapshot/backup_repository/_current"
```

## Upgrade Runbook

### Phase 1: Control Plane Upgrade

```bash
# Check current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Upgrade control plane (10-15 minutes)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32

# Verify control plane
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"

# Ensure system pods are healthy
kubectl get pods -n kube-system
```

### Phase 2: Node Pool Upgrades (Conservative Strategy)

**Important:** Upgrade coordinator nodes → data nodes → master nodes (reverse order of criticality).

#### Step 1: Coordinator Nodes (Lowest Risk)

```bash
# Configure conservative surge settings
gcloud container node-pools update elasticsearch-coordinator-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade coordinator pool
gcloud container node-pools upgrade elasticsearch-coordinator-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor progress and cluster health
watch 'kubectl get nodes -l node-role=coordinator -o wide'
curl -X GET "http://ELASTICSEARCH_SERVICE:9200/_cluster/health"
```

Wait for coordinator upgrade to complete and verify cluster health before proceeding.

#### Step 2: Data Nodes (Medium Risk)

```bash
# Configure conservative surge for data nodes
gcloud container node-pools update elasticsearch-data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade data pool
gcloud container node-pools upgrade elasticsearch-data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor data node replacement and shard allocation
watch 'kubectl get nodes -l node-role=data -o wide'
curl -X GET "http://ELASTICSEARCH_SERVICE:9200/_cat/allocation?v"
curl -X GET "http://ELASTICSEARCH_SERVICE:9200/_cluster/health?wait_for_status=green&timeout=10m"
```

**Critical:** Wait for cluster status to return to GREEN and all shards to be allocated before proceeding to masters.

#### Step 3: Master Nodes (Highest Risk - Most Conservative)

```bash
# Configure most conservative settings for masters
gcloud container node-pools update elasticsearch-master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade master pool
gcloud container node-pools upgrade elasticsearch-master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor master election and cluster stability
watch 'kubectl get nodes -l node-role=master -o wide'
curl -X GET "http://ELASTICSEARCH_SERVICE:9200/_cluster/health"
curl -X GET "http://ELASTICSEARCH_SERVICE:9200/_cat/master?v"
```

## Monitoring During Upgrade

Run these commands throughout the upgrade to ensure Elasticsearch remains stable:

```bash
# Cluster health (should stay yellow/green, never red)
curl -X GET "http://ELASTICSEARCH_SERVICE:9200/_cluster/health"

# Shard allocation status
curl -X GET "http://ELASTICSEARCH_SERVICE:9200/_cat/shards?v&h=index,shard,prirep,state,node" | grep -v STARTED

# Master node status
curl -X GET "http://ELASTICSEARCH_SERVICE:9200/_cat/master?v"

# Node resource usage
kubectl top nodes -l node-role=elasticsearch

# Pod status across all StatefulSets
kubectl get pods -l app=elasticsearch -o wide
```

## Post-Upgrade Validation

```bash
# Verify all node pools at 1.32
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE

# Confirm all nodes ready
kubectl get nodes

# Elasticsearch cluster health check
curl -X GET "http://ELASTICSEARCH_SERVICE:9200/_cluster/health?pretty"

# Verify all StatefulSets ready
kubectl get statefulsets -n elasticsearch

# Confirm all shards allocated
curl -X GET "http://ELASTICSEARCH_SERVICE:9200/_cat/shards?v" | grep -c STARTED
curl -X GET "http://ELASTICSEARCH_SERVICE:9200/_cat/shards?v" | grep -c UNASSIGNED

# Test basic indexing and search
curl -X POST "http://ELASTICSEARCH_SERVICE:9200/test_index/_doc" -H 'Content-Type: application/json' -d'{"test": "post_upgrade", "timestamp": "'$(date)'"}'
curl -X GET "http://ELASTICSEARCH_SERVICE:9200/test_index/_search?q=post_upgrade"

# Performance baseline check
curl -X GET "http://ELASTICSEARCH_SERVICE:9200/_nodes/stats/indices?pretty"
```

## Troubleshooting Elasticsearch-Specific Issues

### If cluster goes RED during upgrade:

```bash
# Check unassigned shards
curl -X GET "http://ELASTICSEARCH_SERVICE:9200/_cat/shards?v" | grep UNASSIGNED

# Check cluster-level shard allocation
curl -X GET "http://ELASTICSEARCH_SERVICE:9200/_cluster/allocation/explain?pretty"

# Temporarily increase replica tolerance (if safe)
curl -X PUT "http://ELASTICSEARCH_SERVICE:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "transient": {
    "cluster.routing.allocation.node_concurrent_recoveries": 4,
    "cluster.routing.allocation.cluster_concurrent_rebalance": 4
  }
}'
```

### If PDB blocks drain too aggressively:

The PDBs above allow reasonable disruption (1 master, 2 data, 1 coordinator). If they still block, temporarily relax:

```bash
# Allow 2 masters to be unavailable (risky - only if necessary)
kubectl patch pdb elasticsearch-master-pdb -p '{"spec":{"minAvailable":1}}'

# Restore after node is drained
kubectl patch pdb elasticsearch-master-pdb -p '{"spec":{"minAvailable":2}}'
```

## Why This Strategy Works for Elasticsearch

1. **Regional PVs** survive node replacement - data persists through the upgrade
2. **Conservative maxSurge=1** ensures only one node per pool drains at a time
3. **PDBs protect quorum** - always maintain 2/3 masters and majority of data nodes
4. **Upgrade order (coordinator→data→master)** minimizes risk to cluster stability
5. **Status monitoring** catches issues before they cascade
6. **Pre-upgrade snapshot** provides rollback path for data corruption

## Rollback Plan (If Critical Issues Arise)

If Elasticsearch becomes unstable during upgrade:

```bash
# Stop the upgrade operation
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE
# Note the operation ID and contact support if needed to halt

# Restore from snapshot (last resort)
curl -X POST "http://ELASTICSEARCH_SERVICE:9200/_snapshot/backup_repository/SNAPSHOT_NAME/_restore"

# Scale down problematic StatefulSet temporarily
kubectl scale statefulset elasticsearch-master --replicas=0
# Fix node issues, then scale back up
kubectl scale statefulset elasticsearch-master --replicas=3
```

The combination of conservative upgrade settings, proper PDBs, regional storage, and comprehensive monitoring should ensure your Elasticsearch cluster maintains availability and data integrity throughout the 1.31→1.32 upgrade.
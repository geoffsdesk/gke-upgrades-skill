# Elasticsearch Cluster Upgrade Plan: GKE 1.31 → 1.32

## Cluster Configuration Summary
- **Workload**: Elasticsearch cluster (StatefulSet-based)
- **Architecture**: 3 masters, 5 data, 2 coordinators (separate node pools)
- **Storage**: Regional pd-ssd PVs (survives node upgrades)
- **Upgrade path**: Control plane 1.31 → 1.32, then node pools
- **Strategy**: Conservative approach prioritizing data safety

---

## Pre-Upgrade Checklist

```
Elasticsearch-Specific Readiness
- [ ] Elasticsearch cluster health: `curl -X GET "localhost:9200/_cluster/health?pretty"`
- [ ] All shards allocated: `curl -X GET "localhost:9200/_cat/shards?v&s=index"`
- [ ] Cluster backup completed: `curl -X PUT "localhost:9200/_snapshot/my_backup/snapshot_$(date +%Y%m%d_%H%M%S)"`
- [ ] Master quorum verified (3 masters = can lose 1): `curl -X GET "localhost:9200/_cat/master?v"`
- [ ] Data node capacity headroom confirmed (can handle reduced capacity during rolling upgrade)
- [ ] Elasticsearch operator version compatible with Kubernetes 1.32
- [ ] PV reclaim policy verified as 'Retain': `kubectl get pv -o custom-columns=NAME:.metadata.name,RECLAIM:.spec.persistentVolumeReclaimPolicy`

GKE Cluster Readiness
- [ ] Current versions checked: `gcloud container clusters describe CLUSTER --zone ZONE --format="table(currentMasterVersion, nodePools[].name, nodePools[].version)"`
- [ ] Target version 1.32 available in release channel
- [ ] No deprecated API usage: check GKE deprecation insights dashboard
- [ ] PDBs configured (see configuration below)
- [ ] Maintenance window set for off-peak hours
```

## Critical PDB Configuration

Configure these PDBs **before** starting the upgrade to protect Elasticsearch quorum:

```bash
# Master nodes PDB - allow 1 master down, maintain quorum of 2
cat <<EOF | kubectl apply -f -
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

# Data nodes PDB - allow 1 data node down at a time
cat <<EOF | kubectl apply -f -
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-data-pdb
  namespace: elasticsearch
spec:
  minAvailable: 4
  selector:
    matchLabels:
      app: elasticsearch
      role: data
EOF

# Coordinator nodes PDB - allow 1 coordinator down (keep 1 serving)
cat <<EOF | kubectl apply -f -
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

## Step-by-Step Upgrade Runbook

### Phase 1: Control Plane Upgrade

```bash
# 1. Take application-level backup
kubectl exec elasticsearch-master-0 -n elasticsearch -- \
  curl -X PUT "localhost:9200/_snapshot/my_backup/pre_upgrade_$(date +%Y%m%d_%H%M%S)"

# 2. Verify cluster health before upgrade
kubectl exec elasticsearch-master-0 -n elasticsearch -- \
  curl -X GET "localhost:9200/_cluster/health?pretty"

# 3. Upgrade control plane
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.LATEST

# 4. Verify control plane upgrade (wait ~10-15 minutes)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"

# 5. Check system pods health
kubectl get pods -n kube-system
kubectl get pods -n elasticsearch
```

### Phase 2: Node Pool Upgrades (Sequential Order)

**Upgrade order**: Coordinators → Data → Masters (least critical to most critical)

#### Step 1: Coordinator Node Pool

```bash
# Configure conservative surge settings
gcloud container node-pools update coordinator-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade coordinator pool
gcloud container node-pools upgrade coordinator-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.LATEST

# Monitor progress and verify Elasticsearch health
watch 'kubectl get nodes -l node-role=coordinator -o wide'
kubectl exec elasticsearch-master-0 -n elasticsearch -- \
  curl -X GET "localhost:9200/_cluster/health?pretty"
```

#### Step 2: Data Node Pool

```bash
# Configure data node surge settings
gcloud container node-pools update data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade data pool
gcloud container node-pools upgrade data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.LATEST

# Monitor data rebalancing during upgrade
watch 'kubectl exec elasticsearch-master-0 -n elasticsearch -- curl -s "localhost:9200/_cat/shards?v&s=index"'

# Verify no unassigned shards
kubectl exec elasticsearch-master-0 -n elasticsearch -- \
  curl -X GET "localhost:9200/_cluster/health?level=shards&pretty"
```

#### Step 3: Master Node Pool (Most Critical)

```bash
# Configure master node surge settings (most conservative)
gcloud container node-pools update master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade master pool
gcloud container node-pools upgrade master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.LATEST

# Closely monitor master election during upgrade
watch 'kubectl exec elasticsearch-master-0 -n elasticsearch -- curl -s "localhost:9200/_cat/master?v"'

# Verify cluster stability after each master upgrade
kubectl exec elasticsearch-master-0 -n elasticsearch -- \
  curl -X GET "localhost:9200/_cluster/health?pretty"
```

## Validation Commands

Run these after each phase:

```bash
# Cluster versions
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE

# All nodes ready
kubectl get nodes

# Elasticsearch cluster health
kubectl exec elasticsearch-master-0 -n elasticsearch -- \
  curl -X GET "localhost:9200/_cluster/health?pretty"

# Verify all shards allocated
kubectl exec elasticsearch-master-0 -n elasticsearch -- \
  curl -X GET "localhost:9200/_cat/shards?v&h=index,shard,prirep,state,unassigned.reason"

# Master election stable
kubectl exec elasticsearch-master-0 -n elasticsearch -- \
  curl -X GET "localhost:9200/_cat/master?v"

# No stuck StatefulSets
kubectl get statefulsets -n elasticsearch
```

## Data Protection Measures

### Why Your Data is Safe
- **Regional pd-ssd PVs**: Survive node replacement, data persists across upgrades
- **StatefulSet behavior**: Pods retain identity and PVC attachments
- **Surge upgrade**: Old nodes drain gracefully before deletion
- **PDB protection**: Prevents multiple masters from going down simultaneously

### Emergency Procedures

**If a master becomes unavailable during upgrade:**
```bash
# Check remaining master count
kubectl get pods -n elasticsearch -l role=master -o wide

# Verify quorum (need 2+ masters responding)
kubectl exec elasticsearch-master-1 -n elasticsearch -- \
  curl -X GET "localhost:9200/_cluster/health"

# If quorum lost, pause upgrade and investigate
```

**If data becomes unassigned:**
```bash
# Check shard allocation
kubectl exec elasticsearch-master-0 -n elasticsearch -- \
  curl -X GET "localhost:9200/_cluster/allocation/explain?pretty"

# Force allocation if needed (emergency only)
kubectl exec elasticsearch-master-0 -n elasticsearch -- \
  curl -X POST "localhost:9200/_cluster/reroute" -H 'Content-Type: application/json' -d'
{
  "commands": [
    {
      "allocate_stale_primary": {
        "index": "INDEX_NAME",
        "shard": SHARD_NUMBER,
        "node": "NODE_NAME",
        "accept_data_loss": false
      }
    }
  ]
}'
```

## Rollback Strategy

**Control plane**: Cannot be rolled back once complete. Contact GKE support if issues arise.

**Node pools**: Can be rolled back by creating new pools at the previous version:
```bash
# Create rollback pool
gcloud container node-pools create data-pool-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.PREVIOUS \
  --num-nodes 5 \
  --machine-type n2-standard-4

# Cordon upgraded pool
kubectl cordon -l node-role=data

# Let Elasticsearch naturally rebalance to rollback nodes
# Delete old pool once stable
```

## Post-Upgrade Cleanup

```bash
# Remove temporary PDB relaxations (if any were made)
# Verify final cluster health
kubectl exec elasticsearch-master-0 -n elasticsearch -- \
  curl -X GET "localhost:9200/_cluster/health?pretty"

# Document upgrade in changelog
# Take post-upgrade backup
kubectl exec elasticsearch-master-0 -n elasticsearch -- \
  curl -X PUT "localhost:9200/_snapshot/my_backup/post_upgrade_$(date +%Y%m%d_%H%M%S)"
```

**Expected timeline**: 2-4 hours total (CP: 15 min, each node pool: 30-60 min depending on data rebalancing)

This conservative approach prioritizes data safety over speed. The regional pd-ssd storage and proper PDB configuration ensure your Elasticsearch cluster maintains availability and data integrity throughout the upgrade process.
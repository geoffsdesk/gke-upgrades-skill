# Elasticsearch GKE Upgrade Plan: 1.31 → 1.32

## Cluster Overview
- **Mode:** GKE Standard
- **Upgrade:** 1.31 → 1.32 (single minor version jump)
- **Workload:** StatefulSet-based Elasticsearch
- **Topology:** 3 masters, 5 data, 2 coordinating nodes (separate pools)
- **Storage:** Regional pd-ssd PVs

## Pre-Upgrade Checklist

```
Pre-Upgrade Checklist - Elasticsearch
- [ ] Cluster health: `kubectl get nodes` (all Ready)
- [ ] Elasticsearch cluster health: `curl -X GET "ELASTIC_ENDPOINT/_cluster/health?pretty"`
- [ ] All indices green status, no relocating shards
- [ ] Elasticsearch version compatibility with K8s 1.32 confirmed
- [ ] Recent full snapshot to GCS/other backup completed
- [ ] PV reclaim policy set to "Retain": `kubectl get pv -o custom-columns=NAME:.metadata.name,POLICY:.spec.persistentVolumeReclaimPolicy`
- [ ] PDBs configured per pool (recommend: masters=2, data=4, coordinating=1)
- [ ] No bare pods in elasticsearch namespace
- [ ] GKE 1.32 available in release channel verified
```

## Upgrade Strategy: Conservative Rolling Approach

For Elasticsearch, we'll use **surge upgrades with minimal disruption** per pool, upgrading in this order to maintain quorum and data availability:

1. **Coordinating nodes** (least critical)
2. **Master nodes** (maintain quorum: 3→2→3)  
3. **Data nodes** (Elasticsearch handles shard rebalancing)

### Why This Order?
- Coordinating nodes are stateless load balancers
- Master upgrades maintain 2/3 quorum throughout
- Data nodes last ensures stable cluster during shard movements

## Step-by-Step Runbook

### Phase 1: Pre-flight Checks

```bash
# Verify current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Check Elasticsearch cluster health
kubectl exec -it elasticsearch-master-0 -n elasticsearch -- \
  curl -X GET "localhost:9200/_cluster/health?pretty"

# Verify all shards assigned (should be 0)
kubectl exec -it elasticsearch-master-0 -n elasticsearch -- \
  curl -X GET "localhost:9200/_cat/shards?v" | grep UNASSIGNED

# Check PV reclaim policies
kubectl get pv -o custom-columns=NAME:.metadata.name,POLICY:.spec.persistentVolumeReclaimPolicy | grep elasticsearch
```

### Phase 2: Elasticsearch Pre-Upgrade Configuration

```bash
# Disable shard allocation (prevents unnecessary movement during upgrades)
kubectl exec -it elasticsearch-master-0 -n elasticsearch -- \
  curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'

# Verify PDBs are properly configured
kubectl get pdb -n elasticsearch
```

Expected PDB configuration:
```yaml
# Master PDB - allows 1 disruption (maintains 2/3 quorum)
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-master-pdb
spec:
  maxUnavailable: 1
  selector:
    matchLabels:
      app: elasticsearch-master

# Data PDB - allows 1 disruption (maintains data availability)  
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-data-pdb
spec:
  maxUnavailable: 1
  selector:
    matchLabels:
      app: elasticsearch-data

# Coordinating PDB - allows 1 disruption
apiVersion: policy/v1
kind: PodDisruptionBudget  
metadata:
  name: elasticsearch-coordinating-pdb
spec:
  maxUnavailable: 1
  selector:
    matchLabels:
      app: elasticsearch-coordinating
```

### Phase 3: Control Plane Upgrade

```bash
# Upgrade control plane to 1.32
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.XX-gke.XXXXX

# Wait and verify (10-15 minutes)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"

# Verify system pods healthy
kubectl get pods -n kube-system | grep -v Running
```

### Phase 4: Node Pool Upgrades

#### 4.1 Coordinating Nodes First

```bash
# Configure conservative surge settings
gcloud container node-pools update elasticsearch-coordinating \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade coordinating pool
gcloud container node-pools upgrade elasticsearch-coordinating \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.XX-gke.XXXXX

# Monitor progress
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=elasticsearch-coordinating'

# Verify coordinating pods healthy
kubectl get pods -n elasticsearch -l app=elasticsearch-coordinating
```

#### 4.2 Master Nodes Second

```bash
# Configure conservative surge for masters
gcloud container node-pools update elasticsearch-master \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade master pool
gcloud container node-pools upgrade elasticsearch-master \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.XX-gke.XXXXX

# Critical: Monitor master quorum during upgrade
watch 'kubectl exec -it elasticsearch-master-0 -n elasticsearch -- curl -s localhost:9200/_cat/master'

# Verify master pods and cluster health
kubectl get pods -n elasticsearch -l app=elasticsearch-master
kubectl exec -it elasticsearch-master-0 -n elasticsearch -- \
  curl -X GET "localhost:9200/_cluster/health?pretty"
```

#### 4.3 Data Nodes Last

```bash
# Configure conservative surge for data nodes
gcloud container node-pools update elasticsearch-data \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade data pool
gcloud container node-pools upgrade elasticsearch-data \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.XX-gke.XXXXX

# Monitor data node health and shard allocation
watch 'kubectl get pods -n elasticsearch -l app=elasticsearch-data'
kubectl exec -it elasticsearch-master-0 -n elasticsearch -- \
  curl -s "localhost:9200/_cat/shards?v" | head -20
```

### Phase 5: Post-Upgrade Validation

```bash
# Re-enable shard allocation
kubectl exec -it elasticsearch-master-0 -n elasticsearch -- \
  curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": null
  }
}'

# Comprehensive health checks
kubectl exec -it elasticsearch-master-0 -n elasticsearch -- \
  curl -X GET "localhost:9200/_cluster/health?wait_for_status=green&timeout=10m&pretty"

# Verify all nodes in cluster
kubectl exec -it elasticsearch-master-0 -n elasticsearch -- \
  curl -X GET "localhost:9200/_cat/nodes?v"

# Check shard allocation completed
kubectl exec -it elasticsearch-master-0 -n elasticsearch -- \
  curl -X GET "localhost:9200/_cat/allocation?v"

# Verify all node pools at 1.32
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE
```

## Post-Upgrade Checklist

```
Post-Upgrade Validation - Elasticsearch
- [ ] All node pools at 1.32: `gcloud container node-pools list --cluster CLUSTER --zone ZONE`
- [ ] All K8s nodes Ready: `kubectl get nodes`
- [ ] Elasticsearch cluster status GREEN
- [ ] All 10 Elasticsearch nodes visible in cluster: `_cat/nodes`
- [ ] No unassigned shards: `_cat/shards | grep UNASSIGNED` (should be empty)
- [ ] Index write/read tests successful
- [ ] Application health checks passing
- [ ] Monitoring and logging normal
- [ ] Shard allocation re-enabled (verified above)
```

## Rollback Plan (if needed)

```bash
# If issues arise during data node upgrade:
# 1. Cancel the upgrade operation
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE
# Note the operation ID, then contact GKE support to halt if needed

# 2. Elasticsearch should self-heal with remaining nodes
kubectl exec -it elasticsearch-master-0 -n elasticsearch -- \
  curl -X GET "localhost:9200/_cluster/health?pretty"

# 3. If data loss suspected, restore from snapshot
kubectl exec -it elasticsearch-master-0 -n elasticsearch -- \
  curl -X POST "localhost:9200/_snapshot/REPO_NAME/SNAPSHOT_NAME/_restore"
```

## Key Elasticsearch-Specific Considerations

1. **PV Safety**: Regional pd-ssd PVs with "Retain" policy protect against accidental deletion
2. **Quorum Maintenance**: Master upgrade maintains 2/3 quorum throughout
3. **Shard Management**: Temporarily disabling allocation prevents unnecessary shard movement
4. **Surge Strategy**: `maxSurge=1, maxUnavailable=0` ensures no capacity loss during upgrade
5. **Order Matters**: Coordinating→Master→Data preserves cluster stability
6. **PDB Protection**: Properly configured PDBs prevent simultaneous eviction of critical pods

This approach ensures zero data loss and maintains Elasticsearch availability throughout the upgrade process.
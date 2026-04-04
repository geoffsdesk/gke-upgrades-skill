# GKE Elasticsearch Cluster Upgrade Plan: 1.31 → 1.32

## Cluster Overview
- **Mode**: Standard
- **Current**: 1.31 → **Target**: 1.32
- **Architecture**: 3 masters, 5 data, 2 coordinators (separate node pools)
- **Storage**: Regional pd-ssd PVs (good — survives node replacement)

## Pre-Upgrade Checklist

```
Elasticsearch-Specific Preparation
- [ ] Elasticsearch version compatibility with Kubernetes 1.32 verified
- [ ] Cluster health: `kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health"`
- [ ] All shards allocated: `kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/shards?h=index,shard,prirep,state"`
- [ ] Disable shard allocation: `kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'{"persistent":{"cluster.routing.allocation.enable":"primaries"}}'`
- [ ] Application-level snapshot: `kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_snapshot/backup/pre-upgrade-$(date +%Y%m%d)"`
- [ ] Pod Disruption Budgets configured:
      - Masters: minAvailable: 2 (maintains quorum)
      - Data: minAvailable: 3 (keeps majority of shards available)  
      - Coordinators: minAvailable: 1 (maintains query capacity)

Kubernetes Compatibility
- [ ] Check for deprecated APIs: `kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated`
- [ ] GKE 1.31→1.32 release notes reviewed
- [ ] PV reclaim policies verified as Retain: `kubectl get pv -o custom-columns=NAME:.metadata.name,RECLAIM:.spec.persistentVolumeReclaimPolicy`

Infrastructure Readiness  
- [ ] Surge capacity available for 3 separate node pools
- [ ] Maintenance window scheduled (expect 2-3 hours total)
- [ ] Monitoring baseline captured (query latency, indexing rate, JVM heap)
```

## Upgrade Strategy: Sequential with Elasticsearch-Safe Settings

**Node Pool Upgrade Order**: Coordinators → Data → Masters (least critical to most critical)

**Strategy per Pool**: Surge with conservative settings
- **Coordinators**: `maxSurge=1, maxUnavailable=0` (rolling replacement)
- **Data nodes**: `maxSurge=1, maxUnavailable=0` (preserves data availability)  
- **Masters**: `maxSurge=1, maxUnavailable=0` (maintains quorum throughout)

## Step-by-Step Runbook

### Phase 1: Control Plane Upgrade

```bash
# Upgrade control plane first (required before nodes)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32

# Verify control plane (wait ~10-15 min)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"

# Confirm system pods healthy
kubectl get pods -n kube-system
```

### Phase 2: Configure Pod Disruption Budgets

```yaml
# es-master-pdb.yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: es-master-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: elasticsearch
      role: master
---
# es-data-pdb.yaml  
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: es-data-pdb
spec:
  minAvailable: 3
  selector:
    matchLabels:
      app: elasticsearch
      role: data
---
# es-coordinator-pdb.yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: es-coordinator-pdb
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: elasticsearch
      role: coordinator
```

```bash
kubectl apply -f es-master-pdb.yaml
kubectl apply -f es-data-pdb.yaml  
kubectl apply -f es-coordinator-pdb.yaml

# Verify PDBs
kubectl get pdb -o wide
```

### Phase 3: Node Pool Upgrades (Sequential)

#### 3a. Upgrade Coordinator Nodes First (Lowest Risk)

```bash
# Configure surge settings for coordinators
gcloud container node-pools update coordinator-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade coordinator pool
gcloud container node-pools upgrade coordinator-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor progress - coordinators should upgrade smoothly
watch 'kubectl get nodes -l nodepool=coordinator-pool -o wide'

# Verify Elasticsearch cluster health after coordinators
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health"
```

#### 3b. Upgrade Data Nodes (Higher Risk - Monitor Closely)

```bash
# Configure surge for data nodes
gcloud container node-pools update data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# CRITICAL: Re-enable shard allocation before data node upgrade
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'{"persistent":{"cluster.routing.allocation.enable":"all"}}'

# Upgrade data pool
gcloud container node-pools upgrade data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor data node upgrade closely
watch 'kubectl get nodes -l nodepool=data-pool -o wide'

# After each data node comes up, verify cluster health
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health"
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/shards?h=index,shard,prirep,state" | grep -v STARTED
```

#### 3c. Upgrade Master Nodes Last (Highest Risk)

```bash
# Configure surge for masters  
gcloud container node-pools update master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade master pool - PDB ensures quorum maintained
gcloud container node-pools upgrade master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor master upgrades - most critical
watch 'kubectl get nodes -l nodepool=master-pool -o wide'

# Verify master election stability after each master upgrade
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/master"
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"
```

## Post-Upgrade Validation

```bash
# Cluster-level health
kubectl get nodes
kubectl get pods -l app=elasticsearch

# Elasticsearch health checks
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/nodes?h=name,role,version"
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/shards" | wc -l

# Performance validation
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/pending_tasks"
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_nodes/stats/jvm"

# Storage verification - PVs should be unchanged
kubectl get pv | grep elasticsearch
```

## Critical Elasticsearch Considerations

**Why This Order Works:**
1. **Coordinators first**: Handle queries/aggregations but no data - lowest risk
2. **Data nodes second**: PDB ensures 3/5 stay up, maintaining shard availability  
3. **Masters last**: PDB ensures 2/3 quorum maintained throughout

**Shard Allocation Strategy:**
- Initially disabled to prevent unnecessary shard movement
- Re-enabled before data node upgrades so Elasticsearch can rebalance away from draining nodes
- Regional PVs ensure data persists across node replacement

**If Things Go Wrong:**
- **Cluster goes red**: Check `_cat/shards` for unassigned shards, may need to wait for node startup
- **Split brain**: Verify master PDB maintained 2/3 quorum - should be impossible with our settings
- **Data loss**: Regional PVs protect against this, but application snapshots provide additional safety

**Recovery Time**: Expect 30-45 minutes per node pool. Total upgrade window: 2-3 hours.

This approach prioritizes Elasticsearch stability over upgrade speed. The conservative `maxSurge=1` ensures orderly replacement while PDBs provide the safety net for quorum and data availability.
# GKE Upgrade Plan: Elasticsearch Cluster (1.31 → 1.32)

## Cluster Overview
- **Mode:** Standard
- **Current version:** 1.31
- **Target version:** 1.32
- **Workload:** StatefulSet-based Elasticsearch (3 masters, 5 data nodes, 2 coordinators)
- **Storage:** Regional pd-ssd PVs

## Pre-Upgrade Assessment

### 1. Version Compatibility Check
```bash
# Verify 1.32 is available in your release channel
gcloud container get-server-config --zone ZONE --format="yaml(channels)"

# Check current cluster details
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, releaseChannel.channel, nodePools[].name, nodePools[].version)"
```

### 2. Elasticsearch Health Baseline
```bash
# Cluster health (should be green before upgrade)
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"

# Shard allocation status
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cat/shards?v"

# Index health
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cat/indices?v&health=yellow,red"
```

**Critical:** Only proceed if cluster health is GREEN and all shards are allocated.

## Upgrade Strategy: Conservative Approach

Given Elasticsearch's distributed nature and data criticality, we'll use a conservative strategy:

- **Control plane:** Standard upgrade
- **Node pools:** Blue-green strategy with careful sequencing
- **Order:** Coordinators → Masters → Data nodes (reverse criticality)

## Step-by-Step Upgrade Plan

### Phase 1: Pre-Upgrade Preparation

#### 1.1 Disable Elasticsearch Shard Allocation
This prevents Elasticsearch from moving shards during node drains:

```bash
kubectl exec -it elasticsearch-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" \
  -H "Content-Type: application/json" \
  -d '{
    "persistent": {
      "cluster.routing.allocation.enable": "primaries"
    }
  }'
```

#### 1.2 Configure PodDisruptionBudgets
Ensure PDBs protect your Elasticsearch pods but aren't overly restrictive:

```yaml
# Master nodes PDB (allow 1 disruption out of 3)
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-master-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: elasticsearch
      role: master
---
# Data nodes PDB (allow 2 disruptions out of 5 - maintains quorum)
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-data-pdb
spec:
  minAvailable: 3
  selector:
    matchLabels:
      app: elasticsearch
      role: data
---
# Coordinator nodes PDB (allow 1 disruption out of 2)
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-coordinator-pdb
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: elasticsearch
      role: coordinator
```

#### 1.3 Take Elasticsearch Snapshot
```bash
# Create snapshot repository (if not already configured)
kubectl exec -it elasticsearch-master-0 -- curl -X PUT "localhost:9200/_snapshot/backup" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "gcs",
    "settings": {
      "bucket": "YOUR_BACKUP_BUCKET",
      "base_path": "elasticsearch-snapshots"
    }
  }'

# Create pre-upgrade snapshot
kubectl exec -it elasticsearch-master-0 -- curl -X PUT "localhost:9200/_snapshot/backup/pre-upgrade-$(date +%Y%m%d-%H%M)" \
  -H "Content-Type: application/json" \
  -d '{
    "indices": "*",
    "ignore_unavailable": true,
    "include_global_state": true
  }'
```

### Phase 2: Control Plane Upgrade

```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.xxxx

# Wait and verify (~10-15 minutes)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

### Phase 3: Node Pool Upgrades (Sequential Blue-Green)

For Elasticsearch, we'll use blue-green upgrades to minimize data movement and maintain availability.

#### 3.1 Coordinator Nodes First (Lowest Risk)

```bash
# Configure for blue-green upgrade
gcloud container node-pools update coordinator-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 2 \
  --total-max-nodes 4

# Start blue-green upgrade
gcloud container node-pools update coordinator-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --blue-green-initial-node-percentage=1.0 \
  --blue-green-full-batch-timeout=3600s

gcloud container node-pools upgrade coordinator-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxxx
```

**Wait for completion and verify:**
```bash
kubectl get nodes -l cloud.google.com/gke-nodepool=coordinator-pool
kubectl get pods -l role=coordinator -o wide

# Test coordinator functionality
kubectl port-forward svc/elasticsearch-coordinator 9200:9200 &
curl -X GET "localhost:9200/_cluster/health?pretty"
```

#### 3.2 Master Nodes (Most Critical)

**Important:** For masters, use conservative surge settings to maintain quorum:

```bash
# Conservative blue-green for masters
gcloud container node-pools update master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 3 \
  --total-max-nodes 6

# Upgrade with careful timing
gcloud container node-pools upgrade master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxxx
```

**Monitor master election during upgrade:**
```bash
# Watch master nodes
watch 'kubectl exec -it elasticsearch-master-0 -- curl -s "localhost:9200/_cat/master?v"'

# Monitor cluster state
watch 'kubectl exec -it elasticsearch-master-0 -- curl -s "localhost:9200/_cluster/health" | jq .status'
```

#### 3.3 Data Nodes (Final, Most Storage-Sensitive)

Data nodes require the most care due to shard storage:

```bash
# Blue-green upgrade for data nodes
gcloud container node-pools update data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 5 \
  --total-max-nodes 10

gcloud container node-pools upgrade data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxxx
```

**Monitor shard movement:**
```bash
# Watch shard allocation during upgrade
watch 'kubectl exec -it elasticsearch-master-0 -- curl -s "localhost:9200/_cat/shards?v&h=index,shard,prirep,state,node" | head -20'

# Check for relocating shards
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cat/shards?v&s=state" | grep RELOCATING
```

### Phase 4: Post-Upgrade Validation

#### 4.1 Re-enable Shard Allocation
```bash
kubectl exec -it elasticsearch-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" \
  -H "Content-Type: application/json" \
  -d '{
    "persistent": {
      "cluster.routing.allocation.enable": null
    }
  }'
```

#### 4.2 Health Validation
```bash
# Cluster health check
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cluster/health?wait_for_status=green&timeout=5m&pretty"

# Node roles verification
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cat/nodes?v&h=name,node.role,master"

# Index health
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cat/indices?v&health=yellow,red"

# Verify all shards are assigned
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cat/shards?v" | grep -E "UNASSIGNED|INITIALIZING"
```

#### 4.3 Kubernetes Validation
```bash
# All nodes ready
kubectl get nodes

# All Elasticsearch pods running
kubectl get pods -l app=elasticsearch

# StatefulSets healthy
kubectl get statefulsets

# PV/PVC status
kubectl get pvc | grep elasticsearch
```

## Rollback Plan

If issues occur after data node upgrade:

1. **Immediate:** Restore from snapshot if data corruption detected
2. **Node-level:** Create new node pool at 1.31, migrate workloads back
3. **Cluster-level:** Contact GKE support for control plane downgrade

```bash
# Emergency snapshot restore (if needed)
kubectl exec -it elasticsearch-master-0 -- curl -X POST "localhost:9200/_snapshot/backup/pre-upgrade-TIMESTAMP/_restore" \
  -H "Content-Type: application/json" \
  -d '{
    "indices": "*",
    "ignore_unavailable": true,
    "include_global_state": true
  }'
```

## Risk Mitigation Summary

1. **Data Protection:** Snapshot before upgrade, regional PVs survive node replacement
2. **Availability:** Blue-green strategy maintains node availability, PDBs prevent quorum loss
3. **Shard Stability:** Disabled allocation prevents unnecessary shard movement
4. **Upgrade Order:** Coordinators → Masters → Data (increasing criticality)
5. **Monitoring:** Health checks between each phase

## Estimated Timeline

- **Preparation:** 30 minutes
- **Control plane:** 15 minutes
- **Coordinator nodes:** 20 minutes
- **Master nodes:** 30 minutes (watch carefully)
- **Data nodes:** 45 minutes
- **Validation:** 15 minutes

**Total:** ~2.5 hours

This conservative approach prioritizes data safety and availability over speed. The blue-green strategy ensures your Elasticsearch cluster maintains service throughout the upgrade process.
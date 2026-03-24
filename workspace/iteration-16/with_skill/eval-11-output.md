# GKE Upgrade Plan: Elasticsearch Cluster (1.31 → 1.32)

## Cluster Overview
- **Current version:** 1.31 → **Target version:** 1.32
- **Workload:** Elasticsearch StatefulSet (3 masters, 5 data, 2 coordinators)
- **Storage:** Regional pd-ssd PVs (good - survives node changes)
- **Strategy:** Conservative surge upgrade with Elasticsearch-specific protections

## Pre-Upgrade: Elasticsearch-Specific Preparations

### 1. Cluster Health Check
```bash
# Elasticsearch cluster status
kubectl exec -it elasticsearch-master-0 -n elasticsearch -- curl -X GET "localhost:9200/_cluster/health?pretty"
# Should show: status: green, number_of_nodes: 10

# Check for unassigned shards
kubectl exec -it elasticsearch-master-0 -n elasticsearch -- curl -X GET "localhost:9200/_cat/shards?v&h=index,shard,prirep,state,unassigned.reason" | grep UNASSIGNED
# Should return empty
```

### 2. Disable Elasticsearch Auto-Rebalancing
```bash
# Prevent shard rebalancing during upgrade
kubectl exec -it elasticsearch-master-0 -n elasticsearch -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'
```

### 3. Configure PDBs for Each Node Type
```yaml
# Master nodes PDB (allow 1 master to drain, keep 2 for quorum)
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
---
# Data nodes PDB (allow 1 data node at a time)
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
---
# Coordinator nodes PDB (allow 1 coordinator at a time)
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
```

```bash
kubectl apply -f elasticsearch-pdbs.yaml
```

## Upgrade Execution

### Phase 1: Control Plane Upgrade
```bash
# Upgrade control plane first (required before nodes)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.0-gke.1200

# Verify control plane upgrade (~10-15 minutes)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

### Phase 2: Node Pool Upgrades (Sequential Order)

**Upgrade order for Elasticsearch:** Coordinators → Data → Masters (least to most critical)

#### Step 1: Coordinator Node Pool
```bash
# Conservative settings: one node at a time, zero downtime
gcloud container node-pools update coordinator-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade coordinator-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.0-gke.1200

# Monitor progress
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=coordinator-pool -o wide'
```

**Validation after coordinators:**
```bash
# Check Elasticsearch cluster health
kubectl exec -it elasticsearch-master-0 -n elasticsearch -- curl -X GET "localhost:9200/_cluster/health?pretty"
# Verify 2 coordinator nodes are back online
kubectl exec -it elasticsearch-master-0 -n elasticsearch -- curl -X GET "localhost:9200/_cat/nodes?v&h=name,node.role,version"
```

#### Step 2: Data Node Pool
```bash
# One data node at a time to protect data
gcloud container node-pools update data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.0-gke.1200

# Monitor - this will take longest due to data persistence
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=data-pool -o wide'
```

**Validation after data nodes:**
```bash
# Check all shards are assigned
kubectl exec -it elasticsearch-master-0 -n elasticsearch -- curl -X GET "localhost:9200/_cat/shards?v&h=index,shard,prirep,state" | grep -v STARTED
# Should return empty

# Verify 5 data nodes online
kubectl exec -it elasticsearch-master-0 -n elasticsearch -- curl -X GET "localhost:9200/_cat/nodes?v&h=name,node.role" | grep data
```

#### Step 3: Master Node Pool (Most Critical)
```bash
# Very conservative: one master at a time
gcloud container node-pools update master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.0-gke.1200

# Monitor closely - master changes affect cluster coordination
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=master-pool -o wide'
```

**Critical validation after each master node:**
```bash
# Check quorum maintained (should stay green throughout)
kubectl exec -it elasticsearch-master-0 -n elasticsearch -- curl -X GET "localhost:9200/_cluster/health?wait_for_status=green&timeout=30s&pretty"

# Verify master election stability
kubectl exec -it elasticsearch-master-0 -n elasticsearch -- curl -X GET "localhost:9200/_cat/master?v"
```

## Post-Upgrade: Re-enable Elasticsearch Features

### 1. Re-enable Auto-Rebalancing
```bash
kubectl exec -it elasticsearch-master-0 -n elasticsearch -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "all"
  }
}'
```

### 2. Final Health Verification
```bash
# Comprehensive cluster health
kubectl exec -it elasticsearch-master-0 -n elasticsearch -- curl -X GET "localhost:9200/_cluster/health?pretty"
# Should show: status: green, number_of_nodes: 10

# All nodes at correct versions
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,POOL:.metadata.labels.cloud\.google\.com/gke-nodepool

# All Elasticsearch pods healthy
kubectl get pods -n elasticsearch -o wide
kubectl get statefulsets -n elasticsearch
```

## Rollback Plan (If Needed)

If issues arise during node pool upgrades:

```bash
# Cancel in-progress upgrade
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES"

# For emergency rollback, create new node pool at 1.31
gcloud container node-pools create POOL-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.xxxx \
  --num-nodes NUM_NODES \
  --machine-type MACHINE_TYPE

# Cordon upgraded nodes and drain workloads to rollback pool
kubectl cordon -l cloud.google.com/gke-nodepool=PROBLEM_POOL
```

## Key Safety Measures

- **PVs survive node replacement** - Regional pd-ssd volumes automatically reattach to new nodes
- **PDBs protect quorum** - Masters: 2/3 minimum, Data: 4/5 minimum  
- **Conservative surge settings** - One node at a time prevents multiple simultaneous failures
- **Disabled rebalancing** - Prevents unnecessary shard movement during upgrades
- **Sequential pool upgrades** - Coordinators → Data → Masters (increasing criticality)
- **Health checks between phases** - Verify green status before proceeding

**Estimated timeline:** 2-4 hours total (30 min CP + 45-90 min per node pool)

The regional pd-ssd storage is your safety net - even if a node fails completely during upgrade, the PV reattaches to the replacement node and your data is intact.
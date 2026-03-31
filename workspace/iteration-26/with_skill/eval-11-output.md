# GKE Upgrade Plan: Elasticsearch Cluster (1.31 → 1.32)

## Cluster Overview
- **Current version:** 1.31 → **Target:** 1.32
- **Workload:** Elasticsearch cluster (StatefulSets)
- **Architecture:** 3 masters + 5 data + 2 coordinators (separate node pools)
- **Storage:** Regional pd-ssd PVs (survive node replacement)

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

# 2. Stop indexing new data (coordinate with application teams)
# This is optional but recommended for zero data loss

# 3. Perform synced flush
curl -X POST "localhost:9200/_flush/synced"

# 4. Take cluster snapshot (application-level backup)
curl -X PUT "localhost:9200/_snapshot/backup_repository/pre-upgrade-snapshot?wait_for_completion=true"
```

### Kubernetes Preparation
```bash
# Verify PV reclaim policies are Retain (not Delete)
kubectl get pv -o custom-columns=NAME:.metadata.name,RECLAIM:.spec.persistentVolumeReclaimPolicy | grep elasticsearch

# Configure PDBs for Elasticsearch pods
kubectl apply -f - <<EOF
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-master-pdb
  namespace: elasticsearch
spec:
  minAvailable: 2  # Allows 1 master to drain, keeps quorum of 2
  selector:
    matchLabels:
      app: elasticsearch
      role: master
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-data-pdb
  namespace: elasticsearch
spec:
  minAvailable: 3  # Allows 2 data nodes to drain simultaneously
  selector:
    matchLabels:
      app: elasticsearch
      role: data
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-coordinator-pdb
  namespace: elasticsearch
spec:
  minAvailable: 1  # Allows 1 coordinator to drain
  selector:
    matchLabels:
      app: elasticsearch
      role: coordinator
EOF
```

## Node Pool Upgrade Strategy

**Use surge upgrade with conservative settings:**
- **Coordinator pools:** `maxSurge=1, maxUnavailable=0` (upgrade first, lowest risk)
- **Data pools:** `maxSurge=1, maxUnavailable=0` (one-at-a-time to protect data)
- **Master pools:** `maxSurge=1, maxUnavailable=0` (most critical, upgrade last)

**Upgrade order:** Coordinators → Data nodes → Masters (least to most critical)

## Step-by-Step Upgrade Runbook

### Step 1: Control Plane Upgrade
```bash
# Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32

# Wait and verify (10-15 minutes)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"

# Confirm system pods healthy
kubectl get pods -n kube-system
```

### Step 2: Configure Node Pool Surge Settings
```bash
# Configure conservative surge for all pools
for POOL in coordinator-pool data-pool master-pool; do
  gcloud container node-pools update $POOL \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --max-surge-upgrade 1 \
    --max-unavailable-upgrade 0
done
```

### Step 3: Upgrade Coordinator Pool (First - Lowest Risk)
```bash
# Upgrade coordinators first
gcloud container node-pools upgrade coordinator-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor progress
watch 'kubectl get nodes -l node-pool=coordinator-pool -o wide'
watch 'kubectl get pods -l role=coordinator -o wide'

# Verify coordinator pods are running and healthy
kubectl logs -l role=coordinator --tail=50
```

### Step 4: Upgrade Data Pool (Second - Data Critical)
```bash
# Upgrade data nodes one at a time
gcloud container node-pools upgrade data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor carefully - this is where data lives
watch 'kubectl get nodes -l node-pool=data-pool -o wide'
watch 'kubectl get pods -l role=data -o wide'

# Check cluster health after each data node upgrade
curl -X GET "localhost:9200/_cluster/health?pretty"
```

### Step 5: Upgrade Master Pool (Last - Most Critical)
```bash
# Masters last - most critical for cluster coordination
gcloud container node-pools upgrade master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor master election during upgrade
watch 'kubectl get pods -l role=master -o wide'
curl -X GET "localhost:9200/_cat/master?v"
```

## Post-Upgrade Validation

### Kubernetes Validation
```bash
# Verify all nodes upgraded
kubectl get nodes -o wide

# Check all Elasticsearch pods running
kubectl get pods -n elasticsearch -o wide

# Verify StatefulSets at desired replica count
kubectl get statefulsets -n elasticsearch
```

### Elasticsearch Validation
```bash
# 1. Check cluster health
curl -X GET "localhost:9200/_cluster/health?pretty"
# Should show: status: green, number_of_nodes: 10

# 2. Verify all nodes joined cluster
curl -X GET "localhost:9200/_cat/nodes?v"

# 3. Re-enable shard allocation
curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": null
  }
}'

# 4. Wait for cluster to rebalance and turn green
curl -X GET "localhost:9200/_cluster/health?wait_for_status=green&timeout=10m"

# 5. Verify data integrity (index count, doc count)
curl -X GET "localhost:9200/_cat/indices?v"

# 6. Test search functionality
curl -X GET "localhost:9200/_search?size=1&pretty"
```

## Rollback Plan (If Issues Arise)

### If Data Nodes Fail to Start
```bash
# 1. Check StatefulSet and pod events
kubectl describe statefulset elasticsearch-data -n elasticsearch
kubectl describe pods -l role=data -n elasticsearch

# 2. Verify PVC attachment
kubectl get pvc -n elasticsearch
kubectl describe pvc elasticsearch-data-pvc-* -n elasticsearch

# 3. If PV issues, restore from snapshot
curl -X POST "localhost:9200/_snapshot/backup_repository/pre-upgrade-snapshot/_restore"
```

### If Cluster Health Degrades
```bash
# 1. Pause further upgrades
# Cancel any in-progress operations if safe to do so

# 2. Check shard allocation
curl -X GET "localhost:9200/_cat/shards?v&h=index,shard,prirep,state,unassigned.reason"

# 3. Force allocation of unassigned shards (last resort)
curl -X POST "localhost:9200/_cluster/reroute?retry_failed=true"
```

## Expected Timeline
- **Control plane:** 15 minutes
- **Coordinator pool:** 20-30 minutes (2 nodes)
- **Data pool:** 45-60 minutes (5 nodes, one at a time)
- **Master pool:** 30-45 minutes (3 nodes, one at a time)
- **Total:** ~2-2.5 hours

## Key Safety Measures
1. **PDBs protect quorum:** Master PDB ensures 2/3 masters always available
2. **Conservative surge:** One node at a time prevents multiple simultaneous failures
3. **Upgrade order:** Coordinators first (safest) → Data → Masters (most critical)
4. **Application backup:** Snapshot taken before any K8s changes
5. **Regional PVs:** Data survives node replacement automatically
6. **Shard allocation disabled:** Prevents unnecessary data movement during upgrade

This plan prioritizes **data safety** and **availability** over speed. The upgrade will take longer but minimizes risk to your Elasticsearch cluster.
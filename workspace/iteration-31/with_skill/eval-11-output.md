# Elasticsearch GKE Upgrade Plan: 1.31 → 1.32

## Cluster Overview
- **Workload:** Elasticsearch StatefulSet (3 masters, 5 data, 2 coordinators)
- **Current:** GKE 1.31 → **Target:** 1.32
- **Storage:** Regional pd-ssd PVs (good - survives node replacement)
- **Architecture:** Separate node pools per ES role

## Pre-Upgrade Checklist

### Elasticsearch Preparation
- [ ] **Disable shard allocation** to prevent rebalancing during upgrade:
  ```bash
  curl -X PUT "elasticsearch-master:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
  {
    "persistent": {
      "cluster.routing.allocation.enable": "primaries"
    }
  }'
  ```
- [ ] **Take application-level snapshot** (critical for stateful workloads):
  ```bash
  curl -X PUT "elasticsearch-master:9200/_snapshot/gke-upgrade-backup/snapshot-$(date +%Y%m%d)" -H 'Content-Type: application/json' -d'
  {
    "indices": "*",
    "ignore_unavailable": true,
    "include_global_state": true
  }'
  ```
- [ ] **Verify cluster health:** `curl -X GET "elasticsearch-master:9200/_cluster/health"` (should be green)
- [ ] **Check PV reclaim policy** (safety measure):
  ```bash
  kubectl get pv -o custom-columns=NAME:.metadata.name,RECLAIM:.spec.persistentVolumeReclaimPolicy | grep elasticsearch
  ```

### GKE Compatibility
- [ ] **Check target version availability:**
  ```bash
  gcloud container get-server-config --zone ZONE --format="yaml(channels)"
  ```
- [ ] **Review breaking changes:** Check [GKE 1.32 release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes)
- [ ] **Deprecated API check:**
  ```bash
  kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
  ```

### Configure PDBs (Critical for Elasticsearch)
```bash
# Master nodes PDB - allow 1 master down, maintain quorum of 2
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
      app: elasticsearch-master
EOF

# Data nodes PDB - allow 2 data nodes down simultaneously
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
      app: elasticsearch-data
EOF

# Coordinator nodes PDB - allow 1 coordinator down
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
      app: elasticsearch-coordinator
EOF
```

## Upgrade Execution Plan

### Phase 1: Control Plane Upgrade
```bash
# Upgrade control plane first (required order)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.LATEST

# Monitor progress (~10-15 minutes)
watch 'gcloud container clusters describe CLUSTER_NAME --zone ZONE --format="value(currentMasterVersion)"'
```

### Phase 2: Node Pool Upgrades (Conservative Strategy)

**Upgrade Order:** Coordinators → Data → Masters (least critical to most critical)

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

# Validate coordinator health before proceeding
curl -X GET "elasticsearch-master:9200/_cat/nodes?v" | grep coord
```

#### Step 2: Data Node Pool
```bash
# Conservative settings for data nodes (most critical for data)
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

# Monitor data node rejoining and shard allocation
watch 'curl -s "elasticsearch-master:9200/_cat/nodes?v"'
```

#### Step 3: Master Node Pool (Most Critical)
```bash
# Most conservative settings for masters
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

# Critical: Monitor master quorum throughout
watch 'curl -s "elasticsearch-master:9200/_cat/master?v"'
```

## Post-Upgrade Validation

### 1. Cluster Health
```bash
# Verify all nodes upgraded
kubectl get nodes -o wide

# Check system pods
kubectl get pods -n kube-system

# Verify no stuck pods
kubectl get pods -A | grep -E "Terminating|Pending"
```

### 2. Elasticsearch Health
```bash
# Re-enable shard allocation
curl -X PUT "elasticsearch-master:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "all"
  }
}'

# Wait for cluster to return to green status
watch 'curl -s "elasticsearch-master:9200/_cluster/health" | jq .status'

# Verify all nodes visible
curl -X GET "elasticsearch-master:9200/_cat/nodes?v"

# Check shard allocation
curl -X GET "elasticsearch-master:9200/_cat/allocation?v"

# Validate data integrity with search test
curl -X GET "elasticsearch-master:9200/_cat/indices?v"
```

### 3. StatefulSet Status
```bash
# Verify all StatefulSets at desired replicas
kubectl get statefulsets -n elasticsearch

# Check PVC status
kubectl get pvc -n elasticsearch | grep -v Bound
```

## Rollback Plan (If Issues Arise)

**During Node Pool Upgrade:**
```bash
# Cancel in-progress upgrade
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE
# Node pool upgrades can be cancelled during drain phase

# Create new node pool at 1.31 if needed
gcloud container node-pools create POOL-NAME-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.PREVIOUS \
  --num-nodes NUM_NODES \
  --machine-type MACHINE_TYPE

# Cordon problematic pool and migrate workloads
kubectl cordon -l cloud.google.com/gke-nodepool=PROBLEMATIC_POOL
```

**Data Recovery:**
```bash
# If cluster corruption occurs, restore from snapshot
curl -X POST "elasticsearch-master:9200/_snapshot/gke-upgrade-backup/snapshot-YYYYMMDD/_restore"
```

## Key Safety Measures

1. **PDBs protect quorum** - Masters maintain 2/3 quorum, data maintains 3/5
2. **Conservative maxSurge=1** - Only one node upgrading at a time per pool
3. **Regional PVs survive** - Data persists through node replacement
4. **Shard allocation disabled** - Prevents unnecessary data movement
5. **Application snapshot** - Full data backup before any changes
6. **Sequential pool upgrades** - Validate each tier before proceeding

## Expected Timeline
- Control plane: ~15 minutes
- Each node pool: ~20-30 minutes (1 node at a time)
- **Total: ~2 hours** for conservative approach

This plan prioritizes **data safety over speed** - appropriate for production Elasticsearch. The regional PVs and PDBs provide the safety net, while the conservative surge settings ensure minimal simultaneous disruption to your cluster quorum.
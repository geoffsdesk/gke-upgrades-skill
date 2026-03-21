# GKE Upgrade Plan: Elasticsearch Cluster (1.31 → 1.32)

## Overview
- **Cluster**: Standard GKE
- **Current**: 1.31 → **Target**: 1.32 
- **Workload**: Elasticsearch StatefulSet (3 master, 5 data, 2 coordinating nodes)
- **Storage**: Regional pd-ssd PVs
- **Priority**: Zero data loss, minimal availability impact

## Pre-Upgrade Preparation

### 1. Elasticsearch Cluster Health Check
```bash
# Verify cluster is green and all shards allocated
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health?pretty"
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/shards?v" | grep UNASSIGNED

# Check shard allocation settings (disable if needed)
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/settings?pretty"
```

### 2. Backup Strategy
```bash
# Verify snapshot repository is configured
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_snapshot?pretty"

# Create pre-upgrade snapshot
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_snapshot/my-repo/pre-upgrade-$(date +%Y%m%d)" \
  -H 'Content-Type: application/json' \
  -d '{"indices": "*", "ignore_unavailable": true, "include_global_state": true}'
```

### 3. PV Backup (Additional Safety)
```bash
# Create disk snapshots of all PVs
kubectl get pv | grep es- | awk '{print $1}' | while read pv; do
  DISK=$(kubectl get pv $pv -o jsonpath='{.spec.csi.volumeHandle}' | cut -d'/' -f6)
  gcloud compute disks snapshot $DISK --snapshot-names=${pv}-pre-upgrade-$(date +%Y%m%d) --zone=YOUR_ZONE
done
```

## Node Pool Upgrade Strategy

Given Elasticsearch's data sensitivity, we'll use **conservative surge settings** and upgrade in this order:
1. **Coordinating nodes** (least risky - stateless)
2. **Master nodes** (critical but small)  
3. **Data nodes** (most sensitive - contains data)

### Configure PDBs for Protection
```yaml
# Apply before upgrade - protects during drain
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: es-master-pdb
spec:
  minAvailable: 2  # Keep quorum of 3 masters
  selector:
    matchLabels:
      component: elasticsearch-master
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: es-data-pdb
spec:
  minAvailable: 4  # Keep majority of 5 data nodes
  selector:
    matchLabels:
      component: elasticsearch-data
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: es-coordinating-pdb
spec:
  minAvailable: 1  # Keep at least 1 of 2 coordinators
  selector:
    matchLabels:
      component: elasticsearch-coordinating
```

## Step-by-Step Upgrade Process

### Phase 1: Control Plane Upgrade
```bash
# Upgrade control plane first (required before nodes)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.X-gke.XXXX

# Verify (~10-15 minutes)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

### Phase 2: Coordinating Node Pool (Least Risky)
```bash
# Configure conservative surge - no capacity dip
gcloud container node-pools update coordinating-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade coordinating nodes
gcloud container node-pools upgrade coordinating-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.X-gke.XXXX

# Monitor Elasticsearch during upgrade
watch 'kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health" | jq .status'
```

### Phase 3: Master Node Pool (Critical)
```bash
# Disable shard allocation during master upgrades (prevents unnecessary shard movement)
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" \
  -H 'Content-Type: application/json' \
  -d '{"persistent": {"cluster.routing.allocation.enable": "primaries"}}'

# Configure very conservative surge for masters
gcloud container node-pools update master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade master nodes
gcloud container node-pools upgrade master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.X-gke.XXXX

# Wait for master quorum to stabilize
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/master?v"

# Re-enable shard allocation
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" \
  -H 'Content-Type: application/json' \
  -d '{"persistent": {"cluster.routing.allocation.enable": "all"}}'
```

### Phase 4: Data Node Pool (Most Sensitive)
```bash
# Temporarily disable shard allocation to prevent rebalancing during upgrades
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" \
  -H 'Content-Type: application/json' \
  -d '{"persistent": {"cluster.routing.allocation.enable": "primaries"}}'

# Use maxUnavailable=0 to ensure no data capacity loss
gcloud container node-pools update data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade data nodes
gcloud container node-pools upgrade data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.X-gke.XXXX

# Monitor shard health throughout
watch 'kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/shards?v" | grep -c UNASSIGNED'
```

## During Each Phase - Monitoring Commands

```bash
# Cluster health (should stay GREEN)
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health?pretty"

# Node upgrade progress
kubectl get nodes -o wide -l cloud.google.com/gke-nodepool=POOL_NAME

# Pod status during drain/reschedule
kubectl get pods -l app=elasticsearch -o wide

# PV attachment status (critical for StatefulSets)
kubectl get pvc -l app=elasticsearch
```

## Post-Upgrade Validation

### 1. Elasticsearch Cluster Health
```bash
# Re-enable full shard allocation
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" \
  -H 'Content-Type: application/json' \
  -d '{"persistent": {"cluster.routing.allocation.enable": "all"}}'

# Verify cluster is GREEN and all nodes joined
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health?pretty"
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/nodes?v"

# Verify all shards allocated
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/shards?v" | grep UNASSIGNED
# Should return no results

# Check data integrity
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/indices?v"
```

### 2. GKE Infrastructure
```bash
# Verify all nodes at target version
kubectl get nodes -o wide

# Verify all PVs still bound
kubectl get pvc -l app=elasticsearch

# Verify no pod issues
kubectl get pods -l app=elasticsearch | grep -v Running
```

### 3. Application Testing
```bash
# Test search functionality
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_search?q=*:*&size=1"

# Test indexing
kubectl exec -it es-master-0 -- curl -X POST "localhost:9200/test-index/_doc/" \
  -H 'Content-Type: application/json' \
  -d '{"test": "post-upgrade", "timestamp": "'$(date -Iseconds)'"}'
```

## Key Elasticsearch-Specific Considerations

1. **Shard allocation control**: Temporarily disable allocation during sensitive phases to prevent unnecessary data movement
2. **Master quorum**: With 3 masters, always maintain at least 2 online (PDB protects this)
3. **Data node capacity**: Never let more than 1 data node be unavailable simultaneously with regional PVs
4. **PV reattachment**: Regional pd-ssd can attach to nodes in any zone, reducing risk during rescheduling
5. **Cluster state persistence**: StatefulSet ensures pod names/identities are preserved across restarts

## Rollback Plan (If Needed)

If issues arise, data nodes can be rolled back by creating new node pools at the previous version:

```bash
# Create replacement data node pool at previous version
gcloud container node-pools create data-pool-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.X-gke.XXXX \
  --num-nodes 5 \
  --machine-type YOUR_MACHINE_TYPE

# Cordon new data pool and migrate StatefulSet
kubectl cordon -l cloud.google.com/gke-nodepool=data-pool
# StatefulSet pods will reschedule to rollback pool with same PVs
```

The regional PVs will reattach automatically as StatefulSet pods reschedule, preserving all data.
# Elasticsearch Cluster Upgrade Plan: GKE 1.31 → 1.32

This plan ensures zero data loss and maintains cluster availability during the upgrade of your StatefulSet-based Elasticsearch cluster.

## Cluster Configuration Summary
- **Current version:** 1.31 → **Target:** 1.32
- **Workload:** Elasticsearch with 3 masters, 5 data nodes, 2 coordinators
- **Storage:** Regional pd-ssd PVs (survives node replacement)
- **Node pools:** 3 separate pools (masters, data, coordinators)

## Pre-Upgrade Checklist

```
Pre-Upgrade Checklist - Elasticsearch on GKE
- [ ] Current ES cluster health: GREEN
- [ ] All shards allocated and replicas in sync
- [ ] No ongoing rebalancing operations
- [ ] Application-level backup completed (snapshot to GCS)
- [ ] PV reclaim policies verified as "Retain"
- [ ] PDBs configured for each ES node type
- [ ] Elasticsearch version compatibility with K8s 1.32 confirmed
- [ ] Surge settings calculated per node pool
- [ ] Maintenance window scheduled (off-peak, 4-6 hour window)
```

## Step 1: Pre-Flight Validation

```bash
# Check cluster health
kubectl get nodes -o wide
gcloud container clusters describe CLUSTER_NAME --zone ZONE

# Verify Elasticsearch cluster health
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"
# Should show: "status": "green", "number_of_nodes": 10

# Check PV reclaim policies (critical for data safety)
kubectl get pv -o custom-columns=NAME:.metadata.name,RECLAIM:.spec.persistentVolumeReclaimPolicy
# All should show "Retain"

# Verify no ongoing ES operations
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?level=shards&pretty"
```

## Step 2: Configure PDBs for Each Node Type

Essential for protecting Elasticsearch quorum during upgrades:

```bash
# Masters PDB (allow 1 master drain, keep quorum of 2)
cat <<EOF | kubectl apply -f -
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: es-masters-pdb
  namespace: elasticsearch
spec:
  minAvailable: 2
  selector:
    matchLabels:
      node.elasticsearch.io/master: "true"
EOF

# Data nodes PDB (allow 1-2 data nodes drain, keep majority)
cat <<EOF | kubectl apply -f -
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: es-data-pdb
  namespace: elasticsearch
spec:
  minAvailable: 4
  selector:
    matchLabels:
      node.elasticsearch.io/data: "true"
EOF

# Coordinators PDB (allow 1 coordinator drain)
cat <<EOF | kubectl apply -f -
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: es-coordinators-pdb
  namespace: elasticsearch
spec:
  minAvailable: 1
  selector:
    matchLabels:
      node.elasticsearch.io/ingest: "true"
EOF
```

## Step 3: Take Application-Level Backup

**Critical:** Always backup before upgrading stateful workloads:

```bash
# Create snapshot repository (if not exists)
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_snapshot/gcs-backup" -H 'Content-Type: application/json' -d'
{
  "type": "gcs",
  "settings": {
    "bucket": "your-es-backup-bucket",
    "base_path": "elasticsearch-snapshots"
  }
}'

# Take full cluster snapshot
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_snapshot/gcs-backup/pre-k8s-upgrade-$(date +%Y%m%d-%H%M)" -H 'Content-Type: application/json' -d'
{
  "indices": "*",
  "ignore_unavailable": true,
  "include_global_state": true
}'

# Verify snapshot success
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_snapshot/gcs-backup/_all?pretty"
```

## Step 4: Configure Node Pool Upgrade Strategy

Set conservative surge settings for each pool:

```bash
# Coordinator nodes - least critical, upgrade first
gcloud container node-pools update es-coordinators \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Data nodes - most critical for data safety
gcloud container node-pools update es-data \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Master nodes - critical for cluster coordination
gcloud container node-pools update es-masters \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

## Step 5: Control Plane Upgrade

```bash
# Upgrade control plane first (required order)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.0-gke.PATCH_VERSION

# Monitor progress (~10-15 minutes)
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --limit 1

# Verify control plane version
gcloud container clusters describe CLUSTER_NAME --zone ZONE \
  --format="value(currentMasterVersion)"
```

## Step 6: Node Pool Upgrades (Sequential)

Upgrade in this order: **Coordinators → Data → Masters**

### 6a. Coordinators First (Lowest Risk)

```bash
# Start coordinator upgrade
gcloud container node-pools upgrade es-coordinators \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.0-gke.PATCH_VERSION

# Monitor ES cluster health during upgrade
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"
# Should remain GREEN throughout

# Wait for completion before next pool
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=es-coordinators'
```

### 6b. Data Nodes (Most Critical)

```bash
# Verify ES health before data node upgrade
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?level=shards&pretty"

# Start data node upgrade (one node at a time due to maxSurge=1)
gcloud container node-pools upgrade es-data \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.0-gke.PATCH_VERSION

# Critical: Monitor shard allocation during data node drains
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/shards?v&s=index"

# Watch for any UNASSIGNED shards (should be temporary)
while true; do
  echo "=== $(date) ==="
  kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health" | jq '.status, .number_of_nodes, .active_shards'
  sleep 30
done
```

### 6c. Masters Last (Cluster Coordination)

```bash
# Final health check before master upgrade
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"

# Upgrade masters (PDB ensures 2 masters remain during drain)
gcloud container node-pools upgrade es-masters \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.0-gke.PATCH_VERSION

# Monitor master election stability
kubectl logs -f -l node.elasticsearch.io/master=true --tail=50
```

## Step 7: Post-Upgrade Validation

```bash
# Verify all nodes upgraded
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE
kubectl get nodes -o wide

# Elasticsearch cluster health (should be GREEN with all 10 nodes)
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"

# Verify all shards allocated
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/shards?v" | grep -c UNASSIGNED
# Should return 0

# Check StatefulSet status
kubectl get statefulsets -n elasticsearch
kubectl get pods -n elasticsearch

# Performance test (optional)
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/stats?pretty"
```

## What to Expect During Each Phase

### During Coordinator Upgrades
- **Impact:** Minimal - clients can connect directly to data/master nodes
- **Duration:** ~20-30 minutes for 2 nodes (maxSurge=1)
- **ES Status:** Should remain GREEN

### During Data Node Upgrades  
- **Impact:** Temporary shard relocations as nodes drain
- **Duration:** ~45-60 minutes for 5 nodes (longest phase)
- **ES Status:** May briefly show YELLOW during shard movements, should return to GREEN
- **Watch for:** UNASSIGNED shards (should auto-resolve within 5-10 minutes)

### During Master Upgrades
- **Impact:** Brief master election during each drain
- **Duration:** ~30-45 minutes for 3 nodes  
- **ES Status:** Should remain GREEN (quorum maintained by PDB)

## Rollback Plan (If Needed)

If critical issues arise:

1. **Stop the upgrade:**
   ```bash
   # Note: Cannot stop mid-node, but can prevent starting next pool
   ```

2. **ES-level rollback:**
   ```bash
   # Restore from snapshot if data corruption occurs
   kubectl exec -it es-master-0 -- curl -X POST "localhost:9200/_snapshot/gcs-backup/pre-k8s-upgrade-TIMESTAMP/_restore"
   ```

3. **Node-level rollback (requires new pool):**
   ```bash
   # Create new pool at old version and migrate workloads
   gcloud container node-pools create es-data-rollback \
     --cluster CLUSTER_NAME --zone ZONE \
     --cluster-version 1.31.X-gke.PATCH
   ```

## Troubleshooting Common Issues

### PDB Blocks Drain
```bash
# Check PDB status
kubectl describe pdb es-masters-pdb
# Temporarily increase maxUnavailable if safe
```

### Shards Stuck UNASSIGNED
```bash
# Check shard allocation explanation
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/allocation/explain?pretty"
# May need to manually reroute in extreme cases
```

### StatefulSet Pods Stuck
```bash
# Check PVC attachment
kubectl get pvc -n elasticsearch
kubectl describe pod es-data-0 -n elasticsearch
# Regional PVs should reattach automatically
```

## Timeline Estimate

- **Control plane:** 15 minutes
- **Coordinator nodes:** 30 minutes  
- **Data nodes:** 60 minutes (most critical)
- **Master nodes:** 45 minutes
- **Validation:** 15 minutes
- **Total:** ~2.5-3 hours

Plan for a 4-6 hour maintenance window to account for any troubleshooting.

This approach prioritizes data safety through application-level backups, conservative surge settings, and proper PDB configuration while maintaining Elasticsearch cluster quorum throughout the upgrade process.
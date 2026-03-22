# GKE Upgrade Plan: Elasticsearch Cluster (1.31 → 1.32)

## Cluster Overview
- **Mode:** Standard
- **Current:** 1.31 → **Target:** 1.32
- **Workload:** Elasticsearch StatefulSet (3 masters, 5 data, 2 coordinating)
- **Storage:** Regional pd-ssd PVs
- **Risk Level:** High (stateful data cluster)

## Pre-Upgrade Strategy

### Elasticsearch-Specific Preparation

**1. Disable shard allocation (critical for data safety):**
```bash
# Prevent Elasticsearch from moving shards during node drain
curl -X PUT "elasticsearch-master:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'
```

**2. Verify cluster health:**
```bash
# Must be GREEN before proceeding
curl -X GET "elasticsearch-master:9200/_cluster/health?pretty"
curl -X GET "elasticsearch-master:9200/_cat/nodes?v"
curl -X GET "elasticsearch-master:9200/_cat/shards?v&h=index,shard,prirep,state,unassigned.reason"
```

**3. Create snapshot backup:**
```bash
# Register snapshot repository (if not already done)
curl -X PUT "elasticsearch-master:9200/_snapshot/gcs-backup" -H 'Content-Type: application/json' -d'
{
  "type": "gcs",
  "settings": {
    "bucket": "your-backup-bucket",
    "base_path": "elasticsearch-snapshots"
  }
}'

# Create pre-upgrade snapshot
curl -X PUT "elasticsearch-master:9200/_snapshot/gcs-backup/pre-upgrade-1.32-$(date +%Y%m%d)" -H 'Content-Type: application/json' -d'
{
  "indices": "*",
  "ignore_unavailable": true,
  "include_global_state": true
}'
```

### Node Pool Configuration

**Configure conservative upgrade settings for all pools:**
```bash
# Master nodes (most critical - one at a time)
gcloud container node-pools update es-master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1

# Data nodes (conservative, respect quorum)
gcloud container node-pools update es-data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1

# Coordinating nodes (can be more aggressive)
gcloud container node-pools update es-coord-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### PodDisruptionBudget Verification

**Check existing PDBs (must not be overly restrictive):**
```bash
kubectl get pdb -A -o wide
# For Elasticsearch, typically:
# - Master: minAvailable: 2 (maintain quorum)
# - Data: minAvailable: 4 (keep majority online)
# - Coordinating: minAvailable: 1
```

**If PDBs are too restrictive, temporarily adjust:**
```bash
# Example: relax data node PDB during upgrade
kubectl patch pdb elasticsearch-data-pdb -n elasticsearch \
  -p '{"spec":{"minAvailable":3}}'  # Allow 2 simultaneous disruptions instead of 1
```

## Upgrade Execution

### Phase 1: Control Plane
```bash
# Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32

# Monitor (~10-15 minutes)
watch 'gcloud container clusters describe CLUSTER_NAME --zone ZONE --format="value(currentMasterVersion)"'
```

### Phase 2: Node Pools (Sequential Order)

**Order:** Coordinating → Data → Masters (least to most critical)

**2a. Coordinating Nodes:**
```bash
gcloud container node-pools upgrade es-coord-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor until complete
watch 'kubectl get nodes -l node-pool=es-coord-pool'
```

**2b. Data Nodes (most time-consuming):**
```bash
gcloud container node-pools upgrade es-data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor node-by-node upgrade (will take ~30-45 min per node)
watch 'kubectl get nodes -l node-pool=es-data-pool -o wide'

# Watch Elasticsearch cluster health during data node upgrades
while true; do
  curl -s "elasticsearch-master:9200/_cluster/health?pretty" | grep status
  sleep 30
done
```

**2c. Master Nodes (final, most critical):**
```bash
gcloud container node-pools upgrade es-master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor master quorum carefully
watch 'kubectl get pods -n elasticsearch -l component=master'
```

## Post-Upgrade Recovery

### Re-enable Shard Allocation
```bash
# Critical: restore normal shard allocation
curl -X PUT "elasticsearch-master:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": null
  }
}'
```

### Verification Checklist
```bash
# Cluster health (must return to GREEN)
curl -X GET "elasticsearch-master:9200/_cluster/health?pretty"

# All nodes visible
curl -X GET "elasticsearch-master:9200/_cat/nodes?v"

# No unassigned shards
curl -X GET "elasticsearch-master:9200/_cat/shards?v&h=index,shard,prirep,state" | grep UNASSIGNED

# All StatefulSets ready
kubectl get statefulsets -n elasticsearch

# PV status
kubectl get pv | grep elasticsearch
```

### Restore Original PDB Settings
```bash
# Restore stricter PDB if you relaxed it
kubectl patch pdb elasticsearch-data-pdb -n elasticsearch \
  -p '{"spec":{"minAvailable":4}}'
```

## Troubleshooting Elasticsearch-Specific Issues

### If Shards Go Unassigned During Upgrade:
```bash
# Check why shards are unassigned
curl -X GET "elasticsearch-master:9200/_cluster/allocation/explain?pretty" -H 'Content-Type: application/json' -d'
{
  "index": "INDEX_NAME",
  "shard": 0,
  "primary": true
}'

# Force allocation if necessary (emergency only)
curl -X POST "elasticsearch-master:9200/_cluster/reroute" -H 'Content-Type: application/json' -d'
{
  "commands": [
    {
      "allocate_primary": {
        "index": "INDEX_NAME",
        "shard": 0,
        "node": "NODE_NAME",
        "accept_data_loss": false
      }
    }
  ]
}'
```

### If Elasticsearch Won't Start After Node Upgrade:
```bash
# Check pod logs
kubectl logs -n elasticsearch elasticsearch-data-0 --previous

# Common issues:
# - JVM heap size incompatible with new node
# - Volume attachment problems
# - Cluster discovery timeout

# Check PV attachment
kubectl describe pod elasticsearch-data-0 -n elasticsearch
kubectl get pv -o wide | grep elasticsearch-data-0
```

## Key Differences for Regional PD-SSD

- **Advantage:** Regional PDs can reattach to nodes in any zone, reducing attachment failure risk
- **Timing:** Initial volume attachment may take 1-2 minutes per pod
- **Monitoring:** Watch for `FailedAttachVolume` events during pod rescheduling

## Estimated Timeline

- **Control plane:** 15 minutes
- **Coordinating nodes:** 20 minutes (2 nodes with surge)  
- **Data nodes:** 90 minutes (5 nodes × ~15 min each + shard rebalancing)
- **Master nodes:** 45 minutes (3 nodes × 15 min each, sequential)
- **Total:** ~2.5-3 hours

## Emergency Rollback

If the cluster becomes unhealthy:

1. **Don't panic** - regional PDs preserve data
2. **Check snapshot:** Verify backup completed successfully
3. **Node pool recreation:** Create new node pools at 1.31, migrate workloads
4. **Data recovery:** Restore from snapshot if necessary

The conservative upgrade approach (maxUnavailable=1, disabled shard allocation) prioritizes data safety over speed. Your Elasticsearch cluster should maintain availability throughout the process.
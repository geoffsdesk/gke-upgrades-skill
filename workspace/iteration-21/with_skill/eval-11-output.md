# GKE Elasticsearch Upgrade Plan: 1.31 → 1.32

## Cluster Overview
- **Mode**: GKE Standard
- **Current**: 1.31 → **Target**: 1.32
- **Workload**: Elasticsearch with 3 masters, 5 data nodes, 2 coordinators
- **Storage**: Regional pd-ssd PVs (good - survives node changes)

## Pre-Upgrade Checklist

### Elasticsearch-Specific Preparation
- [ ] **Elasticsearch health check**: `curl -X GET "localhost:9200/_cluster/health?pretty"` - must be GREEN
- [ ] **Disable shard allocation**: Prevent rebalancing during upgrade
  ```bash
  curl -X PUT "localhost:9200/_cluster/settings?pretty" -H 'Content-Type: application/json' -d'
  {
    "persistent": {
      "cluster.routing.allocation.enable": "primaries"
    }
  }'
  ```
- [ ] **Snapshot backup**: Create full cluster snapshot before starting
  ```bash
  # Register snapshot repository if not exists
  curl -X PUT "localhost:9200/_snapshot/backup_repo?pretty" -H 'Content-Type: application/json' -d'
  {
    "type": "gcs",
    "settings": {
      "bucket": "your-backup-bucket",
      "base_path": "elasticsearch-snapshots"
    }
  }'
  
  # Create snapshot
  curl -X PUT "localhost:9200/_snapshot/backup_repo/pre-upgrade-1.31-to-1.32?wait_for_completion=true&pretty"
  ```

### GKE Compatibility Checks
- [ ] **Version availability**: Verify 1.32 is available in your release channel
  ```bash
  gcloud container get-server-config --zone YOUR_ZONE --format="yaml(channels)"
  ```
- [ ] **Deprecated APIs**: Check for any deprecated API usage
  ```bash
  kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
  ```
- [ ] **PV reclaim policies**: Ensure all set to "Retain" (not "Delete")
  ```bash
  kubectl get pv -o custom-columns=NAME:.metadata.name,RECLAIM:.spec.persistentVolumeReclaimPolicy | grep -v Retain
  ```

### Pod Disruption Budgets (Critical for Elasticsearch)
- [ ] **Configure PDBs for each component**:
  ```yaml
  # Masters PDB - allow 1 master down, keep quorum of 2
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
  # Data nodes PDB - allow 1-2 data nodes down
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
  # Coordinators PDB - allow 1 coordinator down
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

## Upgrade Strategy: Conservative Surge with Proper Sequencing

### Node Pool Upgrade Settings
For Elasticsearch, use conservative surge settings to minimize disruption:

```bash
# Coordinator nodes (least critical) - upgrade first
gcloud container node-pools update coordinator-pool \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Data nodes (most critical) - conservative
gcloud container node-pools update data-pool \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Master nodes (critical for cluster state) - most conservative
gcloud container node-pools update master-pool \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

## Step-by-Step Upgrade Runbook

### Phase 1: Control Plane Upgrade
```bash
# 1. Upgrade control plane first (required before nodes)
gcloud container clusters upgrade YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --master \
  --cluster-version 1.32

# 2. Wait for completion and verify (~10-15 minutes)
gcloud container clusters describe YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --format="value(currentMasterVersion)"

# 3. Verify system pods healthy
kubectl get pods -n kube-system
```

### Phase 2: Node Pool Upgrades (Sequential)

**Step 1: Coordinator Nodes First (Lowest Risk)**
```bash
# Upgrade coordinators
gcloud container node-pools upgrade coordinator-pool \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --cluster-version 1.32

# Monitor progress
watch 'kubectl get nodes -l node-role=coordinator -o wide'

# Validate Elasticsearch health after coordinators
curl -X GET "localhost:9200/_cluster/health?pretty"
```

**Step 2: Data Nodes (Critical - Monitor Closely)**
```bash
# Before upgrading data nodes, verify cluster is GREEN
curl -X GET "localhost:9200/_cluster/health?pretty"

# Upgrade data pool
gcloud container node-pools upgrade data-pool \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --cluster-version 1.32

# Monitor each data node upgrade closely
watch 'kubectl get nodes -l node-role=data -o wide'
watch 'kubectl get pods -l role=data -o wide'

# After each data node replacement, check cluster health
curl -X GET "localhost:9200/_cluster/health?pretty"
curl -X GET "localhost:9200/_cat/shards?v&h=index,shard,prirep,state,unassigned.reason"
```

**Step 3: Master Nodes Last (Most Critical)**
```bash
# Verify cluster is stable before touching masters
curl -X GET "localhost:9200/_cluster/health?pretty"

# Upgrade master pool (one at a time with surge=1)
gcloud container node-pools upgrade master-pool \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --cluster-version 1.32

# Monitor master elections during upgrade
watch 'kubectl get pods -l role=master -o wide'
# Check Elasticsearch logs for master election messages
kubectl logs -l role=master --tail=20
```

### Phase 3: Post-Upgrade Validation

**Re-enable Shard Allocation**
```bash
curl -X PUT "localhost:9200/_cluster/settings?pretty" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": null
  }
}'
```

**Comprehensive Health Checks**
```bash
# 1. All nodes at target version
kubectl get nodes -o wide

# 2. All pods running
kubectl get pods -A | grep -v Running | grep -v Completed

# 3. Elasticsearch cluster health GREEN
curl -X GET "localhost:9200/_cluster/health?pretty"

# 4. All shards assigned
curl -X GET "localhost:9200/_cat/shards?v&h=index,shard,prirep,state,unassigned.reason" | grep -i unassigned

# 5. Cluster stats normal
curl -X GET "localhost:9200/_cluster/stats?pretty"

# 6. Test index/search operations
curl -X POST "localhost:9200/test-upgrade/_doc/" -H 'Content-Type: application/json' -d'{"message":"upgrade test","timestamp":"2024-01-01"}'
curl -X GET "localhost:9200/test-upgrade/_search?pretty"
```

## Rollback Plan (If Issues Arise)

**If Elasticsearch becomes unhealthy during upgrade:**

1. **Pause the upgrade** (won't stop current node, but prevents next):
   ```bash
   # No direct pause command, but you can create maintenance exclusion
   gcloud container clusters update YOUR_CLUSTER \
     --zone YOUR_ZONE \
     --add-maintenance-exclusion-name "pause-upgrade" \
     --add-maintenance-exclusion-start "2024-01-01T00:00:00Z" \
     --add-maintenance-exclusion-end "2024-01-01T23:59:59Z" \
     --add-maintenance-exclusion-scope no_upgrades
   ```

2. **Restore from snapshot if data corruption**:
   ```bash
   curl -X POST "localhost:9200/_snapshot/backup_repo/pre-upgrade-1.31-to-1.32/_restore?wait_for_completion=true&pretty"
   ```

3. **Create new node pool at 1.31** (if rollback needed):
   ```bash
   gcloud container node-pools create data-pool-rollback \
     --cluster YOUR_CLUSTER \
     --zone YOUR_ZONE \
     --cluster-version 1.31 \
     --num-nodes 5 \
     --machine-type YOUR_MACHINE_TYPE
   ```

## Troubleshooting Common Issues

### Data Node Won't Drain
**Symptom**: Node stuck draining, Elasticsearch showing unassigned shards
```bash
# Check which shards are blocking
curl -X GET "localhost:9200/_cat/shards?v&h=index,shard,prirep,state,unassigned.reason" | grep UNASSIGNED

# Temporarily disable replica requirements
curl -X PUT "localhost:9200/_all/_settings?pretty" -H 'Content-Type: application/json' -d'
{
  "index": {
    "number_of_replicas": 0
  }
}'
```

### PDB Blocking Master Replacement
**Symptom**: Master node won't drain due to PDB
```bash
# Temporarily allow more master disruption (restore after)
kubectl patch pdb es-master-pdb -p '{"spec":{"minAvailable":1}}'
```

### Long Termination Grace Periods
```bash
# Check if Elasticsearch pods have long termination periods
kubectl get pods -l app=elasticsearch -o json | \
  jq '.items[] | {name:.metadata.name, grace:.spec.terminationGracePeriodSeconds}'

# If >300s, consider reducing for faster drain
```

## Timeline Expectations

- **Control Plane**: 10-15 minutes
- **Coordinator Pool**: 15-30 minutes (2 nodes)  
- **Data Pool**: 45-75 minutes (5 nodes, one at a time)
- **Master Pool**: 30-45 minutes (3 nodes, one at a time)
- **Total**: ~2-3 hours

**Success Criteria**: 
- ✅ All nodes at 1.32
- ✅ Elasticsearch cluster health: GREEN  
- ✅ All shards: ASSIGNED
- ✅ No data loss (verify with test queries)

This conservative approach prioritizes data safety over speed. The upgrade sequence (coordinators → data → masters) ensures Elasticsearch cluster stability throughout the process.
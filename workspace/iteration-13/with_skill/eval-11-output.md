# Elasticsearch Cluster Upgrade Plan: GKE 1.31 → 1.32

## Cluster Overview
- **Mode:** Standard
- **Current:** 1.31 → **Target:** 1.32 (single minor version jump ✓)
- **Topology:** 3 master + 5 data + 2 coordinating nodes (separate pools)
- **Storage:** Regional pd-ssd PVs (good for availability)

## Pre-Upgrade Checklist

### Elasticsearch-Specific Preparations
```bash
# 1. Disable shard allocation (prevents data movement during node restarts)
curl -X PUT "elasticsearch-service:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "none"
  }
}'

# 2. Perform synced flush
curl -X POST "elasticsearch-service:9200/_flush/synced"

# 3. Backup cluster state and indices
curl -X PUT "elasticsearch-service:9200/_snapshot/my_backup_repo/pre_upgrade_snapshot?wait_for_completion=true"

# 4. Check cluster health
curl -X GET "elasticsearch-service:9200/_cluster/health?pretty"
```

### GKE Compatibility Checks
```bash
# Verify 1.32 available in your release channel
gcloud container get-server-config --zone ZONE --format="yaml(channels)"

# Check for deprecated API usage
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Verify current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].version)"
```

### Workload Readiness
```bash
# Configure PDBs for each ES component (if not already set)
kubectl apply -f - <<EOF
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: es-master-pdb
  namespace: elasticsearch
spec:
  minAvailable: 2  # Allow 1 master down (quorum = 2/3)
  selector:
    matchLabels:
      app: elasticsearch
      role: master
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: es-data-pdb
  namespace: elasticsearch
spec:
  maxUnavailable: 1  # Conservative: 1 data node at a time
  selector:
    matchLabels:
      app: elasticsearch
      role: data
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: es-coordinating-pdb
  namespace: elasticsearch
spec:
  minAvailable: 1  # Keep at least 1 coordinating node
  selector:
    matchLabels:
      app: elasticsearch
      role: coordinating
EOF
```

## Node Pool Upgrade Strategy

**Recommended approach:** Conservative surge settings with careful sequencing to maintain quorum and data availability.

### Configure Surge Settings
```bash
# Coordinating nodes (least critical) - can handle more disruption
gcloud container node-pools update coordinating-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Master nodes (quorum-sensitive) - very conservative
gcloud container node-pools update master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Data nodes (storage-sensitive) - conservative
gcloud container node-pools update data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

## Step-by-Step Upgrade Process

### Phase 1: Control Plane Upgrade
```bash
# Upgrade control plane first (required)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32

# Wait and verify (~10-15 minutes)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

### Phase 2: Coordinating Nodes (First - Least Critical)
```bash
gcloud container node-pools upgrade coordinating-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor progress
watch 'kubectl get nodes -l node-role=coordinating'

# Verify Elasticsearch cluster health after each pool
curl -X GET "elasticsearch-service:9200/_cluster/health?pretty"
```

### Phase 3: Data Nodes (Second - Most Critical)
```bash
gcloud container node-pools upgrade data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor carefully - each data node restart affects shard distribution
watch 'kubectl get nodes -l node-role=data'

# Check shard allocation during upgrade
curl -X GET "elasticsearch-service:9200/_cat/shards?v&h=index,shard,prirep,state,unassigned.reason"
```

### Phase 4: Master Nodes (Last - Maintain Quorum)
```bash
gcloud container node-pools upgrade master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Critical: Monitor master quorum during upgrade
watch 'kubectl get nodes -l node-role=master'

# Verify cluster can elect master
curl -X GET "elasticsearch-service:9200/_cat/master?v"
```

## Post-Upgrade Recovery

### Re-enable Shard Allocation
```bash
# 1. Re-enable shard allocation
curl -X PUT "elasticsearch-service:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": null
  }
}'

# 2. Monitor shard rebalancing
curl -X GET "elasticsearch-service:9200/_cat/health?v"
curl -X GET "elasticsearch-service:9200/_cat/shards?v&h=index,shard,prirep,state"

# 3. Wait for cluster to return to GREEN status
while true; do
  STATUS=$(curl -s "elasticsearch-service:9200/_cluster/health" | jq -r .status)
  echo "Cluster status: $STATUS"
  [ "$STATUS" = "green" ] && break
  sleep 30
done
```

### Validation Checklist
```bash
# Verify all components
kubectl get pods -l app=elasticsearch -o wide
kubectl get pvc -l app=elasticsearch

# Test cluster functionality
curl -X GET "elasticsearch-service:9200/_cluster/stats?pretty"
curl -X GET "elasticsearch-service:9200/_cat/indices?v"

# Perform a test search
curl -X GET "elasticsearch-service:9200/_search?q=*:*&size=1&pretty"
```

## Rollback Plan (If Needed)

If issues arise during data node upgrade:

```bash
# 1. Stop the upgrade operation
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE
# Note the operation ID, then contact GKE support if needed

# 2. Emergency: Restore from snapshot
curl -X POST "elasticsearch-service:9200/_snapshot/my_backup_repo/pre_upgrade_snapshot/_restore?wait_for_completion=true"

# 3. Re-enable shard allocation if disabled
curl -X PUT "elasticsearch-service:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": null
  }
}'
```

## Key Risk Mitigations

1. **Regional PVs** protect against zone failures during upgrade
2. **PDB configurations** ensure minimum ES quorum maintained
3. **Disabled shard allocation** prevents unnecessary data movement
4. **Sequential pool upgrades** maintain service availability
5. **Conservative surge settings** minimize simultaneous disruptions
6. **Pre-upgrade snapshot** provides rollback option

## Expected Timeline
- Control plane: ~15 minutes
- Each node pool: ~30-45 minutes (3 pools × 45min = ~2.5 hours)
- Shard rebalancing: ~30-60 minutes post-upgrade
- **Total:** ~3.5-4 hours

Monitor Elasticsearch cluster health between each phase. Don't proceed to the next node pool until the cluster returns to GREEN status.
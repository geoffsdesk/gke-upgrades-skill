I'll walk you through a comprehensive GKE upgrade strategy for your Elasticsearch cluster that maintains both data integrity and availability.

## Pre-Upgrade Preparation

### 1. Create Full Backup
```bash
# Create snapshot repository (if not already configured)
curl -X PUT "elasticsearch-service:9200/_snapshot/gcs-backup" -H 'Content-Type: application/json' -d'
{
  "type": "gcs",
  "settings": {
    "bucket": "your-backup-bucket",
    "base_path": "elasticsearch-snapshots"
  }
}'

# Create comprehensive snapshot
curl -X PUT "elasticsearch-service:9200/_snapshot/gcs-backup/pre-upgrade-$(date +%Y%m%d)" -H 'Content-Type: application/json' -d'
{
  "indices": "*",
  "ignore_unavailable": true,
  "include_global_state": true,
  "metadata": {
    "taken_by": "pre-upgrade-backup",
    "taken_because": "gke-upgrade-1.31-to-1.32"
  }
}'
```

### 2. Verify Cluster Health
```bash
# Check cluster status
kubectl get pods -l app=elasticsearch
curl -X GET "elasticsearch-service:9200/_cluster/health?pretty"
curl -X GET "elasticsearch-service:9200/_cat/nodes?v"

# Verify all shards are allocated
curl -X GET "elasticsearch-service:9200/_cat/shards?v&h=index,shard,prirep,state,unassigned.reason"
```

### 3. Disable Shard Allocation (Temporary)
```bash
curl -X PUT "elasticsearch-service:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'
```

## Upgrade Strategy: Rolling Node Pool Updates

### Phase 1: Upgrade Coordinating Nodes (Lowest Risk)

```bash
# Get current node pool version
gcloud container node-pools describe coordinating-pool \
  --cluster=your-cluster-name \
  --zone=your-zone

# Upgrade coordinating node pool
gcloud container node-pools upgrade coordinating-pool \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32.x-gke.xxx

# Monitor pod disruption
kubectl get pods -l role=coordinating -w
```

### Phase 2: Upgrade Master Nodes (Critical Path)

```bash
# Temporarily increase master node count for safety
kubectl scale statefulset elasticsearch-master --replicas=5

# Wait for new masters to join
kubectl get pods -l role=master
curl -X GET "elasticsearch-service:9200/_cat/nodes?v&h=name,role,master"

# Upgrade master node pool
gcloud container node-pools upgrade master-pool \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32.x-gke.xxx

# After upgrade, scale back to 3 masters
kubectl scale statefulset elasticsearch-master --replicas=3
```

### Phase 3: Upgrade Data Nodes (Most Critical)

```bash
# Enable controlled shard rebalancing
curl -X PUT "elasticsearch-service:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "all",
    "cluster.routing.allocation.cluster_concurrent_rebalance": "2",
    "cluster.routing.allocation.node_concurrent_recoveries": "2"
  }
}'

# Upgrade data node pool (this will be done in rolling fashion)
gcloud container node-pools upgrade data-pool \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --node-version=1.32.x-gke.xxx \
  --max-surge=1 \
  --max-unavailable=1
```

## Monitoring During Upgrade

### 1. Create Monitoring Script
```bash
#!/bin/bash
# monitor-upgrade.sh

while true; do
  echo "=== $(date) ==="
  
  # Cluster health
  curl -s "elasticsearch-service:9200/_cluster/health" | jq .
  
  # Node status
  kubectl get nodes -l cloud.google.com/gke-nodepool=data-pool
  
  # Pod status
  kubectl get pods -l role=data --field-selector=status.phase!=Running
  
  # Shard allocation
  curl -s "elasticsearch-service:9200/_cat/shards?h=state" | sort | uniq -c
  
  sleep 30
done
```

### 2. Set Up Alerts
```yaml
# elasticsearch-upgrade-monitoring.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: upgrade-alerts
data:
  check-cluster.sh: |
    #!/bin/bash
    HEALTH=$(curl -s elasticsearch-service:9200/_cluster/health | jq -r .status)
    if [[ "$HEALTH" != "green" && "$HEALTH" != "yellow" ]]; then
      echo "ALERT: Cluster health is $HEALTH"
      exit 1
    fi
```

## Data Node Upgrade Process Detail

### 1. Pre-Node Upgrade
```bash
# Before each data node upgrade, verify:
curl -X GET "elasticsearch-service:9200/_cluster/health?wait_for_status=green&timeout=300s"

# Check for relocating shards
curl -X GET "elasticsearch-service:9200/_cat/shards?h=state" | grep -c RELOCATING
```

### 2. Handle PVC Migration
```yaml
# Verify PVC retention policy
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: elasticsearch-data-elasticsearch-data-0
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 100Gi
  storageClassName: regional-pd-ssd
  # Ensure reclaimPolicy is Retain
```

### 3. StatefulSet Update Strategy
```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: elasticsearch-data
spec:
  updateStrategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1  # Critical: only 1 data node down at a time
  podManagementPolicy: Parallel
```

## Post-Upgrade Verification

### 1. Restore Normal Settings
```bash
# Re-enable full shard allocation
curl -X PUT "elasticsearch-service:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "all",
    "cluster.routing.allocation.cluster_concurrent_rebalance": "4",
    "cluster.routing.allocation.node_concurrent_recoveries": "4"
  }
}'
```

### 2. Comprehensive Health Check
```bash
# Full cluster verification script
#!/bin/bash

echo "=== Cluster Health ==="
curl -X GET "elasticsearch-service:9200/_cluster/health?pretty"

echo "=== Node Count Verification ==="
MASTERS=$(curl -s "elasticsearch-service:9200/_cat/nodes?h=role" | grep -c master)
DATA=$(curl -s "elasticsearch-service:9200/_cat/nodes?h=role" | grep -c data)
COORDS=$(curl -s "elasticsearch-service:9200/_cat/nodes?h=role" | grep -c coordinating_only)

echo "Masters: $MASTERS (expected: 3)"
echo "Data nodes: $DATA (expected: 5)"
echo "Coordinating: $COORDS (expected: 2)"

echo "=== Shard Status ==="
curl -X GET "elasticsearch-service:9200/_cat/shards?v&h=index,shard,prirep,state" | grep -v STARTED | wc -l

echo "=== Index Status ==="
curl -X GET "elasticsearch-service:9200/_cat/indices?v&health=red"

echo "=== GKE Node Versions ==="
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion
```

## Rollback Plan

### If Issues Arise:
```bash
# 1. Stop ongoing upgrade
gcloud container operations cancel OPERATION_ID

# 2. Restore from snapshot if data corruption
curl -X POST "elasticsearch-service:9200/_snapshot/gcs-backup/pre-upgrade-YYYYMMDD/_restore"

# 3. Scale up additional nodes if needed
kubectl scale statefulset elasticsearch-data --replicas=7

# 4. Downgrade node pool (if possible)
gcloud container node-pools rollback data-pool \
  --cluster=your-cluster-name \
  --zone=your-zone
```

## Key Safety Considerations

1. **Never upgrade more than 1 data node simultaneously**
2. **Monitor shard allocation throughout the process**
3. **Maintain quorum of master nodes at all times**
4. **Regional PD-SSD provides data persistence across upgrades**
5. **Test the entire process in a staging environment first**

This approach ensures zero data loss and maintains availability throughout the upgrade process. The regional PD-SSD volumes will automatically reattach to new nodes, preserving your data.
I'll walk you through a safe GKE upgrade strategy for your Elasticsearch cluster. Given your setup with StatefulSets and regional pd-ssd volumes, we can achieve zero data loss, though there will be brief periods of reduced availability.

## Pre-Upgrade Preparation

### 1. Backup and Health Check
```bash
# Check cluster health
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"

# Disable shard allocation (prevents unnecessary shard movement)
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'

# Take a snapshot (if you have snapshot repository configured)
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_snapshot/backup/pre-upgrade-$(date +%Y%m%d)"
```

### 2. Document Current State
```bash
# Save current node pool configurations
gcloud container node-pools list --cluster=YOUR_CLUSTER --zone=YOUR_ZONE > node-pools-backup.txt

# Check PV status
kubectl get pv,pvc -o wide > pv-status-backup.txt
```

## Upgrade Strategy: Node Pool by Node Pool

### Phase 1: Upgrade Coordinating Nodes First
Coordinating nodes are stateless and safest to start with.

```bash
# Upgrade coordinating node pool
gcloud container node-pools upgrade COORDINATING_POOL_NAME \
  --cluster=YOUR_CLUSTER \
  --zone=YOUR_ZONE \
  --node-version=1.32.x-gke.y

# Monitor the upgrade
kubectl get nodes -l node-pool=coordinating -w
```

### Phase 2: Upgrade Master Nodes (One by One)
```bash
# First, ensure you have at least 2 master nodes running
kubectl get pods -l role=master -o wide

# Method 1: Rolling upgrade (safer but slower)
# Scale master StatefulSet to ensure quorum during upgrade
kubectl scale statefulset es-master --replicas=3

# Cordon and drain first master node
NODE_NAME=$(kubectl get nodes -l node-pool=master -o jsonpath='{.items[0].metadata.name}')
kubectl cordon $NODE_NAME
kubectl drain $NODE_NAME --ignore-daemonsets --delete-emptydir-data --force

# Upgrade one master node at a time
gcloud container node-pools upgrade MASTER_POOL_NAME \
  --cluster=YOUR_CLUSTER \
  --zone=YOUR_ZONE \
  --node-version=1.32.x-gke.y \
  --max-surge=1 \
  --max-unavailable=0

# Verify master quorum after each node
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/master?v"
```

### Phase 3: Upgrade Data Nodes (Most Critical)
```bash
# Before starting, ensure cluster is green
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health"

# Upgrade data nodes with careful surge/unavailable settings
gcloud container node-pools upgrade DATA_POOL_NAME \
  --cluster=YOUR_CLUSTER \
  --zone=YOUR_ZONE \
  --node-version=1.32.x-gke.y \
  --max-surge=1 \
  --max-unavailable=1

# Monitor shard allocation during upgrade
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/shards?v" | grep UNASSIGNED
```

## Alternative Approach: Blue-Green Node Pool Upgrade

If you want zero downtime, create new node pools:

```bash
# Create new node pools with 1.32
gcloud container node-pools create master-132 \
  --cluster=YOUR_CLUSTER \
  --zone=YOUR_ZONE \
  --node-version=1.32.x-gke.y \
  --num-nodes=3 \
  --machine-type=YOUR_MASTER_MACHINE_TYPE

# Add node affinity to gradually migrate pods
kubectl patch statefulset es-master -p '
spec:
  template:
    spec:
      affinity:
        nodeAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            preference:
              matchExpressions:
              - key: node-pool
                operator: In
                values:
                - master-132'

# Scale down old node pool after migration
gcloud container node-pools delete MASTER_POOL_NAME --cluster=YOUR_CLUSTER
```

## Post-Upgrade Verification

### 1. Re-enable Shard Allocation
```bash
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "all"
  }
}'
```

### 2. Verify Cluster Health
```bash
# Check cluster health
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"

# Verify all nodes are visible
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/nodes?v"

# Check shard allocation
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/shards?v" | grep -c STARTED
```

### 3. Verify Data Integrity
```bash
# Check index status
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/indices?v"

# Run a test query
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_search?size=1"
```

## Rollback Plan

If issues arise:

```bash
# Emergency: Scale up old node pool (if still available)
gcloud container node-pools resize OLD_POOL_NAME --num-nodes=3

# Restore from snapshot if needed
kubectl exec -it es-master-0 -- curl -X POST "localhost:9200/_snapshot/backup/pre-upgrade-YYYYMMDD/_restore"

# Rollback node pool version (if within 30 days)
gcloud container clusters upgrade YOUR_CLUSTER --node-version=1.31.x-gke.y
```

## Key Considerations

1. **PV Safety**: Regional pd-ssd volumes will automatically reattach to new nodes
2. **Timing**: Plan for 2-4 hours total upgrade time
3. **Monitoring**: Watch cluster health continuously during the process
4. **Quorum**: Never let master nodes drop below 2 healthy instances
5. **Shard Allocation**: Keep it disabled during node transitions to prevent unnecessary data movement

This approach ensures data safety while minimizing downtime. The regional persistent disks will survive node replacements, and the careful sequencing maintains Elasticsearch cluster stability throughout the upgrade.
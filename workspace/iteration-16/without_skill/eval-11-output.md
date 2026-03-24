I'll walk you through a safe GKE cluster upgrade strategy for your Elasticsearch setup. Given your multi-node-pool architecture, we'll use a rolling upgrade approach to maintain availability.

## Pre-Upgrade Preparation

### 1. Backup and Health Check
```bash
# Check cluster health
kubectl get nodes
kubectl get pods -n <elasticsearch-namespace>

# Verify Elasticsearch cluster health
curl -X GET "your-es-endpoint:9200/_cluster/health?pretty"
curl -X GET "your-es-endpoint:9200/_cat/indices?v"

# Create backup (recommended)
curl -X PUT "your-es-endpoint:9200/_snapshot/backup-repo/pre-upgrade-snapshot"
```

### 2. Disable Shard Allocation
```bash
# Temporarily disable shard reallocation to prevent unnecessary movement
curl -X PUT "your-es-endpoint:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'
```

## Rolling Upgrade Strategy

### Phase 1: Upgrade Coordinating Nodes First
Coordinating nodes are stateless and safest to start with:

```bash
# Get current node pool versions
gcloud container node-pools list --cluster=your-cluster-name --region=your-region

# Upgrade coordinating node pool
gcloud container node-pools upgrade coordinating-pool \
  --cluster=your-cluster-name \
  --region=your-region \
  --node-version=1.32.x-gke.xxxx

# Monitor the upgrade
kubectl get nodes -l node-pool=coordinating-pool
kubectl get pods -n elasticsearch -l role=coordinating
```

### Phase 2: Upgrade Data Nodes (Most Critical)
Data nodes require careful handling due to persistent volumes:

```bash
# Upgrade data node pool with surge settings for minimal disruption
gcloud container node-pools upgrade data-pool \
  --cluster=your-cluster-name \
  --region=your-region \
  --node-version=1.32.x-gke.xxxx \
  --max-surge-upgrade=1 \
  --max-unavailable-upgrade=0

# Monitor data node upgrade closely
watch "kubectl get nodes -l node-pool=data-pool && echo '---' && kubectl get pods -n elasticsearch -l role=data"
```

**Important**: GKE will:
- Create new nodes with the new version
- Drain old nodes (triggering pod rescheduling)
- PVs will automatically reattach to new nodes due to regional pd-ssd

### Phase 3: Upgrade Master Nodes (Final)
```bash
# Upgrade master node pool
gcloud container node-pools upgrade master-pool \
  --cluster=your-cluster-name \
  --region=your-region \
  --node-version=1.32.x-gke.xxxx \
  --max-surge-upgrade=1 \
  --max-unavailable-upgrade=0

# Monitor master nodes
kubectl get nodes -l node-pool=master-pool
kubectl get pods -n elasticsearch -l role=master
```

### Phase 4: Upgrade Control Plane
```bash
# Upgrade the GKE control plane (this is non-disruptive)
gcloud container clusters upgrade your-cluster-name \
  --master \
  --cluster-version=1.32.x-gke.xxxx \
  --region=your-region
```

## Monitoring During Upgrade

Monitor these throughout the process:

```bash
# Elasticsearch cluster health
watch "curl -s your-es-endpoint:9200/_cluster/health | jq '.status'"

# Pod status
watch "kubectl get pods -n elasticsearch"

# Node status
watch "kubectl get nodes"

# StatefulSet status
kubectl get statefulsets -n elasticsearch

# PVC status (ensure no issues with volume reattachment)
kubectl get pvc -n elasticsearch
```

## Post-Upgrade Tasks

### 1. Re-enable Shard Allocation
```bash
curl -X PUT "your-es-endpoint:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "all"
  }
}'
```

### 2. Verify Cluster Health
```bash
# Wait for green status
curl -X GET "your-es-endpoint:9200/_cluster/health?wait_for_status=green&timeout=300s"

# Check all nodes are visible
curl -X GET "your-es-endpoint:9200/_cat/nodes?v"

# Verify data integrity
curl -X GET "your-es-endpoint:9200/_cat/indices?v"
```

## Key Safety Considerations

1. **PV Safety**: Regional pd-ssd volumes will automatically reattach when pods reschedule to new nodes
2. **StatefulSet Behavior**: Pods maintain their identity and will reconnect to the same PVs
3. **Elasticsearch Resilience**: With 3 masters, you maintain quorum throughout
4. **Network Disruption**: Brief network interruptions during node transitions are normal

## Rollback Plan
If issues arise:
```bash
# You can rollback individual node pools
gcloud container node-pools rollback data-pool \
  --cluster=your-cluster-name \
  --region=your-region
```

## Expected Timeline
- Coordinating nodes: 10-15 minutes
- Data nodes: 30-45 minutes (most time-consuming)  
- Master nodes: 15-20 minutes
- Control plane: 10-15 minutes
- Total: ~1.5-2 hours

The upgrade should maintain availability throughout, with only brief moments of increased latency during node transitions.
I'll walk you through a safe GKE cluster upgrade for your Elasticsearch setup. Given your multi-node pool architecture, we'll use a rolling approach to maintain availability.

## Pre-Upgrade Preparation

### 1. Backup and Health Check
```bash
# Check cluster health
kubectl get nodes
kubectl get pods -n <elasticsearch-namespace>

# Verify Elasticsearch cluster health
curl -X GET "localhost:9200/_cluster/health?pretty"
# Should show "green" status

# Take snapshot (if configured)
curl -X PUT "localhost:9200/_snapshot/backup_repo/pre-upgrade-$(date +%Y%m%d)"
```

### 2. Disable Shard Allocation
```bash
# Temporarily disable shard reallocation to prevent unnecessary data movement
curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'
```

### 3. Configure PodDisruptionBudgets
```yaml
# Ensure you have PDBs for each node type
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-master-pdb
spec:
  minAvailable: 2  # Keep majority of masters
  selector:
    matchLabels:
      role: master
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-data-pdb
spec:
  minAvailable: 3  # Keep majority of data nodes
  selector:
    matchLabels:
      role: data
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-coordinating-pdb
spec:
  minAvailable: 1  # Keep at least one coordinator
  selector:
    matchLabels:
      role: coordinating
```

## Upgrade Process

### 1. Upgrade Control Plane
```bash
# Upgrade control plane first (minimal downtime)
gcloud container clusters upgrade <cluster-name> \
  --cluster-version=1.32 \
  --master \
  --zone=<zone> \
  --project=<project-id>
```

### 2. Upgrade Node Pools (One at a Time)

#### Start with Coordinating Nodes (Least Critical)
```bash
# Upgrade coordinating node pool
gcloud container node-pools upgrade <coordinating-pool-name> \
  --cluster=<cluster-name> \
  --zone=<zone> \
  --node-version=1.32 \
  --max-surge-upgrade=1 \
  --max-unavailable-upgrade=0

# Monitor the upgrade
kubectl get nodes -l node-pool=<coordinating-pool>
kubectl get pods -l role=coordinating -w
```

#### Upgrade Data Nodes (Most Critical - Go Slow)
```bash
# Before each data node upgrade, verify cluster health
curl -X GET "localhost:9200/_cluster/health?pretty"

# Upgrade data node pool with conservative settings
gcloud container node-pools upgrade <data-pool-name> \
  --cluster=<cluster-name> \
  --zone=<zone> \
  --node-version=1.32 \
  --max-surge-upgrade=1 \
  --max-unavailable-upgrade=1

# Wait for each node to be ready before continuing
kubectl get nodes -l node-pool=<data-pool> -w
```

#### Finally, Upgrade Master Nodes
```bash
# Masters are most critical - upgrade one at a time
gcloud container node-pools upgrade <master-pool-name> \
  --cluster=<cluster-name> \
  --zone=<zone> \
  --node-version=1.32 \
  --max-surge-upgrade=1 \
  --max-unavailable-upgrade=0

# Monitor master election during upgrade
kubectl logs -l role=master -f
```

### 3. Post-Upgrade Steps

#### Re-enable Shard Allocation
```bash
curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": null
  }
}'
```

#### Verify Cluster Health
```bash
# Check all nodes are ready
kubectl get nodes

# Verify Elasticsearch cluster health
curl -X GET "localhost:9200/_cluster/health?pretty"
curl -X GET "localhost:9200/_cat/nodes?v"
curl -X GET "localhost:9200/_cat/shards?v&h=index,shard,prirep,state,node"

# Check that all pods are running
kubectl get pods -n <elasticsearch-namespace>
```

## Monitoring During Upgrade

### Key Metrics to Watch
```bash
# Node status
watch kubectl get nodes

# Pod status
watch kubectl get pods -l app=elasticsearch

# Elasticsearch cluster status
watch 'curl -s localhost:9200/_cluster/health | jq .'

# PV status
kubectl get pv | grep elasticsearch
```

### Rollback Plan
If issues occur:
```bash
# You can rollback individual node pools
gcloud container node-pools rollback <pool-name> \
  --cluster=<cluster-name> \
  --zone=<zone>
```

## Best Practices Applied

1. **Order of Operations**: Coordinating → Data → Master nodes
2. **Conservative Surge Settings**: Especially for data nodes
3. **PV Safety**: Regional pd-ssd will persist through node replacement
4. **Shard Management**: Disabled reallocation during upgrade
5. **Health Monitoring**: Continuous verification at each step

## Expected Downtime

- **Control plane**: ~5-10 minutes
- **Application**: Near-zero if following this process
- **Individual nodes**: ~5-10 minutes per node during replacement

The StatefulSet will ensure pods reconnect to the same PVs, and Elasticsearch's clustering will handle the temporary node unavailability gracefully with your current replica configuration.
# GKE Upgrade Plan: Elasticsearch Cluster (1.31 → 1.32)

## Cluster Overview
- **Mode:** GKE Standard
- **Current:** 1.31 → **Target:** 1.32 
- **Workload:** Elasticsearch StatefulSet cluster (3 masters, 5 data, 2 coordinating nodes)
- **Storage:** Regional pd-ssd PVs
- **Node pools:** 3 separate pools (masters, data, coordinating)

## Pre-Upgrade Planning

### Elasticsearch-Specific Considerations
- **Cluster stability:** Elasticsearch requires quorum (2/3 master nodes) to remain operational
- **Data safety:** Regional pd-ssd provides zone redundancy, but we need shard allocation awareness
- **Rolling restart tolerance:** ES handles node restarts gracefully if properly configured

### Recommended Upgrade Strategy

**Control plane first, then node pools in this order:**
1. Coordinating nodes (least critical, no data)
2. Data nodes (most critical, needs careful shard management)  
3. Master nodes (requires maintaining quorum)

## Step 1: Pre-Flight Checks

```bash
# Verify current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Check Elasticsearch cluster health
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health?pretty"
# Should show: status: "green", number_of_nodes: 10

# Verify shard allocation
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/shards?v"

# Check PV status
kubectl get pv | grep elasticsearch
kubectl get pvc -n NAMESPACE | grep elasticsearch
```

### Critical Elasticsearch Settings

Ensure these are configured before upgrading:

```bash
# Disable shard allocation during upgrades (apply before each node pool upgrade)
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" \
  -H 'Content-Type: application/json' -d '
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'

# Configure proper termination grace period (should be 120s+)
kubectl get statefulset elasticsearch-master -o yaml | grep terminationGracePeriodSeconds
# Should be 120+ to allow graceful shutdown
```

## Step 2: Configure Node Pool Upgrade Settings

**For all Elasticsearch node pools, use conservative surge settings:**

```bash
# Master nodes (critical for quorum)
gcloud container node-pools update es-master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1

# Data nodes (critical for data)
gcloud container node-pools update es-data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1

# Coordinating nodes (least critical)
gcloud container node-pools update es-coordinating-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**Rationale:** `maxSurge=0, maxUnavailable=1` for masters/data ensures only one node upgrades at a time, maintaining quorum and data availability. Regional PVs will reattach to replacement nodes in the same region.

## Step 3: Configure PDBs

```yaml
# Apply this PDB for masters (maintains quorum)
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-master-pdb
spec:
  minAvailable: 2  # Maintains 2/3 quorum
  selector:
    matchLabels:
      app: elasticsearch
      role: master
---
# PDB for data nodes
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-data-pdb
spec:
  minAvailable: 4  # Keeps 4/5 data nodes available
  selector:
    matchLabels:
      app: elasticsearch
      role: data
---
# PDB for coordinating nodes  
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-coordinating-pdb
spec:
  minAvailable: 1  # Keeps 1/2 coordinating nodes available
  selector:
    matchLabels:
      app: elasticsearch
      role: coordinating
```

## Step 4: Upgrade Sequence

### 4.1 Control Plane Upgrade

```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32

# Wait and verify (~10-15 minutes)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"

# Verify ES cluster health after control plane upgrade
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health?pretty"
```

### 4.2 Coordinating Nodes (First - Least Critical)

```bash
# Disable shard allocation before node upgrade
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" \
  -H 'Content-Type: application/json' -d '
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'

# Upgrade coordinating node pool
gcloud container node-pools upgrade es-coordinating-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor progress
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=es-coordinating-pool'

# Re-enable shard allocation after upgrade completes
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" \
  -H 'Content-Type: application/json' -d '
{
  "persistent": {
    "cluster.routing.allocation.enable": null
  }
}'

# Verify cluster health
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health?pretty"
```

### 4.3 Data Nodes (Second - Most Data-Critical)

```bash
# Disable shard allocation
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" \
  -H 'Content-Type: application/json' -d '
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'

# Upgrade data node pool (will take longest due to PV reattachment)
gcloud container node-pools upgrade es-data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor both node status and ES cluster health
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=es-data-pool; echo "---"; kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health"'

# Re-enable shard allocation after upgrade completes
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" \
  -H 'Content-Type: application/json' -d '
{
  "persistent": {
    "cluster.routing.allocation.enable": null
  }
}'

# Wait for cluster to return to green status
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health?wait_for_status=green&timeout=10m"
```

### 4.4 Master Nodes (Last - Quorum Critical)

```bash
# Disable shard allocation
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" \
  -H 'Content-Type: application/json' -d '
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'

# Upgrade master node pool (maintains 2/3 quorum throughout)
gcloud container node-pools upgrade es-master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor master quorum carefully
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=es-master-pool; echo "---"; kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/master"'

# Re-enable shard allocation after upgrade completes
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" \
  -H 'Content-Type: application/json' -d '
{
  "persistent": {
    "cluster.routing.allocation.enable": null
  }
}'

# Final cluster health check
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health?wait_for_status=green&timeout=10m"
```

## Step 5: Post-Upgrade Validation

```bash
# Verify all nodes upgraded
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE

# Comprehensive Elasticsearch health check
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/health?pretty"
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/nodes?v"
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/indices?v&health=red"

# Verify all PVs reattached correctly
kubectl get pods -l app=elasticsearch -o wide
kubectl get pvc | grep elasticsearch

# Check for any unassigned shards
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/shards?h=index,shard,prirep,state,unassigned.reason" | grep UNASSIGNED
```

## Troubleshooting Scenarios

### If ES cluster goes yellow/red during upgrade:

```bash
# Check unassigned shards
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cluster/allocation/explain?pretty"

# Force allocation if needed (last resort)
kubectl exec -it es-master-0 -- curl -X POST "localhost:9200/_cluster/reroute?retry_failed=true"
```

### If PV attachment fails:

```bash
# Check PV/PVC status
kubectl describe pv PV_NAME
kubectl get events --field-selector involvedObject.name=POD_NAME

# Regional pd-ssd should reattach automatically within the same region
# If stuck, delete the pod to trigger rescheduling
kubectl delete pod es-data-X
```

### If master quorum is lost:

```bash
# Check master nodes
kubectl exec -it es-master-0 -- curl -s "localhost:9200/_cat/master"
kubectl get pods -l role=master

# If <2 masters available, wait for node replacement before continuing
```

## Timeline Expectations

- **Control plane:** 10-15 minutes
- **Coordinating nodes:** 15-20 minutes (faster, no PVs)
- **Data nodes:** 45-60 minutes (PV reattachment + shard rebalancing)  
- **Master nodes:** 20-30 minutes (careful quorum management)

**Total estimated time:** 90-125 minutes

## Key Success Factors

1. **Conservative surge settings** prevent multiple nodes upgrading simultaneously
2. **PDB protection** ensures minimum availability during drain
3. **Shard allocation control** prevents unnecessary data movement
4. **Regional PVs** enable cross-zone failover during node replacement
5. **Proper upgrade order** (coordinating → data → master) minimizes risk

Your Elasticsearch cluster should maintain availability throughout this upgrade process. The regional pd-ssd volumes will reattach automatically to replacement nodes within the same region.
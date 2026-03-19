# GKE Upgrade Plan: Elasticsearch Cluster (1.29 → 1.30)

## Executive Summary

Upgrading a StatefulSet-based Elasticsearch cluster requires careful orchestration to maintain quorum and data integrity. The key strategy is **sequential node pool upgrades with surge=1, unavailable=0** to minimize disruption while respecting Elasticsearch's clustering requirements.

## Current State Assessment

- **Cluster**: GKE Standard, v1.29 → v1.30 (single minor version jump ✓)
- **Workloads**: 3 master + 5 data + 2 coordinating nodes = 10 total ES nodes
- **Storage**: Regional PD-SSD (good - can attach to nodes in any zone)
- **Architecture**: Separate node pools per ES role (excellent for controlled upgrades)

## Upgrade Strategy

**Order of operations:**
1. Control plane first (required)
2. Coordinating node pool (lowest impact)
3. Data node pool (most critical - only 1 node at a time)
4. Master node pool (maintains quorum throughout)

**Node pool settings for all pools:**
- `maxSurge=1, maxUnavailable=0` (creates new node before draining old)
- This ensures ES cluster never loses capacity during the upgrade

## Pre-Upgrade Checklist

```
Elasticsearch Cluster Upgrade Checklist
- [ ] Cluster: _YOUR_CLUSTER_NAME_ | Current: 1.29 | Target: 1.30
- [ ] Node pools: master (3), data (5), coordinating (2)

Elasticsearch Health
- [ ] Cluster status GREEN: `curl -X GET "localhost:9200/_cluster/health"`
- [ ] All shards allocated: `curl -X GET "localhost:9200/_cat/shards?v&h=index,shard,prirep,state,unassigned.reason"`
- [ ] No ongoing shard movements: `curl -X GET "localhost:9200/_cat/recovery?active_only"`
- [ ] Recent snapshot completed: `curl -X GET "localhost:9200/_snapshot/_all/_all?pretty"`
- [ ] Replication factor ≥ 1 for all indices
- [ ] Master quorum healthy (3/3 nodes)

Infrastructure
- [ ] PVs are regional pd-ssd (confirmed - can attach to any zone ✓)
- [ ] Sufficient compute quota for surge nodes (need +3 nodes temporarily)
- [ ] PDBs configured but not overly restrictive (allow 1 disruption per role)
- [ ] Maintenance window scheduled (off-peak hours)
- [ ] Monitoring active (ES cluster health + K8s metrics)

Compatibility
- [ ] Elasticsearch version compatible with K8s 1.30
- [ ] No deprecated APIs in ES operator/manifests
- [ ] Admission webhooks tested (if any)
```

## Step-by-Step Upgrade Runbook

### Phase 1: Pre-flight Setup

```bash
# Set variables
export CLUSTER_NAME="your-cluster-name"
export ZONE="your-zone"
export TARGET_VERSION="1.30.6-gke.1125000"  # Latest 1.30 patch

# Verify current state
gcloud container clusters describe $CLUSTER_NAME \
  --zone $ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Check ES cluster health
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"

# Configure surge settings for all node pools
for pool in master-pool data-pool coordinating-pool; do
  gcloud container node-pools update $pool \
    --cluster $CLUSTER_NAME \
    --zone $ZONE \
    --max-surge-upgrade 1 \
    --max-unavailable-upgrade 0
done
```

### Phase 2: Control Plane Upgrade

```bash
# Upgrade control plane (10-15 minutes)
gcloud container clusters upgrade $CLUSTER_NAME \
  --zone $ZONE \
  --master \
  --cluster-version $TARGET_VERSION

# Verify control plane
gcloud container clusters describe $CLUSTER_NAME \
  --zone $ZONE \
  --format="value(currentMasterVersion)"

# Check system pods
kubectl get pods -n kube-system | grep -v Running
```

### Phase 3: Coordinating Nodes (Lowest Risk)

```bash
# Upgrade coordinating node pool first
gcloud container node-pools upgrade coordinating-pool \
  --cluster $CLUSTER_NAME \
  --zone $ZONE \
  --cluster-version $TARGET_VERSION

# Monitor progress (2 nodes, ~20-30 minutes total)
watch 'kubectl get nodes -l node-role=coordinating -o wide'

# Validate ES cluster health after each node
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cluster/health"
```

### Phase 4: Data Nodes (Most Critical)

```bash
# Before starting: disable shard allocation to prevent rebalancing
kubectl exec -it elasticsearch-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" \
  -H 'Content-Type: application/json' \
  -d '{"persistent":{"cluster.routing.allocation.enable":"primaries"}}'

# Upgrade data node pool (5 nodes, ~60-75 minutes total)
gcloud container node-pools upgrade data-pool \
  --cluster $CLUSTER_NAME \
  --zone $ZONE \
  --cluster-version $TARGET_VERSION

# Monitor each node upgrade
watch 'kubectl get nodes -l node-role=data -o wide'

# After each data node comes online, verify shards
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cat/shards?v&h=index,shard,prirep,state,node"

# Re-enable shard allocation after all data nodes upgraded
kubectl exec -it elasticsearch-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" \
  -H 'Content-Type: application/json' \
  -d '{"persistent":{"cluster.routing.allocation.enable":null}}'

# Wait for cluster to rebalance
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cluster/health?wait_for_status=green&timeout=300s"
```

### Phase 5: Master Nodes (Maintain Quorum)

```bash
# Upgrade master node pool (3 nodes, ~30-45 minutes total)
gcloud container node-pools upgrade master-pool \
  --cluster $CLUSTER_NAME \
  --zone $ZONE \
  --cluster-version $TARGET_VERSION

# Monitor carefully - never lose quorum
watch 'kubectl get nodes -l node-role=master -o wide'

# Verify master elections stable
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cat/master?v"
```

## Elasticsearch-Specific Safety Measures

### PodDisruptionBudgets
Ensure you have PDBs that allow exactly 1 disruption per role:

```yaml
# Master PDB - maintain quorum (2/3)
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-master-pdb
spec:
  maxUnavailable: 1
  selector:
    matchLabels:
      app: elasticsearch-master

# Data PDB - protect data integrity
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-data-pdb
spec:
  maxUnavailable: 1
  selector:
    matchLabels:
      app: elasticsearch-data

# Coordinating PDB
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-coordinating-pdb
spec:
  maxUnavailable: 1
  selector:
    matchLabels:
      app: elasticsearch-coordinating
```

### Shard Allocation Strategy

The key insight is **disabling shard rebalancing during data node upgrades**:

1. **Before data pool upgrade**: Set `cluster.routing.allocation.enable: "primaries"`
   - Prevents ES from moving shards around as nodes drain
   - Reduces network traffic and speeds up the upgrade
   - Primary shards stay put, only replicas are affected

2. **After data pool upgrade**: Re-enable with `null` (default)
   - Allows ES to rebalance optimally across new nodes
   - Wait for GREEN status before proceeding

## Post-Upgrade Validation

```bash
# Cluster versions
gcloud container node-pools list --cluster $CLUSTER_NAME --zone $ZONE

# All nodes ready
kubectl get nodes

# Elasticsearch cluster health
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"

# Shard allocation complete
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cat/recovery?active_only"

# Indices healthy
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cat/indices?v&health=yellow,red"

# Test search functionality
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_search?pretty" \
  -H 'Content-Type: application/json' \
  -d '{"query":{"match_all":{}},"size":1}'
```

## Risk Mitigation

### Data Protection
- **Regional PD-SSD**: Your volumes can attach to any zone, eliminating zone-lock issues
- **StatefulSet**: Pods maintain identity and PVC bindings through upgrade
- **Replication**: With RF≥1, losing one data node temporarily is safe
- **Recent snapshots**: Last resort data recovery option

### Availability Protection
- **Surge upgrades**: New node created before old node drained
- **Sequential pools**: Never upgrade multiple node types simultaneously
- **Quorum maintenance**: Masters upgraded one at a time (2/3 always available)
- **Shard allocation control**: Prevents unnecessary data movement

### Rollback Plan
If critical issues arise:
1. **Stop the upgrade**: Cancel any in-progress node pool operation
2. **Create replacement pool**: At the previous version
3. **Migrate workloads**: Cordon upgraded nodes, drain to old pool
4. **ES cluster recovery**: May need to restore from snapshot if data corruption

## Timeline Estimate

- **Control plane**: 15 minutes
- **Coordinating nodes**: 30 minutes (2 nodes)
- **Data nodes**: 75 minutes (5 nodes, includes rebalancing wait)
- **Master nodes**: 45 minutes (3 nodes)
- **Validation**: 15 minutes

**Total**: ~3 hours with careful validation between phases.

This approach prioritizes data safety and availability over speed. Your Elasticsearch cluster should maintain full functionality throughout the upgrade process.
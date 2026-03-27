# Elasticsearch GKE Upgrade Plan: 1.31 → 1.32

## Cluster Overview
- **Workload**: Elasticsearch StatefulSet (3 masters, 5 data, 2 coordinators)
- **Current**: GKE 1.31 → **Target**: 1.32
- **Storage**: Regional pd-ssd PVs (good - survives node changes)
- **Topology**: 3 separate node pools for different ES roles

## Pre-Upgrade Checklist

```markdown
Pre-Upgrade Checklist - Elasticsearch
- [ ] Cluster: ___ | Current: 1.31 | Target: 1.32
- [ ] Elasticsearch version compatibility with K8s 1.32 verified
- [ ] Release channel: ___ (check available versions)

Elasticsearch-Specific Readiness
- [ ] Cluster health GREEN: `curl -X GET "elasticsearch-service:9200/_cluster/health"`
- [ ] All shards allocated: `curl -X GET "elasticsearch-service:9200/_cat/shards?v"`
- [ ] No ongoing shard relocations: `curl -X GET "elasticsearch-service:9200/_cluster/health?wait_for_relocating_shards=0"`
- [ ] Snapshot backup completed: `curl -X PUT "elasticsearch-service:9200/_snapshot/backup/pre-upgrade-$(date +%Y%m%d)"`
- [ ] PV reclaim policies set to Retain: `kubectl get pv -o custom-columns=NAME:.metadata.name,RECLAIM:.spec.persistentVolumeReclaimPolicy`

PDB Configuration (Critical)
- [ ] Master PDB: `minAvailable: 2` (allows 1 master drain, keeps quorum)
- [ ] Data PDB: `minAvailable: 3` (allows 2 data nodes to drain simultaneously)
- [ ] Coordinator PDB: `minAvailable: 1` (allows 1 coordinator drain)

Node Pool Strategy
- [ ] All pools: `maxSurge=1, maxUnavailable=0` (conservative, one-at-a-time)
- [ ] Upgrade order: Coordinators → Data → Masters (least critical first)
- [ ] Regional pd-ssd confirmed (survives node migration)
```

## Detailed Upgrade Runbook

### Phase 1: Pre-flight Checks

```bash
# Check Elasticsearch cluster health
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"
# Must show status: "green", relocating_shards: 0

# Verify PV reclaim policies (safety check)
kubectl get pv -o custom-columns=NAME:.metadata.name,RECLAIM:.spec.persistentVolumeReclaimPolicy | grep -v Retain
# Should return empty - all PVs must be "Retain"

# Current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Check 1.32 availability in your channel
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels)"
```

### Phase 2: Configure PDBs (Essential for Elasticsearch)

```yaml
# Apply these PDBs before upgrading
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-master-pdb
spec:
  minAvailable: 2  # Maintains quorum during drain
  selector:
    matchLabels:
      app: elasticsearch
      role: master
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-data-pdb
spec:
  minAvailable: 3  # Allows 2 data nodes to drain
  selector:
    matchLabels:
      app: elasticsearch
      role: data
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-coordinator-pdb
spec:
  minAvailable: 1  # Allows 1 coordinator to drain
  selector:
    matchLabels:
      app: elasticsearch
      role: coordinator
```

```bash
kubectl apply -f elasticsearch-pdbs.yaml
kubectl get pdb -A
```

### Phase 3: Take Application Backup

```bash
# Create snapshot repository (if not exists)
kubectl exec -it elasticsearch-master-0 -- curl -X PUT "localhost:9200/_snapshot/backup" -H 'Content-Type: application/json' -d'
{
  "type": "gcs",
  "settings": {
    "bucket": "your-backup-bucket",
    "base_path": "elasticsearch-snapshots"
  }
}'

# Take pre-upgrade snapshot
kubectl exec -it elasticsearch-master-0 -- curl -X PUT "localhost:9200/_snapshot/backup/pre-upgrade-$(date +%Y%m%d-%H%M)" -H 'Content-Type: application/json' -d'
{
  "indices": "*",
  "ignore_unavailable": true,
  "include_global_state": true
}'

# Verify snapshot status
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_snapshot/backup/_status"
```

### Phase 4: Control Plane Upgrade

```bash
# Upgrade control plane first (required before nodes)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.LATEST

# Wait ~10-15 minutes, then verify
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"

kubectl get pods -n kube-system
```

### Phase 5: Node Pool Upgrades (Coordinating → Data → Masters)

**Step 1: Configure surge settings for all pools**
```bash
# Coordinator pool (lowest risk, upgrade first)
gcloud container node-pools update es-coordinator-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Data pool
gcloud container node-pools update es-data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Master pool (highest risk, upgrade last)
gcloud container node-pools update es-master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**Step 2: Upgrade coordinator pool first**
```bash
gcloud container node-pools upgrade es-coordinator-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.LATEST

# Monitor progress
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=es-coordinator-pool -o wide'

# Verify coordinator pods healthy
kubectl get pods -l role=coordinator -o wide
kubectl exec -it elasticsearch-coordinator-0 -- curl -X GET "localhost:9200/_cluster/health"
```

**Step 3: Upgrade data pool**
```bash
# Wait for coordinators to be stable, then proceed
gcloud container node-pools upgrade es-data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.LATEST

# Monitor data node migration carefully
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=es-data-pool -o wide'
watch 'kubectl get pods -l role=data -o wide'

# Critical: Monitor shard allocation during data node migration
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cat/shards?v&h=index,shard,prirep,state,node&s=index"

# Ensure no UNASSIGNED shards
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cluster/health?wait_for_status=green&timeout=10m"
```

**Step 4: Upgrade master pool (most critical)**
```bash
# Final verification before masters
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cluster/health"
# Must be GREEN with all data nodes healthy

gcloud container node-pools upgrade es-master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.LATEST

# Monitor master election during upgrade
watch 'kubectl get pods -l role=master -o wide'

# Check cluster remains GREEN throughout
watch 'kubectl exec -it elasticsearch-master-0 -- curl -s -X GET "localhost:9200/_cluster/health" | jq .status'
```

### Phase 6: Post-Upgrade Validation

```bash
# Verify all versions upgraded
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE

# Elasticsearch cluster health
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"
# Status must be "green", all nodes present

# Verify all shards allocated
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cat/shards?v" | grep UNASSIGNED
# Should return empty

# Check node discovery
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cat/nodes?v"
# All 10 nodes (3 master + 5 data + 2 coordinator) should be present

# Application smoke test
kubectl exec -it elasticsearch-master-0 -- curl -X GET "localhost:9200/_cluster/stats?pretty"

# Verify StatefulSet ready state
kubectl get statefulsets -A
```

## Rollback Plan (If Needed)

If the upgrade fails and you need to rollback:

```bash
# You cannot downgrade already-upgraded nodes in-place
# Must create new pools at old version and migrate

# Create rollback data pool
gcloud container node-pools create es-data-pool-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.VERSION \
  --num-nodes 5 \
  --machine-type n1-standard-4

# Wait for nodes ready, then drain Elasticsearch data gracefully
# Use Elasticsearch exclude allocation to move shards off old nodes:
kubectl exec -it elasticsearch-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.exclude._name": "old-node-names"
  }
}'

# Monitor shard evacuation, then delete old pool
```

## Key Elasticsearch Considerations

1. **PDB is Critical**: The `minAvailable: 2` for masters maintains quorum during drain. Never set to 1 or the cluster will lose quorum when a master drains.

2. **Upgrade Order Matters**: Coordinators → Data → Masters minimizes risk. Masters are upgraded last because they coordinate the cluster.

3. **Shard Allocation Monitoring**: Regional pd-ssd PVs will reattach to new nodes, but monitor `_cat/shards` during data node upgrades to ensure no data loss.

4. **One-at-a-time**: `maxSurge=1, maxUnavailable=0` ensures only one node per pool upgrades at once, maintaining maximum stability.

5. **StatefulSet Behavior**: Elasticsearch StatefulSets will restart pods on new nodes. The PVs (regional pd-ssd) will automatically attach to the new nodes.

This plan prioritizes data safety and availability over speed. The entire upgrade will take 2-4 hours but ensures zero data loss and minimal service interruption.
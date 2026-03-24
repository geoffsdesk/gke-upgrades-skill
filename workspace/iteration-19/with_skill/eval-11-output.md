# Elasticsearch Cluster Upgrade Plan: 1.31 → 1.32

## Cluster Overview
- **Workload:** StatefulSet-based Elasticsearch (3 masters, 5 data, 2 coordinators)
- **Current:** GKE 1.31 → **Target:** 1.32  
- **Storage:** Regional pd-ssd PVs (survives node replacement)
- **Architecture:** 3 separate node pools (masters, data, coordinators)

## Pre-Upgrade Checklist

```markdown
Pre-Upgrade Checklist - Elasticsearch
- [ ] Cluster health: `curl -X GET "elasticsearch-service:9200/_cluster/health?pretty"`
- [ ] All shards allocated and green
- [ ] Disable shard allocation: `PUT _cluster/settings {"transient":{"cluster.routing.allocation.enable":"none"}}`
- [ ] Application-level backup: `PUT _snapshot/backup_repo/pre_upgrade_snapshot {"wait_for_completion":true}`
- [ ] PV reclaim policies set to Retain: `kubectl get pv | grep elasticsearch`
- [ ] Elasticsearch version compatibility verified with K8s 1.32
- [ ] PDBs configured correctly (see below)
```

## PodDisruptionBudgets Configuration

**Critical:** Configure these PDBs BEFORE starting the upgrade:

```yaml
# Master PDB - Protects quorum (2/3 masters must remain)
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-master-pdb
  namespace: elasticsearch
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: elasticsearch
      role: master
---
# Data PDB - Prevents multiple data nodes draining simultaneously
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-data-pdb
  namespace: elasticsearch
spec:
  minAvailable: 4
  selector:
    matchLabels:
      app: elasticsearch
      role: data
---
# Coordinator PDB - Keep at least 1 for client access
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-coordinator-pdb
  namespace: elasticsearch
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: elasticsearch
      role: coordinator
```

## Node Pool Upgrade Strategy

**Recommended:** Surge upgrade with conservative settings for all pools:
- `maxSurge=1, maxUnavailable=0` - One-at-a-time replacement, no capacity loss
- **Upgrade order:** Coordinators → Data → Masters (least critical first)

## Upgrade Runbook

### Phase 1: Pre-flight Checks

```bash
# Verify cluster versions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(currentMasterVersion, nodePools[].name, nodePools[].version)"

# Check 1.32 availability
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels)" | grep -A5 -B5 "1.32"

# Elasticsearch health
kubectl exec -it elasticsearch-master-0 -n elasticsearch -- \
  curl -X GET "localhost:9200/_cluster/health?pretty"

# Verify PVs are Retain policy
kubectl get pv -o custom-columns=NAME:.metadata.name,RECLAIM:.spec.persistentVolumeReclaimPolicy | grep elasticsearch
```

### Phase 2: Prepare Elasticsearch

```bash
# Disable shard allocation (prevents rebalancing during upgrade)
kubectl exec -it elasticsearch-master-0 -n elasticsearch -- \
  curl -X PUT "localhost:9200/_cluster/settings" \
  -H 'Content-Type: application/json' \
  -d '{"transient":{"cluster.routing.allocation.enable":"none"}}'

# Take application backup
kubectl exec -it elasticsearch-master-0 -n elasticsearch -- \
  curl -X PUT "localhost:9200/_snapshot/backup_repo/pre_upgrade_1_32" \
  -H 'Content-Type: application/json' \
  -d '{"wait_for_completion":true}'

# Apply PDBs
kubectl apply -f elasticsearch-pdbs.yaml
```

### Phase 3: Control Plane Upgrade

```bash
# Upgrade control plane to 1.32
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.X-gke.XXXX

# Verify (wait 10-15 min)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

### Phase 4: Node Pool Upgrades (Sequential)

**4a. Coordinator Nodes First** (least critical, client-facing)

```bash
# Configure conservative surge
gcloud container node-pools update elasticsearch-coordinators \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade coordinator pool
gcloud container node-pools upgrade elasticsearch-coordinators \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.X-gke.XXXX

# Monitor progress
watch 'kubectl get nodes -l nodepool=coordinators -o wide'
watch 'kubectl get pods -l role=coordinator -n elasticsearch'

# Verify Elasticsearch accessibility
kubectl exec -it elasticsearch-master-0 -n elasticsearch -- \
  curl -X GET "localhost:9200/_cluster/health?pretty"
```

**4b. Data Nodes Second** (contains shard data, protected by PDB)

```bash
# Configure conservative surge for data pool
gcloud container node-pools update elasticsearch-data \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade data pool
gcloud container node-pools upgrade elasticsearch-data \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.X-gke.XXXX

# Monitor - This will take longest due to StatefulSet startup time
watch 'kubectl get nodes -l nodepool=data -o wide'
watch 'kubectl get pods -l role=data -n elasticsearch'
watch 'kubectl get pv | grep elasticsearch-data'

# Verify cluster stability after each data pod restart
kubectl exec -it elasticsearch-master-0 -n elasticsearch -- \
  curl -X GET "localhost:9200/_cluster/health?pretty"
```

**4c. Master Nodes Last** (most critical, quorum-protected)

```bash
# Configure conservative surge for masters
gcloud container node-pools update elasticsearch-masters \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade master pool
gcloud container node-pools upgrade elasticsearch-masters \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.X-gke.XXXX

# Monitor master elections and quorum
watch 'kubectl get nodes -l nodepool=masters -o wide'
watch 'kubectl get pods -l role=master -n elasticsearch'

# Check master election status
kubectl exec -it elasticsearch-master-0 -n elasticsearch -- \
  curl -X GET "localhost:9200/_cat/master?v"
```

### Phase 5: Post-Upgrade Validation

```bash
# Re-enable shard allocation
kubectl exec -it elasticsearch-master-0 -n elasticsearch -- \
  curl -X PUT "localhost:9200/_cluster/settings" \
  -H 'Content-Type: application/json' \
  -d '{"transient":{"cluster.routing.allocation.enable":"all"}}'

# Wait for cluster to stabilize and rebalance
kubectl exec -it elasticsearch-master-0 -n elasticsearch -- \
  curl -X GET "localhost:9200/_cluster/health?wait_for_status=green&timeout=10m"

# Verify all shards allocated
kubectl exec -it elasticsearch-master-0 -n elasticsearch -- \
  curl -X GET "localhost:9200/_cat/shards?v" | grep -i unassigned

# Check node versions
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion

# Post-upgrade backup
kubectl exec -it elasticsearch-master-0 -n elasticsearch -- \
  curl -X PUT "localhost:9200/_snapshot/backup_repo/post_upgrade_1_32" \
  -H 'Content-Type: application/json' \
  -d '{"wait_for_completion":true}'
```

## Key Safety Measures for Elasticsearch

### Why This Order Works
1. **Coordinators first:** Only handle client requests, no data risk
2. **Data nodes second:** PDB ensures 4/5 remain available, shards stay accessible  
3. **Masters last:** PDB ensures 2/3 quorum maintained throughout

### StatefulSet Restart Behavior
- **One pod at a time:** StatefulSet controller waits for each pod to be Ready before starting the next
- **Persistent storage:** Regional pd-ssd PVs survive node replacement and reattach automatically
- **Identity preservation:** Pod names (elasticsearch-master-0, etc.) remain consistent

### Monitoring During Upgrade
```bash
# Real-time cluster status
watch 'kubectl exec -it elasticsearch-master-0 -n elasticsearch -- curl -s "localhost:9200/_cluster/health?pretty" | grep -E "status|number_of_nodes"'

# Check for any unassigned shards (should be 0)
watch 'kubectl exec -it elasticsearch-master-0 -n elasticsearch -- curl -s "localhost:9200/_cat/shards" | grep -i unassigned | wc -l'
```

## Rollback Plan (If Needed)

If issues arise after a node pool upgrade:

```bash
# Create new node pool at 1.31
gcloud container node-pools create elasticsearch-data-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.X-gke.XXXX \
  --num-nodes 5 \
  --machine-type ORIGINAL_MACHINE_TYPE

# Cordon upgraded pool
kubectl cordon -l nodepool=elasticsearch-data

# StatefulSets will automatically reschedule to new nodes
# PVs will reattach to new pods with same names
```

## Expected Timeline
- **Control plane:** 10-15 minutes
- **Coordinators:** 15-20 minutes (2 pods)
- **Data nodes:** 45-60 minutes (5 pods, StatefulSet sequential startup)
- **Masters:** 20-30 minutes (3 pods, careful quorum management)
- **Total:** ~2 hours including validation

This approach ensures your Elasticsearch cluster maintains both data integrity and search availability throughout the upgrade process.
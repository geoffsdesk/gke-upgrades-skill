# GKE Upgrade Plan: Elasticsearch on Standard (1.29 → 1.30)

**Cluster:** Standard | **Upgrade:** 1.29 → 1.30 | **Workload:** StatefulSet Elasticsearch

## Pre-Upgrade Assessment

### Version compatibility
- Kubernetes 1.30 is available in all release channels
- No deprecated APIs removed in 1.30 that affect StatefulSets or PVs
- Elasticsearch operator/helm chart compatibility with K8s 1.30 should be verified

### Elasticsearch-specific considerations
Your topology (3 masters, 5 data, 2 coordinating) provides good resilience:
- **Masters:** Can lose 1 node (quorum = 2/3) 
- **Data:** Can lose multiple nodes if replicas ≥ 1
- **Coordinating:** Stateless, can lose both temporarily

## Upgrade Strategy

**Conservative approach for data safety:**
- **Control plane:** Standard upgrade
- **Node pools:** Surge with `maxSurge=1, maxUnavailable=0` per pool
- **Sequence:** Masters → Data → Coordinating (most to least critical)

## Pre-Upgrade Checklist

```markdown
Pre-Upgrade Checklist - Elasticsearch Cluster
- [ ] Cluster health: `kubectl exec -n elasticsearch es-master-0 -- curl -s 'localhost:9200/_cluster/health'`
- [ ] All indices green, no relocating shards
- [ ] Elasticsearch snapshot completed to GCS/external storage
- [ ] PV backup completed (if using volume snapshots)
- [ ] Shard allocation enabled: `"cluster.routing.allocation.enable": "all"`
- [ ] No cluster-level operations running (reindex, allocation, etc.)
- [ ] PDBs configured for each StatefulSet:
  - [ ] Masters: minAvailable=2 (maintains quorum)
  - [ ] Data: minAvailable=4 (keeps majority available)
  - [ ] Coordinating: minAvailable=1 (keeps service available)
- [ ] Regional pd-ssd PVs verified as reclaimPolicy=Retain
- [ ] Elasticsearch operator/helm chart tested against K8s 1.30
- [ ] Monitoring active (cluster health, shard status, query latency)
```

## Step-by-Step Runbook

### 1. Pre-flight checks

```bash
# Cluster versions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].version)"

# Elasticsearch cluster health
kubectl exec -n elasticsearch es-master-0 -- \
  curl -s 'localhost:9200/_cluster/health?pretty'

# Verify all shards allocated
kubectl exec -n elasticsearch es-master-0 -- \
  curl -s 'localhost:9200/_cat/shards' | grep -v STARTED | wc -l
# Should return 0

# Check PDBs
kubectl get pdb -n elasticsearch -o wide
```

### 2. Elasticsearch pre-upgrade prep

```bash
# Disable shard allocation (prevents unnecessary shard movement during upgrade)
kubectl exec -n elasticsearch es-master-0 -- \
  curl -X PUT 'localhost:9200/_cluster/settings' \
  -H 'Content-Type: application/json' \
  -d '{"persistent": {"cluster.routing.allocation.enable": "primaries"}}'

# Force sync flush (ensures data durability)
kubectl exec -n elasticsearch es-master-0 -- \
  curl -X POST 'localhost:9200/_flush/synced'
```

### 3. Control plane upgrade

```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.30

# Verify (wait ~10-15 min)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

### 4. Configure surge settings for all node pools

```bash
# Master pool (conservative - masters are critical)
gcloud container node-pools update es-master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Data pool (conservative - data safety first)  
gcloud container node-pools update es-data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Coordinating pool (can be faster - stateless)
gcloud container node-pools update es-coord-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

### 5. Upgrade node pools sequentially

**Step 5a: Master nodes first**

```bash
gcloud container node-pools upgrade es-master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30

# Monitor progress - ensure quorum maintained
watch 'kubectl get pods -n elasticsearch -l component=master -o wide'

# Verify cluster health after each master
kubectl exec -n elasticsearch es-master-0 -- \
  curl -s 'localhost:9200/_cluster/health' | jq '.status, .active_primary_shards'
```

**Step 5b: Data nodes (wait for masters to complete)**

```bash
gcloud container node-pools upgrade es-data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30

# Monitor shard allocation during upgrade
watch 'kubectl exec -n elasticsearch es-master-0 -- curl -s "localhost:9200/_cat/shards" | grep -E "RELOCATING|INITIALIZING" | wc -l'
```

**Step 5c: Coordinating nodes**

```bash
gcloud container node-pools upgrade es-coord-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30

# Monitor coordinating pods
watch 'kubectl get pods -n elasticsearch -l component=coordinating'
```

### 6. Post-upgrade Elasticsearch configuration

```bash
# Re-enable full shard allocation
kubectl exec -n elasticsearch es-master-0 -- \
  curl -X PUT 'localhost:9200/_cluster/settings' \
  -H 'Content-Type: application/json' \
  -d '{"persistent": {"cluster.routing.allocation.enable": "all"}}'

# Wait for cluster to stabilize
kubectl exec -n elasticsearch es-master-0 -- \
  curl -s 'localhost:9200/_cluster/health?wait_for_status=green&timeout=300s'
```

## Post-Upgrade Validation

```markdown
Post-Upgrade Checklist - Elasticsearch
- [ ] All node pools at version 1.30: `gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE`
- [ ] All nodes Ready: `kubectl get nodes`
- [ ] All Elasticsearch pods Running: `kubectl get pods -n elasticsearch`
- [ ] Cluster health green: `curl localhost:9200/_cluster/health`
- [ ] All shards allocated (0 unassigned): `curl localhost:9200/_cat/shards | grep -v STARTED | wc -l`
- [ ] Data integrity check: verify index counts match pre-upgrade
- [ ] Query performance within baseline (check p95 latency)
- [ ] Shard allocation re-enabled: `curl localhost:9200/_cluster/settings`
- [ ] Regional PVs still attached correctly
- [ ] Application logs clean (no connection errors)
```

## Rollback Strategy

If issues arise during data node upgrades:

```bash
# 1. Stop ongoing upgrade (GKE finishes current node)
# 2. Create new data pool at 1.29
gcloud container node-pools create es-data-pool-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.29 \
  --num-nodes 5 \
  --machine-type n2-highmem-4

# 3. Cordon problematic nodes
kubectl cordon NODE_NAME

# 4. Let Elasticsearch naturally rebalance to healthy nodes
# Regional PVs will reattach to new nodes in same zone
```

## Risk Mitigation

1. **Data loss prevention:** Regional pd-ssd PVs survive node replacement
2. **Availability:** PDBs prevent too many pods terminating simultaneously  
3. **Elasticsearch-aware:** Disabled allocation prevents unnecessary shard movement
4. **Monitoring:** Check cluster health between each pool upgrade
5. **Gradual rollout:** One pool at a time, with `maxSurge=1` for data pools

**Estimated timeline:** 2-3 hours total (1 hour masters, 1.5 hours data nodes, 30 min coordinating)

This plan prioritizes data safety over speed. The regional PVs and conservative surge settings ensure your Elasticsearch cluster maintains both availability and data integrity throughout the upgrade.
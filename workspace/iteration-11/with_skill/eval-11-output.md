# Elasticsearch GKE Upgrade Plan: 1.31 → 1.32

## Overview
**Cluster:** Standard GKE  
**Current:** 1.31 → **Target:** 1.32  
**Workload:** Elasticsearch StatefulSets (3 masters, 5 data, 2 coordinating nodes)  
**Storage:** Regional pd-ssd PVs  

This is a single minor version upgrade with stateful workloads requiring careful sequencing to maintain cluster quorum and data integrity.

---

## Pre-Upgrade Checklist

```
Elasticsearch-Specific Readiness
- [ ] Elasticsearch cluster health: `curl -X GET "elasticsearch-service:9200/_cluster/health"`
- [ ] All shards active (green status), no relocating/initializing shards
- [ ] Disable shard allocation: `curl -X PUT "elasticsearch-service:9200/_cluster/settings" -H 'Content-Type: application/json' -d '{"persistent":{"cluster.routing.allocation.enable":"primaries"}}'`
- [ ] Snapshot created and verified in GCS/other backup location
- [ ] PV reclaim policies set to "Retain": `kubectl get pv -o custom-columns=NAME:.metadata.name,RECLAIM:.spec.persistentVolumeReclaimPolicy`
- [ ] Elasticsearch operator (if used) compatible with K8s 1.32
- [ ] Regional pd-ssd volumes confirmed accessible from all zones

GKE Cluster Readiness
- [ ] Target version 1.32 available in current release channel
- [ ] GKE deprecation insights dashboard shows no deprecated API usage
- [ ] PDBs configured for each StatefulSet (recommend minAvailable=2 for masters, minAvailable=3 for data nodes)
- [ ] No bare pods in elasticsearch namespace
- [ ] Sufficient node capacity for surge upgrades (master and coordinating pools)
- [ ] terminationGracePeriodSeconds ≥ 120s for graceful Elasticsearch shutdown
```

---

## Upgrade Strategy

**Order:** Control plane → Coordinating nodes → Master nodes → Data nodes  
**Node Pool Strategy:** Conservative surge (`maxSurge=1, maxUnavailable=0`) to maintain quorum and availability  
**Key Principle:** Always maintain Elasticsearch cluster quorum (≥2 master nodes available)

---

## Step-by-Step Runbook

### Phase 1: Control Plane Upgrade

```bash
# Verify current state
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion)"

# Disable Elasticsearch shard allocation
curl -X PUT "elasticsearch-service:9200/_cluster/settings" \
  -H 'Content-Type: application/json' \
  -d '{"persistent":{"cluster.routing.allocation.enable":"primaries"}}'

# Upgrade control plane
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32

# Verify control plane upgrade (wait 10-15 minutes)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"

kubectl get pods -n kube-system
```

### Phase 2: Coordinating Nodes (Lowest Risk First)

```bash
# Configure conservative surge for coordinating node pool
gcloud container node-pools update coordinating-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade coordinating nodes
gcloud container node-pools upgrade coordinating-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor progress - ensure Elasticsearch remains accessible
watch 'kubectl get nodes -l nodepool=coordinating-pool'
curl -X GET "elasticsearch-service:9200/_cluster/health"
```

**Validation:** Elasticsearch cluster should remain green/yellow. Coordinating nodes don't hold data, so this is the safest upgrade.

### Phase 3: Master Nodes (Critical - Maintain Quorum)

```bash
# Configure conservative surge for master node pool
gcloud container node-pools update master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade master nodes ONE AT A TIME to maintain quorum
gcloud container node-pools upgrade master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor Elasticsearch master quorum throughout
watch 'curl -s "elasticsearch-service:9200/_cat/master?v"'
watch 'curl -s "elasticsearch-service:9200/_cluster/health" | jq ".status,.number_of_nodes,.active_primary_shards"'
```

**Critical:** With `maxSurge=1, maxUnavailable=0`, GKE creates a 4th master node, waits for Elasticsearch to join the cluster, then drains one old master. This maintains 3+ masters throughout the process. **Never** use `maxUnavailable=1` for master nodes - it would drop you to 2 masters during the upgrade.

### Phase 4: Data Nodes (Highest Risk - Contains Data)

```bash
# Verify Elasticsearch cluster is stable before data node upgrades
curl -X GET "elasticsearch-service:9200/_cluster/health"
# Should show status: "green" and all shards active

# Configure conservative surge for data node pool
gcloud container node-pools update data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade data nodes
gcloud container node-pools upgrade data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor data node upgrade closely
watch 'kubectl get pods -l app=elasticsearch-data'
watch 'curl -s "elasticsearch-service:9200/_cat/allocation?v"'
```

**Data Safety:** Regional pd-ssd volumes automatically reattach to replacement nodes. The PV → PVC → Pod binding ensures data persistence across node replacement.

### Phase 5: Re-enable Shard Allocation & Validation

```bash
# Re-enable full shard allocation
curl -X PUT "elasticsearch-service:9200/_cluster/settings" \
  -H 'Content-Type: application/json' \
  -d '{"persistent":{"cluster.routing.allocation.enable":"all"}}'

# Wait for cluster to rebalance (may take 10-30 minutes)
watch 'curl -s "elasticsearch-service:9200/_cluster/health"'

# Final validation
curl -X GET "elasticsearch-service:9200/_cluster/health?pretty"
curl -X GET "elasticsearch-service:9200/_cat/nodes?v"
curl -X GET "elasticsearch-service:9200/_cat/shards?v" | head -20
```

---

## Troubleshooting Elasticsearch-Specific Issues

### Issue: Split-Brain During Master Upgrade
**Symptoms:** Multiple master nodes claiming to be primary
```bash
curl -X GET "elasticsearch-service:9200/_cat/master?v"
# Shows different masters from different nodes
```
**Fix:** This shouldn't happen with surge upgrades, but if it does:
1. Stop all Elasticsearch pods temporarily
2. Clear cluster state from problem nodes
3. Restart in order: masters → coordinating → data

### Issue: Shards Not Relocating to New Nodes
**Symptoms:** Elasticsearch health stuck at "yellow", shards remain unassigned
```bash
curl -X GET "elasticsearch-service:9200/_cat/shards" | grep UNASSIGNED
```
**Fix:** Force reallocation for stuck shards:
```bash
curl -X POST "elasticsearch-service:9200/_cluster/reroute?retry_failed=true"
```

### Issue: Data Node PV Attachment Failures
**Symptoms:** New data pods stuck in "Pending" with PVC attachment errors
```bash
kubectl get events -n elasticsearch --field-selector reason=FailedAttachVolume
```
**Fix:** Regional pd-ssd should attach automatically. If not:
1. Verify the replacement node is in a zone where the PV exists
2. Check PV status: `kubectl get pv | grep elasticsearch`
3. For zone-locked PVs, manually cordon nodes in problematic zones

### Issue: Elasticsearch Pods Won't Terminate (Grace Period)
**Symptoms:** Pods stuck in "Terminating" during node drain
**Fix:** Elasticsearch needs time for graceful shutdown. Verify `terminationGracePeriodSeconds` is ≥ 120s. If stuck beyond grace period:
```bash
# Force delete as last resort
kubectl delete pod elasticsearch-data-X -n elasticsearch --force --grace-period=0
```

---

## Rollback Plan

If the upgrade causes data loss or split-brain:

1. **Control plane:** Contact GKE support for minor version rollback
2. **Node pools:** Create new pools at 1.31, migrate workloads:
```bash
gcloud container node-pools create data-pool-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31 \
  --num-nodes 5 \
  --machine-type e2-standard-4

# Cordon upgraded nodes
kubectl cordon -l nodepool=data-pool

# StatefulSets will recreate on new nodes, PVs will reattach
```
3. **Data recovery:** Restore from the pre-upgrade Elasticsearch snapshot

---

## Post-Upgrade Validation

```
Elasticsearch Cluster Health
- [ ] Cluster status: green (`curl -X GET "elasticsearch-service:9200/_cluster/health"`)
- [ ] All nodes present: `curl -X GET "elasticsearch-service:9200/_cat/nodes?v"`
- [ ] All shards active, no relocating/unassigned shards
- [ ] Index count matches pre-upgrade: `curl -X GET "elasticsearch-service:9200/_cat/indices?v"`
- [ ] Query performance within baseline (run test queries)
- [ ] Shard allocation re-enabled: `curl -X GET "elasticsearch-service:9200/_cluster/settings"`

GKE Infrastructure
- [ ] All node pools at 1.32: `gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE`
- [ ] All nodes Ready: `kubectl get nodes`
- [ ] StatefulSet pods running on new nodes: `kubectl get pods -n elasticsearch -o wide`
- [ ] PVs remain bound: `kubectl get pvc -n elasticsearch`
- [ ] No events indicating PV attachment issues
```

**Estimated Duration:** 2-3 hours total (45 min control plane + 30 min per node pool + rebalancing time)

**Key Success Factors:** 
- Conservative surge settings maintain quorum
- Regional PVs ensure data survives node replacement  
- Disabling shard allocation prevents unnecessary data movement
- Proper PDBs protect against over-aggressive eviction
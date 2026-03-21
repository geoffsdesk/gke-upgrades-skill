# GKE Upgrade Plan: Elasticsearch StatefulSet Cluster
**1.31 → 1.32 Standard Cluster**

## Environment Assessment
- **Cluster Mode:** Standard
- **Current → Target:** 1.31 → 1.32 (single minor version jump ✓)
- **Workload:** StatefulSet-based Elasticsearch (data-sensitive)
- **Topology:** 3 master + 5 data + 2 coordinating nodes on separate pools
- **Storage:** Regional pd-ssd PVs (good - survives zone failures)

## Upgrade Strategy

### Control Plane First (Required Order)
The control plane must be upgraded before any node pools. This is non-disruptive to running pods.

### Node Pool Strategy: Conservative Surge
For Elasticsearch StatefulSets, use **conservative surge settings** to prevent data loss:
- `maxSurge=1, maxUnavailable=0` - one new node added, zero removed until ready
- This ensures Elasticsearch can rebalance shards before any node goes down
- Elasticsearch masters need quorum (2 of 3), so never drain more than 1 master simultaneously

### Upgrade Sequence
1. **Control plane** (no pod disruption)
2. **Coordinating nodes** (stateless, safest to test)
3. **Master nodes** (critical for cluster state, but no data)
4. **Data nodes** (most critical, contains actual data)

## Pre-Upgrade Checklist

```
Elasticsearch-Specific Readiness
- [ ] Elasticsearch cluster health GREEN: `kubectl exec -it elasticsearch-master-0 -- curl -s localhost:9200/_cluster/health`
- [ ] All shards allocated: `kubectl exec -it elasticsearch-master-0 -- curl -s localhost:9200/_cat/shards?v`
- [ ] Disable shard allocation during upgrade: `curl -X PUT localhost:9200/_cluster/settings -H "Content-Type: application/json" -d '{"persistent":{"cluster.routing.allocation.enable":"primaries"}}'`
- [ ] Recent snapshot completed to GCS/S3
- [ ] No ongoing reindex or heavy write operations
- [ ] Elasticsearch PDB configured: `kubectl get pdb elasticsearch-master elasticsearch-data`
- [ ] terminationGracePeriodSeconds ≥ 120s for graceful shutdown

Storage & StatefulSet Readiness  
- [ ] All PVCs bound and healthy: `kubectl get pvc -l app=elasticsearch`
- [ ] PV reclaim policy is Retain: `kubectl get pv -o custom-columns=NAME:.metadata.name,RECLAIM:.spec.persistentVolumeReclaimPolicy`
- [ ] StatefulSet update strategy is RollingUpdate: `kubectl get statefulset elasticsearch-master -o yaml | grep updateStrategy`
- [ ] Regional pd-ssd confirmed for zone tolerance

Node Pool Configuration
- [ ] Surge settings configured conservatively per pool:
  - Master pool: maxSurge=1, maxUnavailable=0
  - Data pool: maxSurge=1, maxUnavailable=0  
  - Coordinating pool: maxSurge=1, maxUnavailable=0
- [ ] Sufficient compute quota for surge nodes
- [ ] Node pool names confirmed: `gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE`
```

## Upgrade Runbook

### Step 1: Pre-flight Checks

```bash
# Verify current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Confirm 1.32 available in your release channel
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels)"

# Elasticsearch cluster health
kubectl exec -it elasticsearch-master-0 -- curl -s localhost:9200/_cluster/health | jq '.status'
# Must return "green"

# Check PV reclaim policies
kubectl get pv -o custom-columns=NAME:.metadata.name,RECLAIM:.spec.persistentVolumeReclaimPolicy
```

### Step 2: Prepare Elasticsearch for Maintenance

```bash
# Disable shard allocation (prevents rebalancing during node restarts)
kubectl exec -it elasticsearch-master-0 -- curl -X PUT localhost:9200/_cluster/settings \
  -H "Content-Type: application/json" \
  -d '{"persistent":{"cluster.routing.allocation.enable":"primaries"}}'

# Trigger manual snapshot (if not automated)
kubectl exec -it elasticsearch-master-0 -- curl -X PUT localhost:9200/_snapshot/gcs-repository/pre-upgrade-snapshot \
  -H "Content-Type: application/json" \
  -d '{"indices":"*","ignore_unavailable":true,"include_global_state":false}'
```

### Step 3: Configure Node Pool Surge Settings

```bash
# Master nodes (maintain quorum)
gcloud container node-pools update elasticsearch-master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Data nodes (protect data)
gcloud container node-pools update elasticsearch-data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Coordinating nodes (stateless but conservative)
gcloud container node-pools update elasticsearch-coord-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### Step 4: Control Plane Upgrade

```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32

# Wait and verify (~10-15 minutes)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"

kubectl get pods -n kube-system
# All system pods should be healthy
```

### Step 5: Node Pool Upgrades (Sequential)

**5a. Coordinating Nodes First**
```bash
gcloud container node-pools upgrade elasticsearch-coord-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor progress
watch 'kubectl get nodes -l elasticsearch-role=coordinating -o wide'

# Verify Elasticsearch can reach all masters
kubectl exec -it elasticsearch-coord-0 -- curl -s localhost:9200/_cat/master?v
```

**5b. Master Nodes Second**
```bash
gcloud container node-pools upgrade elasticsearch-master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor master quorum during upgrade
watch 'kubectl exec -it elasticsearch-master-0 -- curl -s localhost:9200/_cat/master?v'
# Should maintain quorum throughout (2/3 masters always available)
```

**5c. Data Nodes Last**
```bash
gcloud container node-pools upgrade elasticsearch-data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor shard allocation
watch 'kubectl exec -it elasticsearch-master-0 -- curl -s localhost:9200/_cat/shards?h=index,shard,prirep,state,unassigned.reason | grep -v STARTED | head -10'
```

### Step 6: Post-Upgrade Validation

```bash
# All node pools at 1.32
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE

# All StatefulSet pods running
kubectl get statefulsets -l app=elasticsearch
kubectl get pods -l app=elasticsearch

# Re-enable shard allocation
kubectl exec -it elasticsearch-master-0 -- curl -X PUT localhost:9200/_cluster/settings \
  -H "Content-Type: application/json" \
  -d '{"persistent":{"cluster.routing.allocation.enable":null}}'

# Wait for cluster to return to GREEN
kubectl exec -it elasticsearch-master-0 -- curl -s localhost:9200/_cluster/health | jq '.status'

# Verify all shards allocated
kubectl exec -it elasticsearch-master-0 -- curl -s localhost:9200/_cat/shards?v | grep -c STARTED
```

## Elasticsearch-Specific Safeguards

### PodDisruptionBudgets
Ensure these PDBs exist:
```yaml
# Master nodes (maintain quorum)
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-master
spec:
  minAvailable: 2
  selector:
    matchLabels:
      elasticsearch-role: master

# Data nodes (protect data availability)  
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-data
spec:
  minAvailable: 4
  selector:
    matchLabels:
      elasticsearch-role: data
```

### StatefulSet Configuration
Verify graceful termination:
```yaml
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 180  # Allow ES to flush and close
      containers:
      - name: elasticsearch
        lifecycle:
          preStop:
            exec:
              command: ["/bin/bash", "-c", "curl -X POST localhost:9200/_flush/synced"]
```

## Rollback Plan

If Elasticsearch cluster health degrades:

1. **Immediate:** Re-enable shard allocation if disabled
2. **Pod-level:** Restart failed pods: `kubectl delete pod elasticsearch-data-X`
3. **Node-level:** Create new node pool at 1.31, migrate StatefulSets
4. **Data-level:** Restore from pre-upgrade snapshot if data corruption detected

## Timeline Estimate

- **Control plane:** 15 minutes
- **Coordinating pool:** 30 minutes (2 nodes)
- **Master pool:** 45 minutes (3 nodes, wait for rebalancing)
- **Data pool:** 75 minutes (5 nodes, heaviest rebalancing)
- **Total:** ~2.5 hours + validation time

**Recommended maintenance window:** 4 hours to allow for troubleshooting.

The regional pd-ssd storage and conservative surge strategy ensure your Elasticsearch data remains safe and available throughout the upgrade process.
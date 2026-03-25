# GKE Upgrade Plan: Elasticsearch Cluster (1.31 → 1.32)

## Environment Overview
- **Cluster Mode:** Standard
- **Current Version:** 1.31
- **Target Version:** 1.32
- **Workload:** Elasticsearch StatefulSet (3 masters, 5 data, 2 coordinators)
- **Storage:** Regional pd-ssd PVs
- **Node Pools:** 3 separate pools (masters, data, coordinators)

## Pre-Upgrade Checklist

### Elasticsearch-Specific Preparations
- [ ] **Elasticsearch cluster health check:**
  ```bash
  kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"
  # Ensure status: green, no relocating/initializing shards
  ```

- [ ] **Disable shard allocation** (prevents rebalancing during node upgrades):
  ```bash
  kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" \
    -H 'Content-Type: application/json' -d'
  {
    "persistent": {
      "cluster.routing.allocation.enable": "primaries"
    }
  }'
  ```

- [ ] **Application-level backup** (pre-upgrade snapshot):
  ```bash
  kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_snapshot/backup_repo/pre_upgrade_snapshot?wait_for_completion=true"
  ```

- [ ] **Verify PV reclaim policy** (safety check):
  ```bash
  kubectl get pv -o custom-columns=NAME:.metadata.name,RECLAIM:.spec.persistentVolumeReclaimPolicy | grep -v Retain
  # If any show "Delete", change to "Retain" before upgrade
  ```

### Configure PDBs for Safe Drain
```bash
# Master nodes PDB - maintain quorum (2 of 3 available)
cat <<EOF | kubectl apply -f -
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: es-master-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: elasticsearch
      role: master
EOF

# Data nodes PDB - conservative (4 of 5 available)
cat <<EOF | kubectl apply -f -
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: es-data-pdb
spec:
  minAvailable: 4
  selector:
    matchLabels:
      app: elasticsearch
      role: data
EOF

# Coordinator nodes PDB - keep 1 available
cat <<EOF | kubectl apply -f -
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: es-coordinator-pdb
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: elasticsearch
      role: coordinator
EOF
```

### Configure Node Pool Upgrade Strategy
```bash
# Conservative settings for all Elasticsearch pools - one node at a time
# Coordinators first (lowest risk)
gcloud container node-pools update es-coordinator-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Data nodes (moderate risk)
gcloud container node-pools update es-data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Masters last (highest risk)
gcloud container node-pools update es-master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

## Upgrade Execution

### Step 1: Control Plane Upgrade
```bash
# Upgrade control plane first (required order)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32

# Monitor progress (~10-15 minutes)
watch 'gcloud container clusters describe CLUSTER_NAME --zone ZONE --format="value(currentMasterVersion)"'

# Verify system pods healthy
kubectl get pods -n kube-system
```

### Step 2: Node Pool Upgrades (Sequential Order)

**Phase 1: Coordinators first (lowest risk, stateless)**
```bash
gcloud container node-pools upgrade es-coordinator-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor coordinator upgrade
watch 'kubectl get nodes -l node-pool=es-coordinator-pool -o wide'
kubectl get pods -l role=coordinator -o wide
```

**Phase 2: Data nodes (wait for coordinators to complete)**
```bash
# Verify coordinators healthy before proceeding
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"

gcloud container node-pools upgrade es-data-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor data node upgrade carefully
watch 'kubectl get nodes -l node-pool=es-data-pool -o wide'
kubectl get pods -l role=data -o wide

# Check cluster health during data node upgrades
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?level=shards&pretty"
```

**Phase 3: Masters last (highest risk, wait for data nodes to complete)**
```bash
# Verify data nodes healthy and cluster green
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"

gcloud container node-pools upgrade es-master-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor master upgrade - critical phase
watch 'kubectl get nodes -l node-pool=es-master-pool -o wide'
kubectl get pods -l role=master -o wide

# Watch for master election during upgrade
kubectl logs -l role=master -f --tail=50
```

## Post-Upgrade Validation

### Re-enable Elasticsearch Shard Allocation
```bash
# Allow normal shard allocation to resume
kubectl exec -it es-master-0 -- curl -X PUT "localhost:9200/_cluster/settings" \
  -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": null
  }
}'
```

### Comprehensive Health Checks
```bash
# 1. All nodes at target version
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE

# 2. All Kubernetes nodes ready
kubectl get nodes

# 3. All Elasticsearch pods running
kubectl get pods -l app=elasticsearch -o wide

# 4. Elasticsearch cluster health
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"
# Expect: status: "green", active_primary_shards > 0, relocating_shards: 0

# 5. All shards allocated
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cat/shards?v"

# 6. Cluster stats (verify data integrity)
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/stats?pretty"

# 7. StatefulSet status
kubectl get statefulsets -o wide

# 8. PVC status (no data loss)
kubectl get pvc | grep elasticsearch
```

### Smoke Test
```bash
# Index test document
kubectl exec -it es-master-0 -- curl -X POST "localhost:9200/upgrade_test/_doc/1" \
  -H 'Content-Type: application/json' -d'
{
  "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
  "message": "Post-upgrade test"
}'

# Retrieve test document
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/upgrade_test/_doc/1?pretty"

# Clean up test index
kubectl exec -it es-master-0 -- curl -X DELETE "localhost:9200/upgrade_test"
```

## Rollback Plan (if needed)

If issues occur during the upgrade:

### Immediate Response
```bash
# Cancel ongoing node pool upgrade
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="status=RUNNING"
# Note operation ID, then monitor - GKE will complete current node and stop

# Check Elasticsearch cluster status
kubectl exec -it es-master-0 -- curl -X GET "localhost:9200/_cluster/health?pretty"
```

### Node Pool Rollback (last resort)
```bash
# Create new node pool at previous version
gcloud container node-pools create es-data-pool-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31 \
  --num-nodes 5 \
  --machine-type MACHINE_TYPE \
  --disk-size DISK_SIZE

# Cordon affected nodes
kubectl cordon -l node-pool=es-data-pool

# Wait for Elasticsearch to rebalance away from cordoned nodes
# Then delete old pool and rename new one
```

## Critical Warnings

⚠️ **During data node upgrades:** Expect temporary cluster yellow status as nodes drain. This is normal - Elasticsearch will maintain availability through replicas.

⚠️ **Master node upgrades:** Brief leadership changes are normal. Monitor logs for successful master elections.

⚠️ **Do not skip the shard allocation disable/re-enable steps** - this prevents unnecessary data movement during upgrades.

⚠️ **PDB timeout:** GKE respects PDBs for up to 1 hour, then force-evicts. If a data node won't drain due to PDB, temporarily reduce `minAvailable` to unblock.

⚠️ **Upgrade order matters:** Always coordinators → data → masters. Masters must be upgraded last to maintain cluster coordination.

The regional pd-ssd storage will persist through the upgrade, but the shard allocation controls and sequential upgrade approach ensure no data loss or extended unavailability.
# GKE Upgrade Plan: Elasticsearch Cluster 1.29 → 1.30

## Overview
Upgrading a StatefulSet-based Elasticsearch cluster requires careful orchestration to maintain quorum, prevent split-brain, and preserve data integrity. This plan prioritizes zero data loss over minimal downtime.

## Environment Assessment
- **Cluster**: GKE Standard 1.29 → 1.30
- **Workload**: Elasticsearch with 3 masters, 5 data nodes, 2 coordinating nodes
- **Storage**: Regional pd-ssd PVs (good - can reattach across zones)
- **Node pools**: Separate pools per ES role (excellent isolation)

## Pre-Upgrade Checklist

### Elasticsearch Cluster Health
```bash
# Verify cluster is green and stable
kubectl exec -n elasticsearch es-master-0 -- curl -s "localhost:9200/_cluster/health?pretty"

# Check all nodes are active
kubectl exec -n elasticsearch es-master-0 -- curl -s "localhost:9200/_cat/nodes?v&h=name,node.role,health,status"

# Verify shard allocation is complete
kubectl exec -n elasticsearch es-master-0 -- curl -s "localhost:9200/_cluster/health?wait_for_status=green&timeout=30s"

# Document current settings
kubectl exec -n elasticsearch es-master-0 -- curl -s "localhost:9200/_cluster/settings?pretty&include_defaults=true" > es-settings-backup.json
```

### GKE Upgrade Readiness
```bash
# Verify target version availability
gcloud container get-server-config --zone YOUR_ZONE --format="yaml(channels)"

# Check current cluster state
gcloud container clusters describe YOUR_CLUSTER --zone YOUR_ZONE --format="table(name,currentMasterVersion,nodePools[].name,nodePools[].version)"

# Verify no deprecated API usage
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
```

### Data Protection
```bash
# Create snapshot repository (if not already configured)
kubectl exec -n elasticsearch es-master-0 -- curl -XPUT "localhost:9200/_snapshot/gcs-backup" -H 'Content-Type: application/json' -d'{
  "type": "gcs",
  "settings": {
    "bucket": "your-es-backup-bucket",
    "base_path": "elasticsearch-snapshots"
  }
}'

# Take full cluster snapshot
kubectl exec -n elasticsearch es-master-0 -- curl -XPUT "localhost:9200/_snapshot/gcs-backup/pre-upgrade-$(date +%Y%m%d-%H%M)" -H 'Content-Type: application/json' -d'{
  "indices": "*",
  "ignore_unavailable": true,
  "include_global_state": true
}'

# Monitor snapshot completion
kubectl exec -n elasticsearch es-master-0 -- curl -s "localhost:9200/_snapshot/gcs-backup/_current"
```

## Elasticsearch Pre-Upgrade Configuration

### Disable Shard Allocation
```bash
# Prevent shard movement during upgrade
kubectl exec -n elasticsearch es-master-0 -- curl -XPUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'
```

### Configure PDBs (Critical)
```yaml
# Apply these PDBs to protect quorum
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: es-master-pdb
  namespace: elasticsearch
spec:
  minAvailable: 2  # Maintain master quorum (2 out of 3)
  selector:
    matchLabels:
      app: elasticsearch
      role: master
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: es-data-pdb
  namespace: elasticsearch
spec:
  minAvailable: 4  # Keep most data nodes available
  selector:
    matchLabels:
      app: elasticsearch
      role: data
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: es-coordinating-pdb
  namespace: elasticsearch
spec:
  minAvailable: 1  # Keep at least one coordinator
  selector:
    matchLabels:
      app: elasticsearch
      role: coordinating
```

## Node Pool Upgrade Strategy

Configure conservative surge settings for each pool:

```bash
# Master nodes - most critical, slowest upgrade
gcloud container node-pools update es-master-pool \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Data nodes - balance between speed and safety
gcloud container node-pools update es-data-pool \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# Coordinating nodes - can upgrade faster
gcloud container node-pools update es-coordinating-pool \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

## Upgrade Execution

### Phase 1: Control Plane
```bash
# Upgrade control plane first
gcloud container clusters upgrade YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --master \
  --cluster-version 1.30.8-gke.1016000  # Use specific patch version

# Wait and verify (10-15 minutes)
gcloud container clusters describe YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --format="value(currentMasterVersion)"

# Ensure ES cluster still healthy
kubectl exec -n elasticsearch es-master-0 -- curl -s "localhost:9200/_cluster/health"
```

### Phase 2: Coordinating Nodes (Least Critical First)
```bash
# Upgrade coordinating node pool
gcloud container node-pools upgrade es-coordinating-pool \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --cluster-version 1.30.8-gke.1016000

# Monitor progress
watch 'kubectl get nodes -l node-pool=es-coordinating-pool'
watch 'kubectl get pods -n elasticsearch -l role=coordinating'
```

### Phase 3: Data Nodes (One at a Time Monitoring)
```bash
# Before starting data node upgrade, verify cluster is still green
kubectl exec -n elasticsearch es-master-0 -- curl -s "localhost:9200/_cluster/health"

# Upgrade data node pool
gcloud container node-pools upgrade es-data-pool \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --cluster-version 1.30.8-gke.1016000

# Critical: Monitor ES cluster health during data node upgrades
# Run this in a separate terminal:
while true; do
  echo "$(date): $(kubectl exec -n elasticsearch es-master-0 -- curl -s "localhost:9200/_cluster/health" | jq -r '.status')"
  sleep 30
done
```

**If cluster goes yellow/red during data node upgrade:**
```bash
# Check which shards are unassigned
kubectl exec -n elasticsearch es-master-0 -- curl -s "localhost:9200/_cat/shards?v&h=index,shard,prirep,state,node&s=state"

# Wait for nodes to rejoin before continuing
kubectl exec -n elasticsearch es-master-0 -- curl -s "localhost:9200/_cat/nodes?v"
```

### Phase 4: Master Nodes (Most Critical - One by One)
```bash
# CRITICAL: Master nodes must maintain quorum
# The PDB ensures only 1 master is down at a time

# Before upgrading masters, ensure cluster is completely stable
kubectl exec -n elasticsearch es-master-0 -- curl -s "localhost:9200/_cluster/health?wait_for_status=green&timeout=300s"

# Upgrade master node pool
gcloud container node-pools upgrade es-master-pool \
  --cluster YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --cluster-version 1.30.8-gke.1016000

# Monitor master election during upgrade
watch 'kubectl exec -n elasticsearch es-master-0 -- curl -s "localhost:9200/_cat/master?v" 2>/dev/null || echo "Master unreachable"'
```

## Post-Upgrade Restoration

### Re-enable Shard Allocation
```bash
# Once all nodes are upgraded and cluster is green
kubectl exec -n elasticsearch es-master-0 -- curl -XPUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'{
  "persistent": {
    "cluster.routing.allocation.enable": null
  }
}'

# Trigger shard rebalancing
kubectl exec -n elasticsearch es-master-0 -- curl -XPOST "localhost:9200/_cluster/reroute?retry_failed=true"
```

### Final Validation
```bash
# Verify all nodes are back and cluster is green
kubectl exec -n elasticsearch es-master-0 -- curl -s "localhost:9200/_cluster/health?pretty"
kubectl exec -n elasticsearch es-master-0 -- curl -s "localhost:9200/_cat/nodes?v"

# Check shard distribution
kubectl exec -n elasticsearch es-master-0 -- curl -s "localhost:9200/_cat/shards?v&s=index"

# Verify all expected nodes are present
kubectl get pods -n elasticsearch -o wide

# Test query performance
kubectl exec -n elasticsearch es-master-0 -- curl -s "localhost:9200/_search?size=1&pretty"
```

## Rollback Plan (If Needed)

If the upgrade fails and ES cluster becomes unstable:

1. **Immediate**: Restore shard allocation if disabled
2. **Node-level**: Create new node pools at 1.29 and migrate StatefulSets
3. **Data-level**: Restore from pre-upgrade snapshot
4. **Network**: Ensure new pods can reach existing PVs

```bash
# Emergency: Restore from snapshot
kubectl exec -n elasticsearch es-master-0 -- curl -XPOST "localhost:9200/_snapshot/gcs-backup/pre-upgrade-TIMESTAMP/_restore" -H 'Content-Type: application/json' -d'{
  "indices": "*",
  "ignore_unavailable": true,
  "include_global_state": true
}'
```

## Key Success Factors

1. **PDBs are critical** - They prevent too many masters from being down simultaneously
2. **Disable shard allocation first** - Prevents unnecessary data movement
3. **Take snapshots** - Your safety net for catastrophic failure
4. **Monitor ES health continuously** - GKE operations can succeed while ES cluster fails
5. **Upgrade order matters** - Coordinating → Data → Masters (least to most critical)
6. **Regional PVs are your friend** - They can reattach to nodes in any zone

This approach prioritizes data safety over speed. The upgrade will take 2-4 hours but should complete with zero data loss and minimal query impact.
I'll walk you through a safe GKE cluster upgrade strategy for your Elasticsearch deployment. This approach minimizes risk while maintaining data integrity and availability.

## Pre-Upgrade Preparation

### 1. Backup and Health Check
```bash
# Check cluster health
kubectl get nodes
kubectl get pods -n <elasticsearch-namespace>

# Verify Elasticsearch cluster health
curl -X GET "elasticsearch-service:9200/_cluster/health?pretty"

# Create Elasticsearch snapshot (recommended)
curl -X PUT "elasticsearch-service:9200/_snapshot/my_backup/pre_upgrade_snapshot?wait_for_completion=true"

# Verify PV status
kubectl get pv
kubectl get pvc -n <elasticsearch-namespace>
```

### 2. Disable Elasticsearch Shard Allocation
```bash
# Temporarily disable shard allocation during upgrade
curl -X PUT "elasticsearch-service:9200/_cluster/settings" \
  -H 'Content-Type: application/json' \
  -d '{
    "persistent": {
      "cluster.routing.allocation.enable": "primaries"
    }
  }'
```

## Upgrade Strategy: Node Pool by Node Pool

### Phase 1: Upgrade Coordinating Nodes First
Coordinating nodes are safest to start with as they don't store data.

```bash
# Upgrade coordinating node pool
gcloud container node-pools upgrade <coordinating-pool-name> \
  --cluster=<cluster-name> \
  --zone=<zone-or-region> \
  --node-version=1.32 \
  --max-surge=1 \
  --max-unavailable=0
```

Wait for completion and verify:
```bash
kubectl get nodes -l node-pool=<coordinating-pool>
curl -X GET "elasticsearch-service:9200/_cluster/health"
```

### Phase 2: Upgrade Master Nodes (One at a Time)
```bash
# Upgrade master node pool with careful surge settings
gcloud container node-pools upgrade <master-pool-name> \
  --cluster=<cluster-name> \
  --zone=<zone-or-region> \
  --node-version=1.32 \
  --max-surge=0 \
  --max-unavailable=1
```

**Critical**: Monitor Elasticsearch master election during this phase:
```bash
# Watch master nodes
kubectl get pods -l role=master -w

# Check cluster state
curl -X GET "elasticsearch-service:9200/_cat/master?v"
```

### Phase 3: Upgrade Data Nodes (Most Critical)
```bash
# Upgrade data node pool very conservatively
gcloud container node-pools upgrade <data-pool-name> \
  --cluster=<cluster-name> \
  --zone=<zone-or-region> \
  --node-version=1.32 \
  --max-surge=0 \
  --max-unavailable=1
```

**Monitor closely**:
```bash
# Watch for shard relocation
curl -X GET "elasticsearch-service:9200/_cat/shards?v&h=index,shard,prirep,state,node"

# Monitor cluster health continuously
watch "curl -s elasticsearch-service:9200/_cluster/health | jq"
```

### Phase 4: Upgrade Control Plane
```bash
# Finally upgrade the control plane
gcloud container clusters upgrade <cluster-name> \
  --master \
  --cluster-version=1.32 \
  --zone=<zone-or-region>
```

## Post-Upgrade Tasks

### 1. Re-enable Shard Allocation
```bash
curl -X PUT "elasticsearch-service:9200/_cluster/settings" \
  -H 'Content-Type: application/json' \
  -d '{
    "persistent": {
      "cluster.routing.allocation.enable": "all"
    }
  }'
```

### 2. Verify Everything is Healthy
```bash
# Check all nodes are on 1.32
kubectl get nodes -o wide

# Verify Elasticsearch cluster health
curl -X GET "elasticsearch-service:9200/_cluster/health?pretty"

# Check all shards are assigned
curl -X GET "elasticsearch-service:9200/_cat/shards?v" | grep -i unassigned

# Verify all pods are running
kubectl get pods -n <elasticsearch-namespace>

# Check PV status
kubectl get pv | grep -v Bound
```

## Safety Considerations

### StatefulSet Specific
- **Pod Disruption Budgets**: Ensure you have appropriate PDBs:
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-master-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      role: master
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: elasticsearch-data-pdb
spec:
  minAvailable: 4
  selector:
    matchLabels:
      role: data
```

### Regional PD-SSD Considerations
- Your regional persistent disks will automatically reattach to new nodes
- Verify PV reclaim policy is "Retain":
```bash
kubectl get pv -o custom-columns=NAME:.metadata.name,RECLAIM:.spec.persistentVolumeReclaimPolicy
```

### Emergency Rollback Plan
```bash
# If issues arise, rollback node pool
gcloud container node-pools rollback <pool-name> \
  --cluster=<cluster-name> \
  --zone=<zone-or-region>

# Restore from snapshot if needed
curl -X POST "elasticsearch-service:9200/_snapshot/my_backup/pre_upgrade_snapshot/_restore"
```

## Timeline Expectations
- **Coordinating nodes**: 10-15 minutes
- **Master nodes**: 20-30 minutes (due to careful unavailability settings)
- **Data nodes**: 45-90 minutes (largest pool, most critical)
- **Control plane**: 10-15 minutes
- **Total**: 2-3 hours

Monitor Elasticsearch logs throughout:
```bash
kubectl logs -f <elasticsearch-pod> -n <elasticsearch-namespace>
```

This approach prioritizes data safety over speed, which is appropriate for production Elasticsearch clusters.
I'll walk you through a safe GKE upgrade strategy for your Elasticsearch cluster. This approach minimizes risk by upgrading infrastructure first, then applications.

## Pre-Upgrade Preparation

### 1. Backup and Validation
```bash
# Create Elasticsearch snapshot
curl -X PUT "localhost:9200/_snapshot/backup_repo/pre_upgrade_snapshot?wait_for_completion=true"

# Verify cluster health
curl -X GET "localhost:9200/_cluster/health"

# Document current versions
kubectl get nodes -o wide
kubectl get pods -o wide -n <elasticsearch-namespace>
```

### 2. Disable Elasticsearch Shard Allocation
```bash
# Prevent shard rebalancing during upgrades
curl -X PUT "localhost:9200/_cluster/settings" -H "Content-Type: application/json" -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'
```

## Phase 1: Upgrade GKE Control Plane

```bash
# Check available versions
gcloud container get-server-config --region=<your-region>

# Upgrade control plane (no downtime)
gcloud container clusters upgrade <cluster-name> \
  --master \
  --cluster-version=1.32.x \
  --region=<your-region>
```

## Phase 2: Upgrade Node Pools (Rolling Strategy)

### Step 1: Upgrade Coordinating Nodes First
```bash
# Coordinating nodes can be upgraded with minimal impact
gcloud container node-pools upgrade <coordinating-pool-name> \
  --cluster=<cluster-name> \
  --region=<your-region> \
  --node-version=1.32.x
```

### Step 2: Upgrade Master Node Pool
```bash
# Before upgrading, ensure cluster is stable
curl -X GET "localhost:9200/_cluster/health"

# Upgrade master nodes one by one
gcloud container node-pools upgrade <master-pool-name> \
  --cluster=<cluster-name> \
  --region=<your-region> \
  --node-version=1.32.x \
  --max-surge=1 \
  --max-unavailable=0
```

**Monitor between each master node upgrade:**
```bash
# Wait for green status before proceeding
while [[ $(curl -s "localhost:9200/_cluster/health" | jq -r '.status') != "green" ]]; do
  echo "Waiting for cluster to be green..."
  sleep 30
done
```

### Step 3: Upgrade Data Nodes (Most Critical)
```bash
# Upgrade data nodes with careful surge settings
gcloud container node-pools upgrade <data-pool-name> \
  --cluster=<cluster-name> \
  --region=<your-region> \
  --node-version=1.32.x \
  --max-surge=1 \
  --max-unavailable=0
```

**Monitor data node upgrades closely:**
```bash
# Script to monitor during data node upgrades
#!/bin/bash
while true; do
  health=$(curl -s "localhost:9200/_cluster/health")
  status=$(echo $health | jq -r '.status')
  relocating=$(echo $health | jq -r '.relocating_shards')
  
  echo "Status: $status, Relocating shards: $relocating"
  
  if [[ $relocating -gt 0 ]]; then
    echo "Waiting for shard relocation to complete..."
  fi
  
  sleep 30
done
```

## Phase 3: Post-Upgrade Tasks

### 1. Re-enable Shard Allocation
```bash
curl -X PUT "localhost:9200/_cluster/settings" -H "Content-Type: application/json" -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "all"
  }
}'
```

### 2. Verify Cluster Health
```bash
# Wait for green status
curl -X GET "localhost:9200/_cluster/health?wait_for_status=green&timeout=300s"

# Check all nodes are present
curl -X GET "localhost:9200/_cat/nodes?v"

# Verify shard distribution
curl -X GET "localhost:9200/_cat/shards?v"
```

## Alternative: Blue-Green Deployment Strategy

If you need zero downtime and have the resources:

```yaml
# Create parallel node pools with 1.32
apiVersion: v1
kind: NodePool
metadata:
  name: elasticsearch-data-132
spec:
  version: "1.32.x"
  # ... other configs
```

Then gradually migrate StatefulSet pods:
```bash
# Add node affinity to new nodes
kubectl patch statefulset elasticsearch-data -p '
{
  "spec": {
    "template": {
      "spec": {
        "affinity": {
          "nodeAffinity": {
            "requiredDuringSchedulingIgnoredDuringExecution": {
              "nodeSelectorTerms": [{
                "matchExpressions": [{
                  "key": "cloud.google.com/gke-nodepool",
                  "operator": "In",
                  "values": ["elasticsearch-data-132"]
                }]
              }]
            }
          }
        }
      }
    }
  }
}'

# Rolling restart to move to new nodes
kubectl rollout restart statefulset/elasticsearch-data
```

## Key Safety Considerations

1. **PV Compatibility**: Regional pd-ssd volumes will automatically reattach to new nodes
2. **Master Quorum**: Never upgrade more than 1 master node at a time
3. **Data Integrity**: Monitor shard allocation throughout the process
4. **Rollback Plan**: Keep old node pools until verification is complete
5. **Timing**: Perform during low-traffic periods

## Emergency Rollback

If issues arise:
```bash
# Rollback node pool
gcloud container node-pools rollback <pool-name> \
  --cluster=<cluster-name> \
  --region=<your-region>

# Restore from snapshot if needed
curl -X POST "localhost:9200/_snapshot/backup_repo/pre_upgrade_snapshot/_restore"
```

The entire process should take 2-4 hours depending on your cluster size and shard count. The key is patience and monitoring between each phase.
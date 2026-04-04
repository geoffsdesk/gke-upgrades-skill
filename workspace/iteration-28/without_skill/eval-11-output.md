I'll walk you through a safe GKE cluster upgrade strategy for your Elasticsearch setup. Given your architecture with separate node pools, we can do a rolling upgrade to maintain availability.

## Pre-Upgrade Preparation

### 1. Backup and Validation
```bash
# Create Elasticsearch snapshot
kubectl exec -it <es-pod> -- curl -X PUT "localhost:9200/_snapshot/my-backup/pre-upgrade-snapshot" \
  -H 'Content-Type: application/json' -d'{"indices": "*","ignore_unavailable": true}'

# Verify cluster health
kubectl exec -it <es-pod> -- curl "localhost:9200/_cluster/health?pretty"

# Document current state
kubectl get nodes -o wide
kubectl get pods -o wide -n <elasticsearch-namespace>
kubectl get pv
```

### 2. Disable Shard Allocation (Temporary)
```bash
kubectl exec -it <es-pod> -- curl -X PUT "localhost:9200/_cluster/settings" \
  -H 'Content-Type: application/json' -d'{
    "persistent": {
      "cluster.routing.allocation.enable": "primaries"
    }
  }'
```

## Upgrade Strategy: Control Plane First, Then Node Pools

### 3. Upgrade Control Plane
```bash
# Check available versions
gcloud container get-server-config --region=<your-region>

# Upgrade control plane (no downtime)
gcloud container clusters upgrade <cluster-name> \
  --master \
  --cluster-version=1.32.x-gke.x \
  --region=<your-region>
```

### 4. Node Pool Upgrade Order (Critical for ES)

**Order: Coordinating → Data → Master nodes**

#### A. Upgrade Coordinating Nodes First
```bash
# Coordinating nodes can be upgraded quickly since they don't store data
gcloud container node-pools upgrade <coordinating-node-pool> \
  --cluster=<cluster-name> \
  --cluster-version=1.32.x-gke.x \
  --region=<your-region>
```

#### B. Upgrade Data Nodes (One by One)
```bash
# For each data node pool, or if using one pool with multiple nodes:
# Method 1: Rolling upgrade (safer but slower)
gcloud container node-pools upgrade <data-node-pool> \
  --cluster=<cluster-name> \
  --cluster-version=1.32.x-gke.x \
  --region=<your-region> \
  --max-surge=1 \
  --max-unavailable=0

# Method 2: Manual node-by-node (more control)
# Drain one data node at a time
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data --grace-period=300

# Wait for ES to rebalance, then continue with next node
```

#### C. Upgrade Master Nodes (Most Critical)
```bash
# Before upgrading master nodes, ensure cluster is green
kubectl exec -it <es-pod> -- curl "localhost:9200/_cluster/health?wait_for_status=green&timeout=5m"

# Upgrade master node pool with conservative settings
gcloud container node-pools upgrade <master-node-pool> \
  --cluster=<cluster-name> \
  --cluster-version=1.32.x-gke.x \
  --region=<your-region> \
  --max-surge=1 \
  --max-unavailable=0
```

## During Each Node Pool Upgrade

### 5. Monitor Elasticsearch Health
```bash
# Create monitoring script
cat > monitor-es.sh << 'EOF'
#!/bin/bash
while true; do
  echo "=== $(date) ==="
  kubectl exec -it <es-pod> -- curl -s "localhost:9200/_cluster/health?pretty" | grep -E "(status|number_of_nodes|active_shards)"
  kubectl exec -it <es-pod> -- curl -s "localhost:9200/_cat/nodes?v"
  echo "===================="
  sleep 30
done
EOF

chmod +x monitor-es.sh
./monitor-es.sh &
```

### 6. Handle PV Attachments
Since you're using regional pd-ssd, the volumes should automatically reattach, but monitor:

```bash
# Watch PV status during node transitions
kubectl get pv -w

# Check for any pending pods
kubectl get pods -n <elasticsearch-namespace> | grep Pending
```

## Post-Upgrade Steps

### 7. Re-enable Shard Allocation
```bash
kubectl exec -it <es-pod> -- curl -X PUT "localhost:9200/_cluster/settings" \
  -H 'Content-Type: application/json' -d'{
    "persistent": {
      "cluster.routing.allocation.enable": "all"
    }
  }'
```

### 8. Final Validation
```bash
# Verify cluster health
kubectl exec -it <es-pod> -- curl "localhost:9200/_cluster/health?pretty"

# Check all nodes are present
kubectl exec -it <es-pod> -- curl "localhost:9200/_cat/nodes?v"

# Verify data integrity
kubectl exec -it <es-pod> -- curl "localhost:9200/_cat/indices?v"

# Test search functionality
kubectl exec -it <es-pod> -- curl "localhost:9200/_search?size=1&pretty"
```

## Rollback Plan

If issues occur:
```bash
# Emergency: Scale up old version nodes
gcloud container node-pools create temp-rollback-pool \
  --cluster=<cluster-name> \
  --machine-type=<original-type> \
  --node-version=1.31.x-gke.x \
  --num-nodes=<required-count>

# Restore from snapshot if needed
kubectl exec -it <es-pod> -- curl -X POST "localhost:9200/_snapshot/my-backup/pre-upgrade-snapshot/_restore"
```

## Key Considerations

1. **Timing**: Plan for 2-4 hours depending on cluster size
2. **Monitoring**: Keep the monitoring script running throughout
3. **Regional PVs**: Should handle zone changes automatically
4. **ES Quorum**: Never upgrade more than 1 master node simultaneously
5. **Shard Allocation**: Critical to manage this properly during data node upgrades

Would you like me to elaborate on any of these steps or discuss specific configurations for your node pools?
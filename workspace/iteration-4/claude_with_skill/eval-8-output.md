For a Cassandra ring on GKE Standard with local SSDs, I **strongly recommend surge upgrade** with conservative settings. Here's why and how to configure it:

## Why Surge Over Blue-Green for Cassandra

### Surge advantages for your use case:
- **Cost-effective**: No doubling of expensive local SSD instances
- **Cassandra-friendly**: Rolling replacement aligns with Cassandra's built-in resilience to individual node failures
- **Local SSD compatible**: Blue-green would require complex data migration since local SSDs are ephemeral
- **Simpler orchestration**: Less coordination needed compared to managing two full rings

### Blue-green disadvantages:
- **Data migration complexity**: Local SSDs don't persist across blue-green switches - you'd need to rebuild the entire ring or implement complex streaming
- **Cost**: Temporarily doubles your local SSD compute costs
- **Overkill**: Cassandra's replication already provides the safety blue-green aims for

## Recommended Surge Configuration

Configure conservative surge settings that respect Cassandra's fault tolerance:

```bash
# Configure surge upgrade for Cassandra node pool
gcloud container node-pools update CASSANDRA_NODE_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**Why these settings:**
- `maxSurge=1`: Upgrade one node at a time - conservative for stateful workloads
- `maxUnavailable=0`: Never reduce capacity below original count - maintains quorum safety
- This creates 10 nodes temporarily (9 original + 1 new), then removes 1 old node, maintaining 9 throughout

## Pre-Upgrade Preparation

### 1. Configure Pod Disruption Budget
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: cassandra-pdb
  namespace: cassandra-ns
spec:
  minAvailable: 7  # Maintain quorum for RF=3
  selector:
    matchLabels:
      app: cassandra
```

### 2. Verify Cassandra cluster health
```bash
# Check cluster status before upgrade
kubectl exec -n cassandra-ns cassandra-0 -- nodetool status
# Should show all nodes UN (Up Normal)

# Verify replication factor
kubectl exec -n cassandra-ns cassandra-0 -- nodetool describecluster
```

### 3. Backup considerations
```bash
# Take snapshots before upgrade (recommended for peace of mind)
kubectl exec -n cassandra-ns cassandra-0 -- nodetool snapshot
```

## Upgrade Process

### 1. Set maintenance window (optional but recommended)
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-27T02:00:00Z" \
  --maintenance-window-end "2024-01-27T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### 2. Execute the upgrade
```bash
# Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION

# Then upgrade the Cassandra node pool
gcloud container node-pools upgrade CASSANDRA_NODE_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

### 3. Monitor progress
```bash
# Watch nodes cycling
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=CASSANDRA_NODE_POOL'

# Monitor Cassandra cluster health during upgrade
watch 'kubectl exec -n cassandra-ns cassandra-0 -- nodetool status'
```

## What to Expect During Upgrade

1. **Node-by-node replacement**: GKE creates 1 new node, drains 1 old node, repeats
2. **Cassandra behavior**: Each pod restart triggers:
   - Graceful shutdown (respects `terminationGracePeriodSeconds`)
   - Pod reschedules to new node
   - Cassandra rejoins ring and streams missed data
3. **Duration**: ~45-60 minutes for 9 nodes (5-7 minutes per node cycle)

## Troubleshooting Cassandra-Specific Issues

### If a Cassandra pod won't terminate:
```bash
# Check if Cassandra is stuck in shutdown
kubectl logs -n cassandra-ns POD_NAME -c cassandra --tail=50

# Force termination if needed (use sparingly)
kubectl delete pod POD_NAME -n cassandra-ns --grace-period=0 --force
```

### If cluster becomes unhealthy during upgrade:
```bash
# Check ring status
kubectl exec -n cassandra-ns cassandra-0 -- nodetool status

# Look for nodes in DN (Down Normal) state - this is expected during upgrades
# UJ (Up Joining) or UL (Up Leaving) states are also normal during transitions
```

## Alternative: Faster Surge for Larger Rings

If you have confidence in your Cassandra setup and want faster upgrades:

```bash
# More aggressive settings for experienced teams
gcloud container node-pools update CASSANDRA_NODE_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

This upgrades 2 nodes simultaneously but requires ensuring your replication factor can handle 2 concurrent node failures.

**Bottom line**: Surge upgrade is the right choice for Cassandra on GKE. The conservative 1-node-at-a-time approach respects Cassandra's distributed nature while avoiding the complexity and cost of blue-green for stateful workloads.
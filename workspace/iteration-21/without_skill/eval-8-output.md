For a Cassandra ring with 9 nodes using local SSDs, I strongly recommend **Blue-Green upgrade** over surge upgrade. Here's why and how to configure it:

## Why Blue-Green for Cassandra?

### Problems with Surge Upgrade for Cassandra:
- **Data locality loss**: Local SSDs are ephemeral and lost when nodes are recreated
- **Replication factor risk**: With RF=3, losing multiple nodes simultaneously during surge can cause data unavailability
- **Network partition risk**: Rapid node replacement can trigger split-brain scenarios
- **Bootstrap overhead**: New nodes joining mid-upgrade consume significant bandwidth for data streaming

### Benefits of Blue-Green:
- **Controlled transition**: Complete cluster migration with full data replication
- **Zero data loss**: Existing data remains intact during transition
- **Rollback capability**: Can revert to original cluster if issues arise
- **Predictable timeline**: No dependency on Cassandra's bootstrap process

## Recommended Blue-Green Configuration

### Step 1: Create the Green Node Pool
```yaml
# green-nodepool.yaml
apiVersion: container.gke.io/v1beta1
kind: NodePool
metadata:
  name: cassandra-green
  namespace: default
spec:
  cluster: your-cluster-name
  nodeCount: 9
  config:
    machineType: n2-highmem-16  # Adjust based on your current specs
    diskSizeGb: 100
    localSsdCount: 2  # Match your current local SSD configuration
    preemptible: false
    labels:
      node-pool: cassandra-green
      cassandra-cluster: main
    taints:
    - key: "cassandra-green"
      value: "true"
      effect: "NoSchedule"
  locations:
  - us-central1-a
  - us-central1-b
  - us-central1-c
  management:
    autoUpgrade: false
    autoRepair: true
```

### Step 2: Update Cassandra StatefulSet for Green Deployment
```yaml
# cassandra-green-statefulset.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: cassandra-green
spec:
  serviceName: cassandra-green-headless
  replicas: 9
  selector:
    matchLabels:
      app: cassandra
      cluster: green
  template:
    metadata:
      labels:
        app: cassandra
        cluster: green
    spec:
      nodeSelector:
        node-pool: cassandra-green
      tolerations:
      - key: "cassandra-green"
        operator: "Equal"
        value: "true"
        effect: "NoSchedule"
      # Anti-affinity to spread across zones
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
          - labelSelector:
              matchLabels:
                app: cassandra
            topologyKey: kubernetes.io/hostname
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              labelSelector:
                matchLabels:
                  app: cassandra
              topologyKey: topology.kubernetes.io/zone
      containers:
      - name: cassandra
        image: cassandra:4.0  # Your updated version
        env:
        - name: CASSANDRA_SEEDS
          value: "cassandra-green-0.cassandra-green-headless.default.svc.cluster.local,cassandra-green-1.cassandra-green-headless.default.svc.cluster.local"
        - name: CASSANDRA_CLUSTER_NAME
          value: "MainCluster"
        - name: CASSANDRA_ENDPOINT_SNITCH
          value: "GossipingPropertyFileSnitch"
        volumeMounts:
        - name: cassandra-data
          mountPath: /var/lib/cassandra
        - name: cassandra-logs
          mountPath: /var/log/cassandra
      volumes:
      - name: cassandra-data
        hostPath:
          path: /mnt/disks/ssd0/cassandra-data
      - name: cassandra-logs
        hostPath:
          path: /mnt/disks/ssd0/cassandra-logs
```

### Step 3: Migration Script
```bash
#!/bin/bash
# cassandra-blue-green-migration.sh

set -e

BLUE_CLUSTER="cassandra"
GREEN_CLUSTER="cassandra-green"
KEYSPACES="your_keyspace1 your_keyspace2"  # List your keyspaces

echo "Starting Cassandra Blue-Green Migration..."

# Step 1: Deploy green cluster
echo "1. Deploying green node pool..."
kubectl apply -f green-nodepool.yaml

# Wait for nodes to be ready
echo "Waiting for green nodes to be ready..."
kubectl wait --for=condition=Ready nodes -l node-pool=cassandra-green --timeout=600s

# Step 2: Deploy green Cassandra cluster
echo "2. Deploying green Cassandra cluster..."
kubectl apply -f cassandra-green-statefulset.yaml

# Wait for green cluster to be ready
echo "Waiting for green Cassandra cluster..."
kubectl wait --for=condition=Ready pod -l cluster=green --timeout=1800s

# Step 3: Wait for green cluster to form ring
echo "3. Waiting for green cluster ring formation..."
sleep 300

# Verify green cluster health
kubectl exec cassandra-green-0 -- nodetool status

# Step 4: Backup data from blue cluster
echo "4. Creating backup from blue cluster..."
for keyspace in $KEYSPACES; do
    echo "Backing up keyspace: $keyspace"
    kubectl exec cassandra-0 -- nodetool snapshot $keyspace
done

# Step 5: Restore data to green cluster
echo "5. Restoring data to green cluster..."
# This is a simplified example - you'll need to copy snapshot data
# In practice, you might use Cassandra's sstableloader or restore from external backup

# Step 6: Verify data consistency
echo "6. Verifying data consistency..."
# Add your data verification logic here

# Step 7: Update service to point to green cluster
echo "7. Switching traffic to green cluster..."
kubectl patch service cassandra-service -p '{"spec":{"selector":{"cluster":"green"}}}'

# Step 8: Monitor for issues
echo "8. Monitoring new cluster..."
sleep 600

# Verify cluster health
kubectl exec cassandra-green-0 -- nodetool status

echo "Migration completed successfully!"
echo "Blue cluster is still running. Remove it manually after confirming green cluster stability."
```

### Step 4: Monitoring and Validation
```bash
# health-check.sh
#!/bin/bash

GREEN_POD="cassandra-green-0"

echo "Checking green cluster health..."

# Check cluster status
kubectl exec $GREEN_POD -- nodetool status

# Check data consistency
kubectl exec $GREEN_POD -- nodetool repair --full

# Verify keyspace data
kubectl exec $GREEN_POD -- cqlsh -e "SELECT count(*) FROM your_keyspace.your_table;"

# Check application connectivity
# Add your application-specific health checks here
```

## Migration Timeline

1. **Preparation** (30 minutes): Deploy green node pool and wait for nodes
2. **Deployment** (45 minutes): Deploy green Cassandra cluster and wait for ring formation
3. **Data Migration** (2-4 hours): Depends on data size and backup/restore method
4. **Verification** (30 minutes): Validate data integrity and cluster health
5. **Traffic Switch** (15 minutes): Update services and monitor
6. **Cleanup** (Next day): Remove blue cluster after 24h stability confirmation

## Rollback Plan

If issues arise:
```bash
# Quick rollback - switch service back to blue
kubectl patch service cassandra-service -p '{"spec":{"selector":{"cluster":"blue"}}}'
```

This approach gives you maximum control and safety for your stateful Cassandra workload while ensuring zero data loss during the upgrade process.
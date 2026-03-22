For a Cassandra ring with 9 nodes using local SSDs, I strongly recommend **blue-green upgrade** over surge upgrade. Here's why and how to configure it:

## Why Blue-Green for Cassandra?

### Problems with Surge Upgrade for Cassandra:
- **Data loss risk**: Local SSDs are ephemeral - data is lost when nodes are terminated
- **Replication factor concerns**: With RF=3, losing multiple nodes simultaneously during surge can cause data unavailability
- **Cluster instability**: Rapid node changes can trigger unnecessary repairs and affect performance
- **Resource constraints**: Surge requires extra capacity that may not be available

### Benefits of Blue-Green:
- **Controlled migration**: Move one node at a time with proper data streaming
- **No data loss**: Allows for graceful handoff of data between old and new nodes
- **Cluster stability**: Maintains cluster health throughout the upgrade
- **Rollback capability**: Can abort and return to original pool if issues arise

## Configuration

### 1. Create the Blue-Green Node Pool

```yaml
# blue-green-nodepool.yaml
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerNodePool
metadata:
  name: cassandra-blue-green
spec:
  location: us-central1
  cluster: your-cluster-name
  initialNodeCount: 9
  
  nodeConfig:
    machineType: n2-highmem-8  # Adjust based on your current specs
    diskSizeGb: 100
    diskType: pd-ssd
    
    # Local SSDs
    localSsdCount: 1  # Adjust based on your current setup
    
    labels:
      workload: cassandra
      pool-version: blue-green-v2
    
    taints:
    - key: cassandra
      value: "true"
      effect: NO_SCHEDULE
      
    oauth_scopes:
    - https://www.googleapis.com/auth/devstorage.read_only
    - https://www.googleapis.com/auth/logging.write
    - https://www.googleapis.com/auth/monitoring
    - https://www.googleapis.com/auth/servicecontrol
    - https://www.googleapis.com/auth/service.management.readonly
    - https://www.googleapis.com/auth/trace.append

  upgradeSettings:
    maxSurge: 0
    maxUnavailable: 1
    strategy: BLUE_GREEN
    
  management:
    autoUpgrade: false
    autoRepair: true
```

### 2. Apply the Configuration

```bash
# Create the new node pool
kubectl apply -f blue-green-nodepool.yaml

# Or using gcloud
gcloud container node-pools create cassandra-blue-green \
    --cluster=your-cluster-name \
    --zone=us-central1 \
    --num-nodes=9 \
    --machine-type=n2-highmem-8 \
    --disk-size=100 \
    --disk-type=pd-ssd \
    --local-ssd-count=1 \
    --node-labels=workload=cassandra,pool-version=blue-green-v2 \
    --node-taints=cassandra=true:NoSchedule \
    --enable-autorepair \
    --no-enable-autoupgrade \
    --max-surge=0 \
    --max-unavailable=1
```

### 3. Migration Script for Cassandra

```bash
#!/bin/bash
# cassandra-blue-green-migration.sh

OLD_POOL="cassandra-original"
NEW_POOL="cassandra-blue-green" 
NAMESPACE="cassandra"

# Function to wait for node readiness
wait_for_node_ready() {
    local node=$1
    echo "Waiting for node $node to be ready..."
    kubectl wait --for=condition=Ready node/$node --timeout=300s
}

# Function to migrate one Cassandra pod
migrate_cassandra_pod() {
    local pod_name=$1
    local old_node=$2
    local new_node=$3
    
    echo "Migrating $pod_name from $old_node to $new_node"
    
    # 1. Cordon old node
    kubectl cordon $old_node
    
    # 2. Update pod to schedule on new node
    kubectl patch sts cassandra-sts -p '{"spec":{"template":{"spec":{"nodeSelector":{"kubernetes.io/hostname":"'$new_node'"}}}}}'
    
    # 3. Delete the pod (StatefulSet will recreate)
    kubectl delete pod $pod_name -n $NAMESPACE
    
    # 4. Wait for pod to be running on new node
    kubectl wait --for=condition=Ready pod/$pod_name -n $NAMESPACE --timeout=600s
    
    # 5. Wait for Cassandra to join cluster and stream data
    echo "Waiting for Cassandra node to complete bootstrap..."
    kubectl exec $pod_name -n $NAMESPACE -- nodetool status
    
    # Wait for UN (Up Normal) status
    while ! kubectl exec $pod_name -n $NAMESPACE -- nodetool status | grep -q "UN.*$(kubectl get pod $pod_name -n $NAMESPACE -o jsonpath='{.status.podIP}')"; do
        echo "Waiting for node to become UN (Up Normal)..."
        sleep 30
    done
    
    echo "Migration of $pod_name completed successfully"
}

# Get list of old and new nodes
OLD_NODES=($(kubectl get nodes -l cloud.google.com/gke-nodepool=$OLD_POOL -o jsonpath='{.items[*].metadata.name}'))
NEW_NODES=($(kubectl get nodes -l cloud.google.com/gke-nodepool=$NEW_POOL -o jsonpath='{.items[*].metadata.name}'))

# Migrate pods one by one
for i in "${!OLD_NODES[@]}"; do
    OLD_NODE=${OLD_NODES[$i]}
    NEW_NODE=${NEW_NODES[$i]}
    
    # Get pod on old node
    POD=$(kubectl get pods -n $NAMESPACE -o wide | grep $OLD_NODE | awk '{print $1}')
    
    if [ ! -z "$POD" ]; then
        migrate_cassandra_pod $POD $OLD_NODE $NEW_NODE
        
        # Wait between migrations to ensure cluster stability
        echo "Waiting 60 seconds before next migration..."
        sleep 60
    fi
done

echo "All Cassandra pods migrated successfully!"
```

### 4. Post-Migration Verification

```bash
# Verify all nodes are in the new pool
kubectl get pods -n cassandra -o wide

# Check Cassandra cluster status
kubectl exec cassandra-0 -n cassandra -- nodetool status

# Verify data consistency
kubectl exec cassandra-0 -n cassandra -- nodetool repair

# Clean up old node pool
gcloud container node-pools delete $OLD_POOL --cluster=your-cluster-name --zone=us-central1
```

## Key Considerations

1. **Backup First**: Always backup your Cassandra data before migration
2. **Monitor Closely**: Watch cluster health during each node migration
3. **Timing**: Perform during low-traffic periods
4. **Resource Monitoring**: Ensure sufficient cluster resources during migration
5. **Rollback Plan**: Keep old pool until migration is fully verified

This approach ensures zero data loss and maintains Cassandra cluster integrity throughout the upgrade process.
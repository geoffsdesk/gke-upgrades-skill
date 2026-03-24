For a Cassandra ring with 9 nodes using local SSDs, I strongly recommend **blue-green upgrade** over surge upgrade. Here's why and how to configure it:

## Why Blue-Green is Better for Your Use Case

### Problems with Surge Upgrade for Cassandra:
- **Data Loss Risk**: Local SSDs are ephemeral - when old nodes are terminated, all local data is lost
- **Replication Chaos**: New nodes joining simultaneously can overwhelm the gossip protocol
- **Split-Brain Risk**: During overlap period, you might have nodes with inconsistent cluster state
- **Resource Waste**: Running 18 nodes temporarily (9 old + 9 new) during upgrade

### Benefits of Blue-Green for Cassandra:
- **Controlled Migration**: Systematic data transfer between pools
- **Data Preservation**: Proper time for data streaming/repair
- **Validation Window**: Test new pool before cutting over
- **Clean Separation**: No cluster state confusion

## Recommended Configuration

### 1. Create Blue-Green Node Pool Configuration

```yaml
# blue-green-nodepool.yaml
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerNodePool
metadata:
  name: cassandra-pool-v2
spec:
  cluster: your-cluster-name
  location: your-cluster-location
  
  # Blue-green specific settings
  upgradeSettings:
    strategy: BLUE_GREEN
    blueGreenSettings:
      standardRolloutPolicy:
        batchPercentage: 33.33  # Upgrade ~3 nodes at a time
        batchSoakDuration: "300s"  # 5 min soak between batches
      nodePoolSoakDuration: "1800s"  # 30 min to validate before finalizing
  
  nodeConfig:
    machineType: n2-standard-8  # Adjust as needed
    diskType: pd-ssd
    diskSizeGb: 100
    
    # Local SSD configuration
    localSsdCount: 2  # Adjust based on your storage needs
    
    # Cassandra-optimized settings
    metadata:
      disable-legacy-endpoints: "true"
    
    labels:
      workload: cassandra
      pool-version: v2
    
    taints:
    - key: cassandra
      value: "true"
      effect: NO_SCHEDULE
```

### 2. Cassandra StatefulSet Configuration

```yaml
# cassandra-statefulset.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: cassandra
spec:
  serviceName: cassandra-headless
  replicas: 9
  selector:
    matchLabels:
      app: cassandra
  
  template:
    metadata:
      labels:
        app: cassandra
    spec:
      # Node selection for blue-green
      nodeSelector:
        workload: cassandra
      
      tolerations:
      - key: cassandra
        value: "true"
        effect: NoSchedule
      
      # Anti-affinity to spread across nodes
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
          - labelSelector:
              matchLabels:
                app: cassandra
            topologyKey: kubernetes.io/hostname
      
      containers:
      - name: cassandra
        image: cassandra:4.0
        ports:
        - containerPort: 7000
          name: intra-node
        - containerPort: 7199
          name: jmx
        - containerPort: 9042
          name: cql
        
        volumeMounts:
        - name: cassandra-data
          mountPath: /var/lib/cassandra
        
        env:
        - name: CASSANDRA_CLUSTER_NAME
          value: "MyCluster"
        - name: CASSANDRA_SEEDS
          value: cassandra-0.cassandra-headless,cassandra-1.cassandra-headless,cassandra-2.cassandra-headless
      
      # Use local SSD
      volumes:
      - name: cassandra-data
        hostPath:
          path: /mnt/disks/ssd0/cassandra
          type: DirectoryOrCreate
      
      # Initialize local SSD
      initContainers:
      - name: setup-local-ssd
        image: alpine:latest
        command:
        - sh
        - -c
        - |
          mkdir -p /mnt/disks/ssd0/cassandra
          chown -R 999:999 /mnt/disks/ssd0/cassandra
        volumeMounts:
        - name: cassandra-data
          mountPath: /var/lib/cassandra
        securityContext:
          runAsUser: 0
```

### 3. Upgrade Process Script

```bash
#!/bin/bash
# cassandra-blue-green-upgrade.sh

set -e

CLUSTER_NAME="your-cluster"
ZONE="your-zone"
OLD_POOL="cassandra-pool-v1" 
NEW_POOL="cassandra-pool-v2"

echo "Starting Cassandra blue-green upgrade..."

# 1. Create new node pool
echo "Creating new node pool..."
kubectl apply -f blue-green-nodepool.yaml

# Wait for new pool to be ready
echo "Waiting for new node pool to be ready..."
kubectl wait --for=condition=Ready nodes -l cloud.google.com/gke-nodepool=$NEW_POOL --timeout=600s

# 2. Cordon old nodes to prevent new pods
echo "Cordoning old nodes..."
kubectl cordon -l cloud.google.com/gke-nodepool=$OLD_POOL

# 3. Scale up Cassandra on new nodes (one by one)
echo "Starting controlled migration..."

for i in {0..8}; do
    echo "Migrating cassandra-$i..."
    
    # Delete pod to trigger rescheduling on new node
    kubectl delete pod cassandra-$i
    
    # Wait for pod to be ready on new node
    kubectl wait --for=condition=Ready pod/cassandra-$i --timeout=600s
    
    # Wait for Cassandra node to join cluster
    kubectl exec cassandra-$i -- nodetool status | grep -q "UN.*$(kubectl get pod cassandra-$i -o jsonpath='{.status.podIP}')"
    
    echo "cassandra-$i successfully migrated and joined cluster"
    
    # Brief pause between migrations
    sleep 30
done

# 4. Verify cluster health
echo "Verifying cluster health..."
kubectl exec cassandra-0 -- nodetool status
kubectl exec cassandra-0 -- nodetool ring

# 5. Run repair to ensure data consistency
echo "Running cluster repair..."
for i in {0..8}; do
    kubectl exec cassandra-$i -- nodetool repair &
done
wait

# 6. Final verification
echo "Final cluster verification..."
kubectl exec cassandra-0 -- nodetool status | grep -c "UN" | grep -q "9"

if [ $? -eq 0 ]; then
    echo "All 9 nodes are Up and Normal. Migration successful!"
    
    # 7. Clean up old node pool
    echo "Cleaning up old node pool..."
    gcloud container node-pools delete $OLD_POOL \
        --cluster=$CLUSTER_NAME \
        --zone=$ZONE \
        --quiet
    
    echo "Blue-green upgrade completed successfully!"
else
    echo "ERROR: Not all nodes are healthy. Please investigate before proceeding."
    exit 1
fi
```

### 4. Monitoring During Upgrade

```bash
# Monitor cluster status
kubectl exec -it cassandra-0 -- watch nodetool status

# Monitor pod distribution
kubectl get pods -o wide -l app=cassandra

# Check node pool status
kubectl get nodes -l cloud.google.com/gke-nodepool --show-labels

# Monitor data streaming
kubectl exec cassandra-0 -- nodetool netstats
```

## Key Considerations

1. **Backup First**: Always backup your data before starting
2. **Test Process**: Run this on a staging environment first
3. **Monitor Resources**: Ensure adequate CPU/memory during repair operations
4. **Timing**: Plan for 2-4 hours depending on data size
5. **Rollback Plan**: Keep old pool until you verify everything works

This approach ensures data safety and provides a clean upgrade path for your Cassandra cluster while leveraging GKE's blue-green capabilities.
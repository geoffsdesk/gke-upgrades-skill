For a Cassandra ring with 9 nodes using local SSDs, I **strongly recommend Blue-Green upgrade** over Surge upgrade. Here's why and how to configure it:

## Why Blue-Green for Cassandra?

### Problems with Surge Upgrade:
- **Data Loss Risk**: Local SSDs are ephemeral - when old nodes are terminated, all local data is lost
- **Replication Stress**: Cassandra would need to replicate data to new nodes while old nodes are being destroyed
- **Unpredictable Timing**: You can't control when nodes are replaced, making it hard to ensure data consistency

### Benefits of Blue-Green:
- **Controlled Migration**: You manage the data migration process
- **Zero Data Loss**: Migrate data before terminating old nodes
- **Validation Window**: Test the new cluster before switching traffic
- **Rollback Safety**: Keep old cluster until you're confident

## Recommended Blue-Green Configuration

### Step 1: Prepare the Green Node Pool

```yaml
# green-nodepool.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: cassandra-green-config
data:
  create-green-pool.sh: |
    #!/bin/bash
    
    # Create new node pool with updated Kubernetes version
    gcloud container node-pools create cassandra-green \
      --cluster=your-cluster-name \
      --zone=your-zone \
      --machine-type=n1-standard-8 \
      --num-nodes=9 \
      --local-ssd-count=1 \
      --node-version=1.28.3-gke.1286000 \
      --node-labels=cassandra-pool=green,workload=cassandra \
      --node-taints=cassandra=green:NoSchedule \
      --disk-size=100GB \
      --preemptible=false
```

### Step 2: Cassandra StatefulSet for Green Pool

```yaml
# cassandra-green-statefulset.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: cassandra-green
spec:
  serviceName: cassandra-green
  replicas: 9
  selector:
    matchLabels:
      app: cassandra-green
  template:
    metadata:
      labels:
        app: cassandra-green
        pool: green
    spec:
      nodeSelector:
        cassandra-pool: green
      tolerations:
      - key: cassandra
        value: green
        effect: NoSchedule
      containers:
      - name: cassandra
        image: cassandra:4.0
        ports:
        - containerPort: 7000
          name: intra-node
        - containerPort: 7001
          name: tls-intra-node
        - containerPort: 7199
          name: jmx
        - containerPort: 9042
          name: cql
        env:
        - name: CASSANDRA_SEEDS
          value: "cassandra-green-0.cassandra-green,cassandra-green-1.cassandra-green,cassandra-green-2.cassandra-green"
        - name: CASSANDRA_CLUSTER_NAME
          value: "CassandraCluster"
        - name: CASSANDRA_DC
          value: "DC1"
        - name: CASSANDRA_RACK
          value: "Rack1"
        volumeMounts:
        - name: cassandra-data
          mountPath: /var/lib/cassandra
        resources:
          requests:
            cpu: 2
            memory: 8Gi
          limits:
            cpu: 4
            memory: 16Gi
      volumes:
      - name: cassandra-data
        hostPath:
          path: /mnt/disks/ssd0
          type: Directory
---
apiVersion: v1
kind: Service
metadata:
  name: cassandra-green
spec:
  clusterIP: None
  selector:
    app: cassandra-green
  ports:
  - port: 9042
    name: cql
```

### Step 3: Migration Script

```bash
#!/bin/bash
# cassandra-blue-green-migration.sh

set -e

echo "=== Cassandra Blue-Green Migration ==="

# Step 1: Create green node pool
echo "Creating green node pool..."
gcloud container node-pools create cassandra-green \
  --cluster=your-cluster-name \
  --zone=your-zone \
  --machine-type=n1-standard-8 \
  --num-nodes=9 \
  --local-ssd-count=1 \
  --node-version=1.28.3-gke.1286000 \
  --node-labels=cassandra-pool=green \
  --disk-size=100GB

# Step 2: Deploy green Cassandra cluster
echo "Deploying green Cassandra cluster..."
kubectl apply -f cassandra-green-statefulset.yaml

# Step 3: Wait for green cluster to be ready
echo "Waiting for green cluster to be ready..."
kubectl wait --for=condition=ready pod -l app=cassandra-green --timeout=600s

# Step 4: Create snapshot on blue cluster
echo "Creating snapshot on blue cluster..."
kubectl exec -it cassandra-0 -- nodetool snapshot

# Step 5: Copy data from blue to green
echo "Copying data from blue to green..."
for i in {0..8}; do
  echo "Migrating data from cassandra-$i to cassandra-green-$i..."
  
  # Create tar of snapshot data
  kubectl exec cassandra-$i -- tar -czf /tmp/snapshot.tar.gz -C /var/lib/cassandra/data .
  
  # Copy to local
  kubectl cp cassandra-$i:/tmp/snapshot.tar.gz ./snapshot-$i.tar.gz
  
  # Copy to green pod
  kubectl cp ./snapshot-$i.tar.gz cassandra-green-$i:/tmp/snapshot.tar.gz
  
  # Extract on green pod
  kubectl exec cassandra-green-$i -- tar -xzf /tmp/snapshot.tar.gz -C /var/lib/cassandra/data
  
  # Fix permissions
  kubectl exec cassandra-green-$i -- chown -R cassandra:cassandra /var/lib/cassandra/data
  
  # Cleanup
  rm ./snapshot-$i.tar.gz
done

# Step 6: Restart green cluster to load data
echo "Restarting green cluster..."
kubectl rollout restart statefulset/cassandra-green
kubectl rollout status statefulset/cassandra-green

# Step 7: Verify green cluster
echo "Verifying green cluster..."
kubectl exec -it cassandra-green-0 -- nodetool status

echo "=== Verification Commands ==="
echo "Check cluster status: kubectl exec -it cassandra-green-0 -- nodetool status"
echo "Check data: kubectl exec -it cassandra-green-0 -- cqlsh -e 'DESCRIBE KEYSPACES;'"
echo "After verification, update your application to use cassandra-green service"
```

### Step 4: Application Update

```yaml
# Update your application configuration
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
data:
  cassandra-hosts: "cassandra-green-0.cassandra-green,cassandra-green-1.cassandra-green,cassandra-green-2.cassandra-green"
  # Update service reference
  cassandra-service: "cassandra-green"
```

### Step 5: Cleanup Script

```bash
#!/bin/bash
# cleanup-blue-cluster.sh

echo "=== Cleanup Blue Cluster ==="
echo "WARNING: This will delete the old cluster. Ensure green cluster is working!"
read -p "Are you sure? (yes/no): " confirm

if [[ $confirm == "yes" ]]; then
  # Delete blue StatefulSet and service
  kubectl delete statefulset cassandra
  kubectl delete service cassandra
  
  # Delete blue node pool
  gcloud container node-pools delete cassandra-blue --cluster=your-cluster-name --zone=your-zone
  
  echo "Blue cluster deleted successfully"
else
  echo "Cleanup cancelled"
fi
```

## Migration Checklist

1. **Pre-migration**:
   - [ ] Backup current data
   - [ ] Test migration in staging
   - [ ] Plan maintenance window
   - [ ] Notify stakeholders

2. **During migration**:
   - [ ] Create green node pool
   - [ ] Deploy green Cassandra
   - [ ] Migrate data using snapshots
   - [ ] Verify data integrity
   - [ ] Update application configs

3. **Post-migration**:
   - [ ] Monitor green cluster
   - [ ] Validate application performance
   - [ ] Keep blue cluster for rollback window
   - [ ] Clean up blue cluster after confirmation

This approach gives you complete control over the migration process and ensures no data loss with your local SSD setup.
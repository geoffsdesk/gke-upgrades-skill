For your Cassandra ring with 9 nodes using local SSDs, I strongly recommend **Blue-Green upgrade** over surge upgrade. Here's why and how to configure it:

## Why Blue-Green is Better for Your Use Case

### Problems with Surge Upgrade for Cassandra:
- **Data Loss Risk**: Local SSDs are ephemeral - when old nodes terminate, all data is lost
- **Replication Overhead**: Cassandra would need to replicate data to new nodes, then lose original data
- **Cluster Instability**: Mixed node versions during rolling upgrades can cause issues
- **Resource Waste**: You'd pay for extra nodes during the upgrade period

### Blue-Green Advantages:
- **Data Preservation**: Controlled migration of data between environments
- **Atomic Rollback**: Can quickly switch back if issues occur
- **Validation Window**: Test the new environment before switching traffic
- **Predictable Downtime**: Plan maintenance windows appropriately

## Recommended Blue-Green Configuration

Here's how to set up blue-green upgrades for your Cassandra cluster:

### 1. Configure the Node Pool with Blue-Green

```yaml
# cassandra-nodepool.yaml
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerNodePool
metadata:
  name: cassandra-nodepool
spec:
  location: us-central1-a
  cluster: your-cluster-name
  initialNodeCount: 9
  
  upgradeSettings:
    strategy: BLUE_GREEN
    blueGreenSettings:
      # Time to wait before draining nodes (for data migration)
      nodePoolSoakDuration: "3600s"  # 1 hour
      
      # How long to wait for pods to terminate gracefully
      standardRolloutPolicy:
        batchSoakDuration: "300s"  # 5 minutes
        batchNodeCount: 3  # Upgrade 3 nodes at a time
        batchPercentage: null

  nodeConfig:
    machineType: n2-standard-8
    diskSizeGb: 100
    diskType: pd-ssd
    
    # Local SSDs for Cassandra data
    localSsdCount: 2
    
    # Preemptible: false for production Cassandra
    preemptible: false
    
    labels:
      workload-type: cassandra
      
    taints:
    - key: cassandra-only
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
      # Ensure pods only run on Cassandra nodes
      tolerations:
      - key: cassandra-only
        operator: Equal
        value: "true"
        effect: NoSchedule
        
      nodeSelector:
        workload-type: cassandra
        
      # Critical: Allow time for proper shutdown
      terminationGracePeriodSeconds: 1800  # 30 minutes
      
      containers:
      - name: cassandra
        image: cassandra:4.0
        
        # Proper shutdown handling
        lifecycle:
          preStop:
            exec:
              command:
              - /bin/bash
              - -c
              - |
                # Drain the node before shutdown
                nodetool drain
                # Wait for drain to complete
                sleep 30
        
        # Resource requests/limits
        resources:
          requests:
            cpu: 2
            memory: 8Gi
          limits:
            cpu: 4
            memory: 16Gi
            
        # Mount local SSDs
        volumeMounts:
        - name: cassandra-data
          mountPath: /var/lib/cassandra
          
        # Readiness probe to ensure proper startup
        readinessProbe:
          exec:
            command:
            - /bin/bash
            - -c
            - "nodetool status | grep UN"
          initialDelaySeconds: 60
          periodSeconds: 30
          
      # Use local SSDs
      volumes:
      - name: cassandra-data
        hostPath:
          path: /mnt/disks/ssd0
          type: Directory
```

### 3. Data Migration Strategy

Create a migration job for blue-green transitions:

```yaml
# cassandra-migration-job.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: cassandra-migration
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
      - name: migration
        image: cassandra:4.0
        command:
        - /bin/bash
        - -c
        - |
          # Script to handle data migration between blue/green environments
          
          # 1. Create snapshot on old cluster
          OLD_CLUSTER_IPS="10.1.1.1,10.1.1.2,10.1.1.3"  # Blue cluster
          NEW_CLUSTER_IPS="10.1.2.1,10.1.2.2,10.1.2.3"  # Green cluster
          
          echo "Creating snapshot on old cluster..."
          cqlsh -e "CREATE SNAPSHOT backup_$(date +%Y%m%d_%H%M%S)" $OLD_CLUSTER_IPS
          
          # 2. Copy data to new cluster (you'll need to implement based on your backup strategy)
          echo "Restoring data to new cluster..."
          # Your restore logic here
          
          # 3. Verify data integrity
          echo "Verifying data integrity..."
          # Your verification logic here
```

### 4. Upgrade Process

```bash
#!/bin/bash
# upgrade-cassandra-cluster.sh

set -e

echo "Starting Blue-Green upgrade for Cassandra cluster..."

# 1. Create snapshot before upgrade
kubectl exec cassandra-0 -- nodetool snapshot

# 2. Trigger the upgrade
gcloud container node-pools upgrade cassandra-nodepool \
  --cluster=your-cluster-name \
  --zone=us-central1-a \
  --node-version=1.28.3-gke.1286000

# 3. Monitor the upgrade
echo "Monitoring upgrade progress..."
while true; do
  STATUS=$(gcloud container operations list --filter="status=RUNNING" --format="value(status)")
  if [[ -z "$STATUS" ]]; then
    echo "Upgrade completed!"
    break
  fi
  echo "Upgrade in progress..."
  sleep 30
done

# 4. Verify cluster health
echo "Verifying Cassandra cluster health..."
kubectl exec cassandra-0 -- nodetool status

echo "Blue-Green upgrade completed successfully!"
```

## Key Configuration Points

1. **Soak Duration**: Set to 3600s (1 hour) to allow time for data migration
2. **Grace Period**: 30 minutes for proper Cassandra shutdown
3. **PreStop Hook**: Ensures `nodetool drain` before termination
4. **Readiness Probe**: Confirms nodes are properly joined to cluster
5. **Resource Limits**: Prevent resource contention during transitions

## Monitoring During Upgrades

```yaml
# cassandra-monitoring.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: upgrade-monitoring
data:
  monitor.sh: |
    #!/bin/bash
    
    # Monitor Cassandra cluster health during upgrade
    while true; do
      echo "=== Cluster Status ==="
      kubectl exec cassandra-0 -- nodetool status
      
      echo "=== Ring Status ==="
      kubectl exec cassandra-0 -- nodetool ring
      
      echo "=== Pending Tasks ==="
      kubectl exec cassandra-0 -- nodetool compactionstats
      
      sleep 60
    done
```

This blue-green approach ensures your Cassandra data remains safe while providing a reliable upgrade path with the ability to rollback if needed.
For your Cassandra ring with 9 nodes using local SSDs, I **strongly recommend blue-green upgrade** over surge upgrade. Here's why and how to configure it:

## Why Blue-Green is Better for Your Use Case

### Problems with Surge Upgrade for Cassandra:
- **Data loss risk**: Local SSDs are ephemeral and lost when nodes are replaced
- **Replication factor conflicts**: If you have RF=3, surge might temporarily create too many replicas in one zone
- **Bootstrap storms**: New nodes joining simultaneously can overwhelm the cluster
- **Split-brain risk**: Temporary network partitions during rolling updates

### Benefits of Blue-Green for Cassandra:
- **Controlled migration**: You manage data transfer and cluster topology
- **No data loss**: Existing nodes remain untouched during upgrade
- **Validation opportunity**: Test the new cluster before switching traffic
- **Rollback capability**: Easy to revert if issues arise

## Configuration and Implementation

### 1. Current Cluster Setup (Blue Environment)

```yaml
# current-cassandra-nodepool.yaml
apiVersion: container.gke.io/v1beta1
kind: NodePool
metadata:
  name: cassandra-blue
  namespace: default
spec:
  cluster: your-cluster-name
  nodeCount: 9
  config:
    machineType: n2-highmem-4
    diskType: pd-ssd
    diskSizeGb: 100
    localSsdCount: 1
    labels:
      workload: cassandra
      environment: blue
    taints:
    - key: cassandra
      value: "true"
      effect: NO_SCHEDULE
```

### 2. Create Green Environment

```bash
# Create new node pool with upgraded Kubernetes version
gcloud container node-pools create cassandra-green \
    --cluster=your-cluster-name \
    --zone=your-zone \
    --num-nodes=9 \
    --machine-type=n2-highmem-4 \
    --local-ssd-count=1 \
    --disk-size=100GB \
    --disk-type=pd-ssd \
    --node-labels=workload=cassandra,environment=green \
    --node-taints=cassandra=true:NoSchedule \
    --node-version=TARGET_K8S_VERSION
```

### 3. Cassandra StatefulSet for Green Environment

```yaml
# cassandra-green-statefulset.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: cassandra-green
  labels:
    app: cassandra
    environment: green
spec:
  serviceName: cassandra-green-headless
  replicas: 9
  selector:
    matchLabels:
      app: cassandra
      environment: green
  template:
    metadata:
      labels:
        app: cassandra
        environment: green
    spec:
      nodeSelector:
        environment: green
        workload: cassandra
      tolerations:
      - key: cassandra
        operator: Equal
        value: "true"
        effect: NoSchedule
      containers:
      - name: cassandra
        image: cassandra:4.0
        resources:
          requests:
            memory: 8Gi
            cpu: 2
          limits:
            memory: 12Gi
            cpu: 4
        env:
        - name: CASSANDRA_SEEDS
          value: "cassandra-green-0.cassandra-green-headless.default.svc.cluster.local,cassandra-green-1.cassandra-green-headless.default.svc.cluster.local"
        - name: CASSANDRA_CLUSTER_NAME
          value: "green-cluster"
        - name: CASSANDRA_DC
          value: "dc1"
        - name: CASSANDRA_RACK
          value: "rack1"
        volumeMounts:
        - name: cassandra-data
          mountPath: /var/lib/cassandra
        - name: local-ssd
          mountPath: /var/lib/cassandra/data
      volumes:
      - name: local-ssd
        hostPath:
          path: /mnt/disks/ssd0
  volumeClaimTemplates:
  - metadata:
      name: cassandra-data
    spec:
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 50Gi
```

### 4. Migration Script

```bash
#!/bin/bash
# cassandra-blue-green-migration.sh

set -e

echo "Starting Cassandra Blue-Green Migration..."

# Step 1: Deploy green environment
kubectl apply -f cassandra-green-statefulset.yaml

# Step 2: Wait for green cluster to be ready
echo "Waiting for green cluster to be ready..."
kubectl wait --for=condition=ready pod -l app=cassandra,environment=green --timeout=600s

# Step 3: Create backup of blue cluster
echo "Creating backup of blue cluster..."
kubectl exec cassandra-blue-0 -- nodetool snapshot

# Step 4: Copy data to green cluster (you'll need to implement data migration)
echo "Migrating data to green cluster..."
# This is cluster-specific - you might use:
# - sstableloader for bulk loading
# - Logical backup/restore
# - Custom migration script

# Step 5: Update services to point to green
kubectl patch service cassandra-service -p '{"spec":{"selector":{"environment":"green"}}}'

# Step 6: Verify green cluster
echo "Verifying green cluster..."
kubectl exec cassandra-green-0 -- nodetool status

echo "Migration completed. Monitor the green cluster before removing blue."
```

### 5. Services Configuration

```yaml
# cassandra-services.yaml
apiVersion: v1
kind: Service
metadata:
  name: cassandra-service
spec:
  selector:
    app: cassandra
    environment: blue  # Switch to 'green' during migration
  ports:
  - port: 9042
    name: cql
  - port: 7000
    name: intra-node
---
apiVersion: v1
kind: Service
metadata:
  name: cassandra-green-headless
spec:
  clusterIP: None
  selector:
    app: cassandra
    environment: green
  ports:
  - port: 9042
    name: cql
```

### 6. Migration Checklist

```bash
# Pre-migration checks
□ Verify blue cluster health: nodetool status
□ Check replication factor and consistency
□ Ensure sufficient storage for data migration
□ Plan for application downtime window

# Migration steps
□ Create green node pool
□ Deploy green Cassandra cluster
□ Migrate data (sstableloader, backup/restore, or streaming)
□ Validate data consistency
□ Switch application traffic
□ Monitor green cluster performance

# Post-migration cleanup
□ Run for 24-48 hours in parallel
□ Verify all applications working
□ Remove blue node pool
□ Update monitoring and alerting
```

### 7. Rollback Plan

```bash
# Quick rollback if needed
kubectl patch service cassandra-service -p '{"spec":{"selector":{"environment":"blue"}}}'

# Full rollback
kubectl delete statefulset cassandra-green
gcloud container node-pools delete cassandra-green --cluster=your-cluster-name
```

## Key Considerations

1. **Data Migration**: Plan your data migration strategy (backup/restore, streaming, or sstableloader)
2. **Monitoring**: Implement comprehensive monitoring during migration
3. **Testing**: Validate data integrity and application functionality thoroughly
4. **Timing**: Plan migration during low-traffic periods
5. **Resources**: Ensure you have enough cluster resources to run both environments

This approach gives you maximum control and safety for your critical Cassandra workload while upgrading your Kubernetes nodes.
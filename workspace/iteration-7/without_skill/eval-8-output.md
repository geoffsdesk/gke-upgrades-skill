For a stateful workload like Cassandra with local SSDs, I strongly recommend **Blue-Green upgrade** over surge upgrade. Here's why and how to configure it:

## Why Blue-Green for Cassandra

**Surge upgrade risks:**
- Creates new nodes that must join the Cassandra ring
- Triggers data rebalancing and streaming during upgrade
- Potential split-brain scenarios if nodes are removed too quickly
- Local SSD data loss requires full data restoration

**Blue-Green advantages:**
- Complete isolation between old and new clusters
- Controlled data migration timing
- Ability to validate the new cluster before switching
- Easy rollback capability
- No mid-upgrade ring topology changes

## Recommended Blue-Green Configuration

### 1. Create the New (Green) Node Pool

```yaml
# green-nodepool.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: cassandra-upgrade-config
data:
  upgrade-strategy: "blue-green"
---
# Create new node pool with gcloud CLI
```

```bash
# Create the green node pool
gcloud container node-pools create cassandra-green \
    --cluster=your-cluster-name \
    --zone=your-zone \
    --machine-type=n1-standard-8 \
    --num-nodes=9 \
    --local-ssd-count=2 \
    --node-labels=pool=green,cassandra-role=standby \
    --node-taints=pool=green:NoSchedule \
    --disk-type=pd-ssd \
    --disk-size=100GB \
    --enable-autorepair \
    --enable-autoupgrade=false
```

### 2. Update Cassandra StatefulSet for Blue-Green

```yaml
# cassandra-statefulset-green.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: cassandra-green
spec:
  serviceName: cassandra-green
  replicas: 9
  selector:
    matchLabels:
      app: cassandra
      version: green
  template:
    metadata:
      labels:
        app: cassandra
        version: green
    spec:
      nodeSelector:
        pool: green
      tolerations:
      - key: "pool"
        operator: "Equal"
        value: "green"
        effect: "NoSchedule"
      containers:
      - name: cassandra
        image: cassandra:4.0.7  # Updated version
        ports:
        - containerPort: 7000
          name: intra-node
        - containerPort: 7001
          name: tls-intra-node
        - containerPort: 7199
          name: jmx
        - containerPort: 9042
          name: cql
        resources:
          limits:
            cpu: "6"
            memory: "24Gi"
          requests:
            cpu: "6"
            memory: "24Gi"
        env:
        - name: CASSANDRA_SEEDS
          value: "cassandra-green-0.cassandra-green,cassandra-green-1.cassandra-green"
        - name: CASSANDRA_CLUSTER_NAME
          value: "K8S Demo Cluster Green"
        - name: CASSANDRA_DC
          value: "DC1-K8S"
        - name: CASSANDRA_RACK
          value: "Rack1-K8S"
        - name: POD_IP
          valueFrom:
            fieldRef:
              fieldPath: status.podIP
        volumeMounts:
        - name: cassandra-data
          mountPath: /cassandra_data
  volumeClaimTemplates:
  - metadata:
      name: cassandra-data
    spec:
      accessModes: [ "ReadWriteOnce" ]
      storageClassName: "fast-ssd"
      resources:
        requests:
          storage: 1Ti
```

### 3. Create Green Service

```yaml
# cassandra-service-green.yaml
apiVersion: v1
kind: Service
metadata:
  labels:
    app: cassandra
    version: green
  name: cassandra-green
spec:
  clusterIP: None
  ports:
  - port: 9042
    name: cql
  selector:
    app: cassandra
    version: green
```

## Migration Process

### Phase 1: Deploy Green Cluster
```bash
# Remove taint to allow scheduling
kubectl taint nodes -l pool=green pool=green:NoSchedule-

# Deploy green cluster
kubectl apply -f cassandra-service-green.yaml
kubectl apply -f cassandra-statefulset-green.yaml

# Wait for green cluster to be ready
kubectl wait --for=condition=ready pod -l version=green --timeout=600s
```

### Phase 2: Data Migration Script
```bash
#!/bin/bash
# migrate-cassandra.sh

set -e

echo "Starting Cassandra Blue-Green migration..."

# Verify green cluster health
echo "Checking green cluster status..."
for i in {0..8}; do
    kubectl exec cassandra-green-$i -- nodetool status
done

# Create backup from blue cluster
echo "Creating backup from blue cluster..."
for i in {0..8}; do
    kubectl exec cassandra-blue-$i -- nodetool snapshot
done

# Stream data to green cluster (if using same datacenter)
# Or restore from backup
echo "Migrating data to green cluster..."
# Implementation depends on your backup strategy

# Verify data consistency
echo "Verifying data consistency..."
kubectl exec cassandra-green-0 -- cqlsh -e "SELECT count(*) FROM your_keyspace.your_table;"
```

### Phase 3: Traffic Switch
```yaml
# Switch main service to green
apiVersion: v1
kind: Service
metadata:
  labels:
    app: cassandra
  name: cassandra  # Main service name
spec:
  clusterIP: None
  ports:
  - port: 9042
    name: cql
  selector:
    app: cassandra
    version: green  # Switch from blue to green
```

### Phase 4: Cleanup
```bash
# After validating green cluster
# Scale down blue cluster
kubectl scale statefulset cassandra-blue --replicas=0

# Delete blue node pool
gcloud container node-pools delete cassandra-blue \
    --cluster=your-cluster-name \
    --zone=your-zone
```

## Monitoring and Validation

```yaml
# monitoring-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: migration-monitoring
data:
  validation-script: |
    #!/bin/bash
    # Validate cluster health
    kubectl exec cassandra-green-0 -- nodetool status | grep "UN" | wc -l
    # Should return 9
    
    # Check data consistency
    kubectl exec cassandra-green-0 -- nodetool repair
    
    # Performance test
    kubectl exec cassandra-green-0 -- cassandra-stress write n=10000
```

## Rollback Plan

```bash
# Quick rollback by switching service selector
kubectl patch service cassandra -p '{"spec":{"selector":{"version":"blue"}}}'

# Or use original service configuration
kubectl apply -f cassandra-service-blue-original.yaml
```

This blue-green approach minimizes risk for your stateful Cassandra workload while providing a clear upgrade path and rollback strategy.
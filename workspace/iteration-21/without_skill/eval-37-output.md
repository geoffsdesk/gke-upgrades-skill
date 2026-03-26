# GKE Cluster Upgrade Plan: 1.31 → 1.32
## Mixed AI/ML Platform (5,000 Nodes)

## 🎯 Objectives
- **Primary**: Maintain training continuity (H100 nodes)
- **Secondary**: Ensure inference availability (A100 nodes)
- **Tertiary**: Minimize development disruption (T4 nodes)
- **Support**: Maintain platform services (CPU nodes)

---

## 📋 Pre-Upgrade Preparation

### 1. Assessment & Validation
```bash
# Check current cluster health
kubectl get nodes --show-labels
kubectl get pods --all-namespaces --field-selector=status.phase!=Running

# Validate workload compatibility
kubectl api-versions
kubectl get apiservices

# Check resource utilization
kubectl top nodes
kubectl describe nodes | grep -A 5 "Allocated resources"
```

### 2. Backup & Safety Measures
```yaml
# Create etcd backup
gcloud container clusters backup-create backup-pre-upgrade \
  --cluster=ai-ml-cluster \
  --location=us-central1 \
  --backup-location=gs://backup-bucket/pre-upgrade

# Export critical configurations
kubectl get all --all-namespaces -o yaml > cluster-state-backup.yaml
```

### 3. Node Pool Configuration
```bash
# Verify current node pool setup
gcloud container node-pools list --cluster=ai-ml-cluster --location=us-central1

Expected pools:
- h100-training-pool (2,000 nodes)
- a100-inference-pool (1,500 nodes)  
- t4-dev-pool (500 nodes)
- cpu-services-pool (1,000 nodes)
```

---

## 🚀 Phase 1: Control Plane & CPU Services (Week 1)

### Control Plane Upgrade
```bash
# Upgrade control plane first
gcloud container clusters update ai-ml-cluster \
  --cluster-version=1.32.0-gke.1200 \
  --location=us-central1 \
  --async
```

### CPU Services Node Pool Upgrade
```bash
# Create new CPU node pool
gcloud container node-pools create cpu-services-pool-132 \
  --cluster=ai-ml-cluster \
  --location=us-central1 \
  --machine-type=n2-standard-16 \
  --num-nodes=334 \
  --node-version=1.32.0-gke.1200 \
  --node-taints=services=cpu:NoSchedule \
  --node-labels=workload=services,version=1.32

# Gradual migration script
cat << 'EOF' > migrate-cpu-services.sh
#!/bin/bash
OLD_POOL="cpu-services-pool"
NEW_POOL="cpu-services-pool-132"

# Scale new pool in batches
for batch in {1..3}; do
  echo "Scaling batch $batch"
  new_size=$((batch * 334))
  
  gcloud container node-pools resize $NEW_POOL \
    --cluster=ai-ml-cluster \
    --location=us-central1 \
    --num-nodes=$new_size \
    --async
  
  # Wait for nodes to be ready
  kubectl wait --for=condition=Ready nodes -l cloud.google.com/gke-nodepool=$NEW_POOL --timeout=600s
  
  # Cordon and drain old nodes gradually
  old_nodes=$(kubectl get nodes -l cloud.google.com/gke-nodepool=$OLD_POOL --no-headers | head -334 | awk '{print $1}')
  for node in $old_nodes; do
    kubectl cordon $node
    kubectl drain $node --ignore-daemonsets --delete-emptydir-data --timeout=300s &
  done
  wait
  
  echo "Batch $batch complete. Waiting 30 minutes before next batch..."
  sleep 1800
done
EOF

chmod +x migrate-cpu-services.sh
./migrate-cpu-services.sh
```

### Validation
```bash
# Verify services are running on new nodes
kubectl get pods -n kube-system -o wide
kubectl get pods --all-namespaces --field-selector spec.nodeName!=
```

---

## 🚀 Phase 2: Development Environment (Week 2)

### T4 Development Pool Upgrade
```bash
# Create new T4 development pool
gcloud container node-pools create t4-dev-pool-132 \
  --cluster=ai-ml-cluster \
  --location=us-central1 \
  --machine-type=n1-standard-16 \
  --accelerator=type=nvidia-tesla-t4,count=1 \
  --num-nodes=167 \
  --node-version=1.32.0-gke.1200 \
  --node-taints=development=t4:NoSchedule \
  --node-labels=workload=development,gpu=t4,version=1.32

# Development workload migration
cat << 'EOF' > migrate-dev-workloads.sh
#!/bin/bash
# Schedule maintenance window (e.g., weekends)
echo "Starting T4 development pool migration..."

# Scale new pool
for batch in {1..3}; do
  new_size=$((batch * 167))
  
  gcloud container node-pools resize t4-dev-pool-132 \
    --cluster=ai-ml-cluster \
    --location=us-central1 \
    --num-nodes=$new_size
  
  # Update development deployments to prefer new nodes
  kubectl patch deployment dev-jupyter-hub \
    -p '{"spec":{"template":{"spec":{"nodeSelector":{"version":"1.32"}}}}}'
  
  # Gracefully migrate development pods
  old_nodes=$(kubectl get nodes -l cloud.google.com/gke-nodepool=t4-dev-pool --no-headers | head -167 | awk '{print $1}')
  for node in $old_nodes; do
    kubectl cordon $node
    # Give developers time to save work
    echo "Node $node cordoned. Development teams notified."
  done
  
  sleep 3600  # 1 hour grace period
  
  for node in $old_nodes; do
    kubectl drain $node --ignore-daemonsets --delete-emptydir-data --timeout=600s
  done
  
  echo "Batch $batch complete"
  sleep 7200  # 2 hours between batches
done
EOF

chmod +x migrate-dev-workloads.sh
./migrate-dev-workloads.sh
```

---

## 🚀 Phase 3: Inference Infrastructure (Week 3-4)

### A100 Inference Pool Upgrade Strategy
```bash
# Create multiple smaller A100 pools for rolling upgrade
gcloud container node-pools create a100-inference-pool-132-zone-a \
  --cluster=ai-ml-cluster \
  --location=us-central1 \
  --machine-type=a2-highgpu-1g \
  --accelerator=type=nvidia-tesla-a100,count=1 \
  --num-nodes=500 \
  --node-version=1.32.0-gke.1200 \
  --node-taints=inference=a100:NoSchedule \
  --node-labels=workload=inference,gpu=a100,version=1.32,zone=a

gcloud container node-pools create a100-inference-pool-132-zone-b \
  --cluster=ai-ml-cluster \
  --location=us-central1 \
  --machine-type=a2-highgpu-1g \
  --accelerator=type=nvidia-tesla-a100,count=1 \
  --num-nodes=500 \
  --node-version=1.32.0-gke.1200 \
  --node-taints=inference=a100:NoSchedule \
  --node-labels=workload=inference,gpu=a100,version=1.32,zone=b

gcloud container node-pools create a100-inference-pool-132-zone-c \
  --cluster=ai-ml-cluster \
  --location=us-central1 \
  --machine-type=a2-highgpu-1g \
  --accelerator=type=nvidia-tesla-a100,count=1 \
  --num-nodes=500 \
  --node-version=1.32.0-gke.1200 \
  --node-taints=inference=a100:NoSchedule \
  --node-labels=workload=inference,gpu=a100,version=1.32,zone=c
```

### Inference Service Migration
```yaml
# Update inference deployments for blue-green deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inference-service-v2
spec:
  replicas: 50
  selector:
    matchLabels:
      app: inference-service
      version: v2
  template:
    metadata:
      labels:
        app: inference-service
        version: v2
    spec:
      nodeSelector:
        version: "1.32"
        gpu: "a100"
      tolerations:
      - key: "inference"
        operator: "Equal"
        value: "a100"
        effect: "NoSchedule"
      containers:
      - name: inference-container
        image: your-inference-image:latest
        resources:
          limits:
            nvidia.com/gpu: 1
---
apiVersion: v1
kind: Service
metadata:
  name: inference-service
spec:
  selector:
    app: inference-service
  ports:
  - port: 80
    targetPort: 8080
```

### Zone-by-Zone Migration Script
```bash
cat << 'EOF' > migrate-inference-zones.sh
#!/bin/bash
ZONES=("a" "b" "c")

for zone in "${ZONES[@]}"; do
  echo "Migrating inference zone $zone..."
  
  # Scale up new pool for this zone
  gcloud container node-pools resize a100-inference-pool-132-zone-$zone \
    --cluster=ai-ml-cluster \
    --location=us-central1 \
    --num-nodes=500
  
  # Wait for nodes to be ready
  kubectl wait --for=condition=Ready \
    nodes -l "cloud.google.com/gke-nodepool=a100-inference-pool-132-zone-$zone" \
    --timeout=1200s
  
  # Update service to route traffic to new nodes
  kubectl apply -f inference-service-v2.yaml
  
  # Health check new deployment
  kubectl rollout status deployment/inference-service-v2 --timeout=600s
  
  # Run load test to verify
  kubectl run load-test-$zone --image=loadtest:latest \
    --rm -it --restart=Never -- \
    /load-test.sh http://inference-service/health
  
  # If successful, drain old zone nodes
  old_nodes=$(kubectl get nodes -l "cloud.google.com/gke-nodepool=a100-inference-pool,zone=$zone" --no-headers | awk '{print $1}')
  for node in $old_nodes; do
    kubectl cordon $node
    kubectl drain $node --ignore-daemonsets --delete-emptydir-data --timeout=900s
  done
  
  echo "Zone $zone migration complete. Waiting 1 hour before next zone..."
  sleep 3600
done
EOF

chmod +x migrate-inference-zones.sh
./migrate-inference-zones.sh
```

---

## 🚀 Phase 4: Training Infrastructure (Week 5-6)

### Critical Training Pool Upgrade
```bash
# Create new H100 training pools with careful sizing
gcloud container node-pools create h100-training-pool-132-primary \
  --cluster=ai-ml-cluster \
  --location=us-central1 \
  --machine-type=a3-highgpu-8g \
  --accelerator=type=nvidia-h100-80gb,count=8 \
  --num-nodes=500 \
  --node-version=1.32.0-gke.1200 \
  --node-taints=training=h100:NoSchedule \
  --node-labels=workload=training,gpu=h100,version=1.32,pool=primary \
  --placement-type=COMPACT

gcloud container node-pools create h100-training-pool-132-secondary \
  --cluster=ai-ml-cluster \
  --location=us-central1 \
  --machine-type=a3-highgpu-8g \
  --accelerator=type=nvidia-h100-80gb,count=8 \
  --num-nodes=500 \
  --node-version=1.32.0-gke.1200 \
  --node-taints=training=h100:NoSchedule \
  --node-labels=workload=training,gpu=h100,version=1.32,pool=secondary \
  --placement-type=COMPACT
```

### Training Workload Migration Strategy
```yaml
# Training job checkpoint and migration
apiVersion: batch/v1
kind: Job
metadata:
  name: training-migration-coordinator
spec:
  template:
    spec:
      containers:
      - name: migration-coordinator
        image: training-coordinator:latest
        env:
        - name: CHECKPOINT_BUCKET
          value: "gs://training-checkpoints"
        - name: MIGRATION_MODE
          value: "gradual"
        command:
        - /bin/bash
        - -c
        - |
          # Coordinate training job checkpointing
          for job in $(kubectl get jobs -l workload=training -o name); do
            echo "Initiating checkpoint for $job"
            kubectl annotate $job training.ai/checkpoint-requested=true
          done
          
          # Wait for checkpoints to complete
          sleep 1800  # 30 minutes
          
          # Reschedule on new nodes
          kubectl get jobs -l workload=training -o name | while read job; do
            kubectl patch $job --type='merge' -p='{"spec":{"template":{"spec":{"nodeSelector":{"version":"1.32"}}}}}'
          done
```

### Coordinated Training Migration
```bash
cat << 'EOF' > migrate-training-infrastructure.sh
#!/bin/bash
echo "Starting critical H100 training infrastructure migration..."

# Phase 4a: Scale up new primary pool
echo "Phase 4a: Scaling new primary H100 pool"
gcloud container node-pools resize h100-training-pool-132-primary \
  --cluster=ai-ml-cluster \
  --location=us-central1 \
  --num-nodes=500

# Wait for new nodes
kubectl wait --for=condition=Ready \
  nodes -l "cloud.google.com/gke-nodepool=h100-training-pool-132-primary" \
  --timeout=1800s

# Phase 4b: Checkpoint running training jobs
echo "Phase 4b: Coordinating training job checkpoints"
kubectl apply -f training-migration-coordinator.yaml

# Wait for checkpoint coordination
kubectl wait --for=condition=complete job/training-migration-coordinator --timeout=3600s

# Phase 4c: Gradual node migration (25% at a time)
echo "Phase 4c: Gradual training node migration"
old_nodes=($(kubectl get nodes -l "cloud.google.com/gke-nodepool=h100-training-pool" --no-headers | awk '{print $1}'))
total_nodes=${#old_nodes[@]}
batch_size=$((total_nodes / 4))

for batch in {1..4}; do
  echo "Migrating training batch $batch of 4"
  start_idx=$(((batch - 1) * batch_size))
  end_idx=$((start_idx + batch_size))
  
  # Scale up secondary pool for this batch
  current_secondary_size=$((batch * 125))  # 500 nodes / 4 batches
  gcloud container node-pools resize h100-training-pool-132-secondary \
    --cluster=ai-ml-cluster \
    --location=us-central1 \
    --num-nodes=$current_secondary_size
  
  # Cordon and drain old nodes in this batch
  for i in $(seq $start_idx $((end_idx - 1))); do
    if [ $i -lt $total_nodes ]; then
      node=${old_nodes
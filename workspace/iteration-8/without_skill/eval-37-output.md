# GKE Mixed AI/ML Fleet Upgrade Plan: 1.31 → 1.32

## Executive Summary
This plan ensures minimal disruption to training workloads and maintains inference availability while upgrading 5,000 nodes across your AI/ML platform.

## Phase Overview
```
Phase 1: Infrastructure & Dev (500 T4 + 1,000 CPU) - 7 days
Phase 2: Inference Fleet (1,500 A100) - 10 days  
Phase 3: Training Fleet (2,000 H100) - 14 days
Phase 4: Validation & Cleanup - 3 days
Total Duration: 34 days
```

## Pre-Upgrade Preparation (Week -1)

### Control Plane Upgrade
```bash
# Upgrade control plane first (non-disruptive)
gcloud container clusters upgrade ai-ml-cluster \
    --cluster-version=1.32.0-gke.1 \
    --master \
    --zone=us-central1-a
```

### Workload Analysis
```yaml
# Label critical workloads for monitoring
apiVersion: v1
kind: ConfigMap
metadata:
  name: upgrade-monitoring
data:
  critical-training: "h100-pods"
  critical-inference: "a100-serving-pods"
  upgrade-phase: "preparation"
```

### Backup Strategy
```bash
# Backup critical configurations
kubectl get all -o yaml > pre-upgrade-backup.yaml
kubectl get pv,pvc -o yaml > storage-backup.yaml
etcdctl snapshot save pre-upgrade-$(date +%Y%m%d).db
```

## Phase 1: Infrastructure & Development (Days 1-7)

### 1.1 CPU Services Nodes (1,000 nodes)
**Objective**: Upgrade supporting services with minimal impact

```yaml
# Node pool configuration
apiVersion: container.v1
kind: NodePool
metadata:
  name: cpu-services-pool-v132
spec:
  version: "1.32.0-gke.1"
  nodeConfig:
    machineType: "n2-standard-16"
    labels:
      node-type: "cpu-services"
      upgrade-batch: "phase1-cpu"
```

**Upgrade Strategy**: Blue-Green Deployment
```bash
# Create new node pool
gcloud container node-pools create cpu-services-v132 \
    --cluster=ai-ml-cluster \
    --machine-type=n2-standard-16 \
    --num-nodes=250 \
    --node-version=1.32.0-gke.1 \
    --node-labels=upgrade-phase=phase1,node-type=cpu-services

# Gradual migration script
for batch in {1..4}; do
  echo "Migrating CPU batch $batch/4"
  
  # Cordon old nodes (250 nodes per batch)
  kubectl get nodes -l node-type=cpu-services,upgrade-phase!=phase1 \
    --no-headers | head -250 | awk '{print $1}' | \
    xargs kubectl cordon
  
  # Drain nodes gracefully
  kubectl get nodes -l node-type=cpu-services,upgrade-phase!=phase1 \
    --no-headers | head -250 | awk '{print $1}' | \
    xargs -I {} kubectl drain {} --ignore-daemonsets --delete-emptydir-data
  
  # Wait for pods to reschedule
  sleep 300
  
  # Verify workloads are healthy
  kubectl get pods -l app=monitoring,app=logging,app=ingress
done
```

### 1.2 T4 Development Nodes (500 nodes)
**Objective**: Upgrade development environment

```bash
# Rolling upgrade for dev nodes (acceptable brief interruption)
gcloud container node-pools upgrade t4-dev-pool \
    --cluster=ai-ml-cluster \
    --node-version=1.32.0-gke.1 \
    --max-surge-upgrade=2 \
    --max-unavailable-upgrade=1
```

**Validation Checklist**:
- [ ] Jupyter notebooks accessible
- [ ] Development CI/CD pipelines functional
- [ ] GPU drivers loaded correctly
- [ ] Storage mounts working

## Phase 2: Inference Fleet (Days 8-18)

### 2.1 A100 Inference Preparation
```yaml
# Inference service configuration for HA
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ml-inference-service
spec:
  replicas: 6  # Increased for upgrade period
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
      maxSurge: 2
  template:
    spec:
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
          - labelSelector:
              matchLabels:
                app: ml-inference
            topologyKey: kubernetes.io/hostname
```

### 2.2 A100 Node Upgrade Strategy
```bash
#!/bin/bash
# Inference node upgrade with availability guarantee

TOTAL_A100_NODES=1500
BATCH_SIZE=150
BATCHES=10

for batch in $(seq 1 $BATCHES); do
  echo "Upgrading A100 inference batch $batch/$BATCHES"
  
  # Pre-flight checks
  kubectl get pods -l app=inference --field-selector=status.phase=Running | \
    wc -l > current_inference_pods.txt
  
  # Ensure minimum inference capacity
  CURRENT_CAPACITY=$(cat current_inference_pods.txt)
  if [ $CURRENT_CAPACITY -lt 100 ]; then
    echo "ERROR: Insufficient inference capacity. Aborting batch $batch"
    exit 1
  fi
  
  # Create new nodes first
  gcloud container node-pools create a100-inference-batch-$batch \
      --cluster=ai-ml-cluster \
      --accelerator=type=nvidia-tesla-a100,count=4 \
      --machine-type=a2-highgpu-4g \
      --num-nodes=$BATCH_SIZE \
      --node-version=1.32.0-gke.1 \
      --node-labels=gpu-type=a100,workload=inference,batch=batch-$batch
  
  # Wait for nodes to be ready
  kubectl wait --for=condition=Ready \
    nodes -l batch=batch-$batch --timeout=600s
  
  # Install GPU drivers
  kubectl apply -f gpu-driver-installer-a100.yaml
  
  # Graceful migration
  OLD_NODES=$(kubectl get nodes -l gpu-type=a100,batch!=batch-$batch \
    --no-headers | head -$BATCH_SIZE | awk '{print $1}')
  
  for node in $OLD_NODES; do
    kubectl cordon $node
    kubectl drain $node --ignore-daemonsets --grace-period=300
    
    # Verify inference capacity maintained
    sleep 60
    ACTIVE_PODS=$(kubectl get pods -l app=inference \
      --field-selector=status.phase=Running | wc -l)
    if [ $ACTIVE_PODS -lt 80 ]; then
      echo "WARNING: Low inference capacity detected"
      # Add alerting here
    fi
  done
  
  # Health check before next batch
  kubectl get pods -l app=inference
  sleep 120
done
```

### 2.3 Inference Validation
```bash
# Automated inference testing
kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: inference-validation-phase2
spec:
  template:
    spec:
      containers:
      - name: inference-test
        image: your-registry/inference-tester:latest
        command: ["/bin/sh"]
        args:
          - -c
          - |
            echo "Testing inference endpoints..."
            for endpoint in \$(curl -s http://inference-discovery/endpoints); do
              response=\$(curl -s -w "%{http_code}" \$endpoint/health)
              if [ "\$response" != "200" ]; then
                echo "FAIL: \$endpoint"
                exit 1
              fi
            done
            echo "All inference endpoints healthy"
      restartPolicy: Never
EOF
```

## Phase 3: Training Fleet (Days 19-32)

### 3.1 H100 Training Considerations
```yaml
# Training job checkpoint configuration
apiVersion: kubeflow.org/v1
kind: PyTorchJob
metadata:
  name: training-with-checkpoints
spec:
  pytorchReplicaSpecs:
    Master:
      template:
        spec:
          containers:
          - name: pytorch
            env:
            - name: CHECKPOINT_FREQUENCY
              value: "300"  # 5-minute checkpoints during upgrade
            - name: UPGRADE_MODE
              value: "true"
            volumeMounts:
            - name: checkpoint-storage
              mountPath: /checkpoints
          volumes:
          - name: checkpoint-storage
            persistentVolumeClaim:
              claimName: training-checkpoints-pvc
```

### 3.2 Training Node Upgrade Process
```bash
#!/bin/bash
# H100 training node upgrade with checkpoint coordination

TOTAL_H100_NODES=2000
BATCH_SIZE=200
BATCHES=10

# Pre-upgrade: Increase checkpoint frequency
kubectl patch configmap training-config --patch '
data:
  checkpoint_interval: "300"
  upgrade_mode: "enabled"
'

for batch in $(seq 1 $BATCHES); do
  echo "Upgrading H100 training batch $batch/$BATCHES"
  
  # Identify nodes in current batch
  BATCH_NODES=$(kubectl get nodes -l gpu-type=h100 \
    --no-headers | tail -n +$(( ($batch - 1) * $BATCH_SIZE + 1 )) | \
    head -$BATCH_SIZE | awk '{print $1}')
  
  # Signal training jobs to checkpoint
  kubectl annotate pods -l gpu-type=h100,batch=$batch \
    upgrade.ai-ml.com/checkpoint-requested=true
  
  # Wait for checkpoint completion
  echo "Waiting for training checkpoints..."
  timeout 1800 bash -c '
    while [ $(kubectl get pods -l gpu-type=h100,batch='$batch' \
      -o jsonpath="{.items[*].metadata.annotations.checkpoint\.status}" | \
      grep -c "completed") -lt $(echo "'$BATCH_NODES'" | wc -w) ]; do
      sleep 30
    done
  '
  
  # Create new H100 nodes
  gcloud container node-pools create h100-training-batch-$batch \
      --cluster=ai-ml-cluster \
      --accelerator=type=nvidia-tesla-h100,count=8 \
      --machine-type=a3-highgpu-8g \
      --num-nodes=$BATCH_SIZE \
      --node-version=1.32.0-gke.1 \
      --placement-type=COMPACT \
      --node-labels=gpu-type=h100,workload=training,batch=batch-$batch
  
  # Install GPU drivers and ML frameworks
  kubectl apply -f gpu-driver-installer-h100.yaml
  kubectl wait --for=condition=Ready \
    nodes -l batch=batch-$batch --timeout=900s
  
  # Migrate training workloads
  for node in $BATCH_NODES; do
    echo "Migrating training workloads from $node"
    
    # Graceful pod eviction
    kubectl cordon $node
    kubectl annotate node $node upgrade.ai-ml.com/draining=true
    
    # Custom drain for training pods
    TRAINING_PODS=$(kubectl get pods --field-selector=spec.nodeName=$node \
      -l workload=training --no-headers -o name)
    
    for pod in $TRAINING_PODS; do
      echo "Gracefully stopping training pod $pod"
      kubectl annotate $pod upgrade.ai-ml.com/graceful-stop=true
      
      # Wait for graceful shutdown (up to 10 minutes)
      timeout 600 bash -c "
        while kubectl get $pod &>/dev/null; do
          sleep 10
        done
      "
    done
    
    # Standard drain for remaining pods
    kubectl drain $node --ignore-daemonsets --grace-period=60
  done
  
  # Validation pause between batches
  sleep 300
  
  echo "Batch $batch upgrade completed"
done
```

### 3.3 Training Workload Recovery
```bash
# Restart training jobs on new nodes
kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: training-recovery-phase3
spec:
  template:
    spec:
      containers:
      - name: training-recovery
        image: your-registry/training-manager:latest
        command: ["/bin/sh"]
        args:
          - -c
          - |
            echo "Recovering training jobs..."
            
            # Find available checkpoints
            for checkpoint in /checkpoints/*/latest; do
              if [ -f "\$checkpoint" ]; then
                job_name=\$(basename \$(dirname \$checkpoint))
                echo "Resuming training job: \$job_name"
                
                # Create new training job from checkpoint
                kubectl apply -f /templates/training-job-template.yaml \
                  --dry-run=client -o yaml | \
                  sed "s/JOB_NAME/\$job_name/g" | \
                  sed "s|CHECKPOINT_PATH|\$checkpoint|g" | \
                  kubectl apply -f -
              fi
            done
        volumeMounts:
        - name: checkpoint-storage
          mountPath: /checkpoints
      volumes:
      - name: checkpoint-storage
        persistentVolumeClaim:
          claimName: training-checkpoints-pvc
      restartPolicy: Never
EOF
```

## Phase 4: Validation & Cleanup (Days 33-35)

### 4.1 Comprehensive System Validation
```bash
#!/bin/bash
# Full system validation script

echo "=== Phase 4: System Validation ==="

# Node validation
echo "Validating all nodes are on v1.32..."
kubectl get nodes -o wide | grep -v "1.32" && {
  echo "ERROR: Found nodes not on v1.32"
  exit 1
}

# GPU validation
echo "Validating GPU availability..."
kubectl get nodes -l accelerator -o jsonpath='{.items[*].status.capacity.nvidia\.com/gpu}' | \
  awk '{sum+=$1} END {print "Total GPUs:", sum}'

# Workload validation
echo "Validating critical workloads..."
TRAINING_JOBS=$(kubectl get pytorchjobs --no-headers | wc -l)
INFERENCE_PODS=$(kubectl get pods -l app=inference --field-selector=status.phase=Running --no-headers | wc -l)

echo "Active training jobs: $TRAINING_JOBS"
echo "Running inference pods: $INFERENCE_PODS"

if [ $TRAINING_JOBS -lt 50 ] || [ $INFERENCE_PODS -lt 80 ]; then
  echo "WARNING: Lower than expected workload levels"
fi

# Performance validation
kubectl apply -f performance-test-suite.yaml
kubectl wait --for=condition=complete job/performance-test --timeout=1800s

echo "=== Validation Complete ==="
```

### 4.2 Cleanup Operations
```bash
# Remove old node pools
OLD_POOLS=$(gcloud container node-pools list --cluster=ai-ml-cluster \
  --format="value(name)" | grep -v "batch-")

for pool in $OLD_POOLS; do
  echo "Removing old node pool: $pool"
  gcloud container node-pools delete $pool \
    --cluster=ai-ml-cluster --quiet
done

# Reset checkpoint frequencies
kubectl patch configmap training-config --patch '
data:
  checkpoint_interval: "3600"
  upgrade_mode: "disabled"
'

# Final backup
kubectl get all -o yaml > post-upgrade-backup.yaml
```

## Monitoring & Alerting

### Critical Metrics Dashboard
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name:
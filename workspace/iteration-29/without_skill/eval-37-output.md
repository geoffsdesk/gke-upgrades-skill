# GKE 1.31 to 1.32 Upgrade Plan for AI/ML Platform

## Executive Summary
This phased upgrade plan ensures minimal disruption to critical AI/ML workloads while maintaining training continuity and inference availability across your 5,000-node fleet.

## Pre-Upgrade Preparation

### 1. Assessment & Validation (Week 1)
```bash
# Compatibility checks
kubectl get nodes --show-labels
kubectl get pods --all-namespaces -o wide
kubectl api-versions

# Workload analysis
kubectl top nodes
kubectl get pdb --all-namespaces
kubectl get hpa --all-namespaces
```

### 2. Backup & Safety Measures
```yaml
# Critical workload identification
apiVersion: v1
kind: ConfigMap
metadata:
  name: upgrade-critical-workloads
data:
  training-jobs: "ml-training-*"
  inference-services: "inference-*"
  model-serving: "serving-*"
```

### 3. Monitoring Setup
```bash
# Enhanced monitoring during upgrade
kubectl apply -f - <<EOF
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: upgrade-monitoring
spec:
  selector:
    matchLabels:
      upgrade-phase: active
  endpoints:
  - port: metrics
    interval: 30s
EOF
```

## Phase 1: CPU Services Nodes (Days 1-2)
**Target: 1,000 CPU nodes**

### Rationale
- Least critical for AI/ML workloads
- Fastest to upgrade and validate
- Establishes upgrade patterns

### Implementation
```bash
# Create new CPU node pool
gcloud container node-pools create cpu-services-132 \
  --cluster=ml-platform-cluster \
  --machine-type=n2-standard-8 \
  --num-nodes=200 \
  --enable-autorepair \
  --enable-autoupgrade=false \
  --node-version=1.32.x \
  --node-labels=pool=cpu-services-132,upgrade-phase=1

# Gradual migration script
#!/bin/bash
OLD_POOL="cpu-services-131"
NEW_POOL="cpu-services-132"

for batch in {1..5}; do
  echo "Migrating batch $batch/5"
  
  # Scale up new pool
  gcloud container clusters resize ml-platform-cluster \
    --node-pool=$NEW_POOL \
    --num-nodes=$((batch * 200))
  
  # Drain old nodes (200 at a time)
  OLD_NODES=$(kubectl get nodes -l pool=$OLD_POOL | tail -n 200 | awk '{print $1}')
  
  for node in $OLD_NODES; do
    kubectl drain $node --ignore-daemonsets --delete-emptydir-data --force &
  done
  wait
  
  # Verify workloads
  kubectl get pods --all-namespaces | grep -v Running
  
  sleep 300  # 5-minute stabilization
done
```

### Validation Checklist
- [ ] All services responding normally
- [ ] No pending pods
- [ ] Monitoring dashboards green
- [ ] Log aggregation functioning

## Phase 2: T4 Development Nodes (Days 3-4)
**Target: 500 T4 nodes**

### Implementation Strategy
```yaml
# Development workload scheduling preferences
apiVersion: v1
kind: Pod
metadata:
  name: dev-workload-template
spec:
  affinity:
    nodeAffinity:
      preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        preference:
          matchExpressions:
          - key: pool
            operator: In
            values: ["t4-dev-132"]
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
        - matchExpressions:
          - key: accelerator
            operator: In
            values: ["nvidia-tesla-t4"]
```

```bash
# T4 upgrade with development scheduling
gcloud container node-pools create t4-dev-132 \
  --cluster=ml-platform-cluster \
  --accelerator type=nvidia-tesla-t4,count=4 \
  --machine-type=n1-standard-16 \
  --num-nodes=125 \
  --node-version=1.32.x \
  --node-labels=pool=t4-dev-132,gpu-type=t4,workload=development

# Coordinated migration during low-usage hours
kubectl patch deployment dev-jupyter-hub -p '{
  "spec": {
    "template": {
      "spec": {
        "nodeSelector": {
          "pool": "t4-dev-132"
        }
      }
    }
  }
}'
```

## Phase 3: A100 Inference Nodes (Days 5-8)
**Target: 1,500 A100 nodes (Critical Phase)**

### High-Availability Strategy
```yaml
# Inference service with anti-affinity
apiVersion: apps/v1
kind: Deployment
metadata:
  name: model-inference
spec:
  replicas: 6
  template:
    spec:
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
          - labelSelector:
              matchExpressions:
              - key: app
                operator: In
                values: ["model-inference"]
            topologyKey: kubernetes.io/hostname
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
            - matchExpressions:
              - key: accelerator
                operator: In
                values: ["nvidia-tesla-a100"]
```

### Rolling Upgrade Implementation
```bash
#!/bin/bash
# A100 inference upgrade with zero-downtime

ZONES=("us-central1-a" "us-central1-b" "us-central1-c")
NODES_PER_ZONE=500

for zone in "${ZONES[@]}"; do
  echo "Upgrading A100 nodes in $zone"
  
  # Create new pool in zone
  gcloud container node-pools create a100-inference-132-${zone##*-} \
    --cluster=ml-platform-cluster \
    --zone=$zone \
    --accelerator type=nvidia-tesla-a100,count=8 \
    --machine-type=a2-highgpu-8g \
    --num-nodes=$NODES_PER_ZONE \
    --node-version=1.32.x \
    --node-labels=pool=a100-inference-132,gpu-type=a100,workload=inference
  
  # Wait for nodes ready
  kubectl wait --for=condition=Ready nodes -l pool=a100-inference-132 --timeout=600s
  
  # Gradual traffic shift (25% batches)
  for batch in {1..4}; do
    # Update service selectors to include new nodes
    kubectl patch service inference-service -p "{
      \"spec\": {
        \"selector\": {
          \"pool\": \"a100-inference-132\",
          \"batch\": \"$batch\"
        }
      }
    }"
    
    # Drain old nodes in batches
    OLD_NODES=$(kubectl get nodes -l pool=a100-inference-131,zone=$zone | 
               head -n $((NODES_PER_ZONE/4)) | awk '{print $1}')
    
    for node in $OLD_NODES; do
      kubectl drain $node --grace-period=300 --ignore-daemonsets &
    done
    wait
    
    # Health check
    kubectl get pods -l app=inference -o wide
    sleep 600  # 10-minute stabilization
  done
done
```

### Inference Validation
```bash
# Automated inference testing
#!/bin/bash
INFERENCE_ENDPOINTS=$(kubectl get svc -l type=inference -o jsonpath='{.items[*].status.loadBalancer.ingress[0].ip}')

for endpoint in $INFERENCE_ENDPOINTS; do
  response=$(curl -s -w "%{http_code}" -X POST \
    -H "Content-Type: application/json" \
    -d '{"model": "test", "input": "validation"}' \
    http://$endpoint/predict)
  
  if [[ ${response: -3} != "200" ]]; then
    echo "ALERT: Inference endpoint $endpoint failed"
    exit 1
  fi
done

echo "All inference endpoints validated successfully"
```

## Phase 4: H100 Training Nodes (Days 9-14)
**Target: 2,000 H100 nodes (Most Critical Phase)**

### Training-Aware Upgrade Strategy
```yaml
# Training job with checkpoint management
apiVersion: batch/v1
kind: Job
metadata:
  name: distributed-training
spec:
  template:
    spec:
      containers:
      - name: trainer
        image: training:latest
        env:
        - name: CHECKPOINT_INTERVAL
          value: "300"  # 5-minute checkpoints during upgrade
        - name: UPGRADE_MODE
          value: "true"
        volumeMounts:
        - name: checkpoint-storage
          mountPath: /checkpoints
      volumes:
      - name: checkpoint-storage
        persistentVolumeClaim:
          claimName: training-checkpoints
```

### Coordinated Training Migration
```bash
#!/bin/bash
# H100 training upgrade with job coordination

# Pre-upgrade: Force checkpoint all training jobs
kubectl get jobs -l type=training -o name | xargs -I {} kubectl patch {} -p '{
  "spec": {
    "template": {
      "spec": {
        "containers": [{
          "name": "trainer",
          "env": [{"name": "FORCE_CHECKPOINT", "value": "true"}]
        }]
      }
    }
  }
}'

# Wait for checkpoints
sleep 900  # 15 minutes for checkpoint completion

# Node pool creation with reservation
gcloud compute reservations create h100-upgrade-reservation \
  --accelerator count=8,type=nvidia-h100-80gb \
  --machine-type=a3-highgpu-8g \
  --zone=us-central1-a \
  --vm-count=250

gcloud container node-pools create h100-training-132 \
  --cluster=ml-platform-cluster \
  --accelerator type=nvidia-h100-80gb,count=8 \
  --machine-type=a3-highgpu-8g \
  --num-nodes=250 \
  --node-version=1.32.x \
  --reservation-affinity=specific \
  --reservation=h100-upgrade-reservation \
  --node-labels=pool=h100-training-132,gpu-type=h100,workload=training

# Staged migration (250 nodes at a time)
for batch in {1..8}; do
  echo "Upgrading H100 batch $batch/8"
  
  # Scale new pool
  NEW_SIZE=$((batch * 250))
  gcloud container clusters resize ml-platform-cluster \
    --node-pool=h100-training-132 \
    --num-nodes=$NEW_SIZE
  
  # Wait for nodes
  kubectl wait --for=condition=Ready \
    nodes -l pool=h100-training-132 \
    --timeout=900s
  
  # Resume training jobs on new nodes
  kubectl get jobs -l type=training,batch=$batch -o name | \
    xargs -I {} kubectl patch {} -p '{
      "spec": {
        "template": {
          "spec": {
            "nodeSelector": {
              "pool": "h100-training-132"
            }
          }
        }
      }
    }'
  
  # Graceful old node drainage
  OLD_NODES=$(kubectl get nodes -l pool=h100-training-131 | 
             head -n 250 | awk 'NR>1 {print $1}')
  
  for node in $OLD_NODES; do
    # Longer grace period for training workloads
    kubectl drain $node --grace-period=1800 --ignore-daemonsets &
  done
  wait
  
  # Verify training resumption
  kubectl logs -l type=training --tail=50 | grep "Training resumed"
  
  sleep 1800  # 30-minute stabilization
done
```

### Training Validation
```bash
# Training health monitoring
kubectl create -f - <<EOF
apiVersion: v1
kind: ServiceMonitor
metadata:
  name: training-upgrade-monitor
spec:
  selector:
    matchLabels:
      type: training
  endpoints:
  - port: metrics
    path: /metrics
    interval: 60s
EOF

# Automated training status check
#!/bin/bash
TRAINING_JOBS=$(kubectl get jobs -l type=training -o jsonpath='{.items[*].metadata.name}')

for job in $TRAINING_JOBS; do
  STATUS=$(kubectl get job $job -o jsonpath='{.status.conditions[?(@.type=="Complete")].status}')
  ACTIVE=$(kubectl get job $job -o jsonpath='{.status.active}')
  
  if [[ $ACTIVE -eq 0 && $STATUS != "True" ]]; then
    echo "ALERT: Training job $job may have failed during upgrade"
    kubectl describe job $job
  fi
done
```

## Post-Upgrade Validation & Cleanup

### Comprehensive System Validation
```bash
#!/bin/bash
# Full platform validation

echo "=== Node Validation ==="
kubectl get nodes --show-labels | grep "1.32"
kubectl top nodes

echo "=== Workload Validation ==="
kubectl get pods --all-namespaces -o wide | grep -v Running

echo "=== GPU Validation ==="
kubectl describe nodes -l accelerator | grep "nvidia.com"

echo "=== Service Validation ==="
kubectl get svc --all-namespaces
kubectl get ingress --all-namespaces

echo "=== Training Jobs Status ==="
kubectl get jobs -l type=training -o wide

echo "=== Inference Services Status ==="
kubectl get deployments -l type=inference -o wide
```

### Performance Baseline Comparison
```bash
# Pre/post upgrade performance comparison
kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: performance-validation
spec:
  template:
    spec:
      containers:
      - name: validator
        image: ml-performance-test:latest
        command: ["python", "/test/benchmark.py"]
        env:
        - name: TEST_SUITE
          value: "post-upgrade"
        - name: BASELINE_METRICS_PATH
          value: "/baseline/pre-upgrade.json"
        resources:
          limits:
            nvidia.com/gpu: 1
      restartPolicy: Never
      nodeSelector:
        pool: h100-training-132
EOF
```

### Cleanup Operations
```bash
# Remove old node pools after validation
OLD_POOLS=("cpu-services-131" "t4-dev-131" "a100-inference-131" "h100-training-131")

for pool in "${OLD_POOLS[@]}"; do
  echo "Removing old pool: $pool"
  gcloud container node-pools delete $pool \
    --cluster=ml-platform-cluster \
    --quiet
done

# Clean up reservations
gcloud compute reservations delete h100-upgrade-reservation --quiet
```

## Risk Mitigation & Rollback Plan

### Emergency Rollback Procedure
```bash
#!/bin/bash
# Emergency rollback script

echo "INITIATING EMERGENCY ROLLBACK"

# Immediate traffic redirection
kubectl patch service inference-service -p '{
  "spec": {
    "selector": {
      "pool": "a100-inference-131"
    }
  }
}'

# Pause new training jobs
kubectl patch deployment training-scheduler -p '{
  "spec": {
    "replicas": 0
  }
}'

# Scale back old pools if available
gcloud container clusters resize ml-platform-cluster \
  --node-pool=h100-training-131 \
  --num-nodes=2000 &

gcloud container clusters resize ml-platform-cluster \
  --node-pool=a100-inference-131 \
  --num-nodes=1500 &

wait

echo "Emergency rollback completed. Manual
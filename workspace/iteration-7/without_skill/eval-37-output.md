# GKE Mixed AI/ML Platform Upgrade Plan: v1.31 → v1.32

## Executive Summary
This plan ensures minimal disruption to critical AI/ML workloads during the Kubernetes upgrade, prioritizing training continuity and inference availability across 5,000 nodes.

## Pre-Upgrade Preparation

### 1. Compatibility Assessment
```bash
# Check workload compatibility
kubectl get nodes --show-labels | grep gpu-type
kubectl get pods -A -o wide | grep -E "(training|inference)" 

# Verify GPU operator compatibility
kubectl get pods -n gpu-operator
helm list -A | grep nvidia
```

### 2. Backup Strategy
```yaml
# Critical backup checklist
- [ ] ETCD snapshots
- [ ] Training checkpoints and model weights
- [ ] Inference model artifacts
- [ ] ConfigMaps and Secrets
- [ ] PVC snapshots for persistent training data
```

### 3. Monitoring Setup
```yaml
# Enhanced monitoring during upgrade
apiVersion: v1
kind: ConfigMap
metadata:
  name: upgrade-monitoring
data:
  alerts.yaml: |
    - alert: TrainingJobFailure
      expr: kube_job_failed{job_name=~".*training.*"} > 0
      labels:
        severity: critical
    - alert: InferenceLatencyHigh
      expr: histogram_quantile(0.95, http_request_duration_seconds) > 2.0
      labels:
        severity: warning
```

## Phase 1: Foundation Services (Days 1-2)
**Target: 1,000 CPU nodes**

### Priority: Low-risk services first
```bash
# Upgrade sequence
1. Logging and monitoring infrastructure
2. CI/CD pipeline nodes
3. Internal tooling and utilities
4. Load balancers and ingress controllers
```

### Node Pool Configuration:
```yaml
# cpu-services-pool upgrade
gcloud container node-pools create cpu-services-v132 \
  --cluster=ml-platform-cluster \
  --machine-type=n2-standard-16 \
  --num-nodes=250 \
  --node-version=1.32.0 \
  --node-labels=node-type=cpu,phase=foundation \
  --enable-autoscaling \
  --max-nodes=300
```

### Validation:
```bash
# Verify CPU node functionality
kubectl get nodes -l node-type=cpu --show-labels
kubectl top nodes -l node-type=cpu
```

## Phase 2: Development Environment (Days 3-4)
**Target: 500 T4 nodes**

### Strategy: Blue-green deployment
```bash
# Create new T4 development pool
gcloud container node-pools create t4-dev-v132 \
  --cluster=ml-platform-cluster \
  --machine-type=n1-standard-8 \
  --accelerator=type=nvidia-tesla-t4,count=1 \
  --num-nodes=125 \
  --node-version=1.32.0 \
  --node-labels=gpu-type=t4,environment=dev,phase=development
```

### Workload Migration:
```yaml
# Development workload migration
apiVersion: batch/v1
kind: Job
metadata:
  name: dev-workload-migration
spec:
  template:
    spec:
      nodeSelector:
        gpu-type: t4
        environment: dev
        phase: development
      containers:
      - name: migration-validator
        image: nvidia/cuda:12.0-runtime-ubuntu20.04
        command: ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv"]
```

## Phase 3: Inference Infrastructure (Days 5-8)
**Target: 1,500 A100 nodes - CRITICAL PHASE**

### Strategy: Rolling upgrade with traffic shifting
```bash
# Create A100 inference pools in batches of 375 nodes
for batch in {1..4}; do
  gcloud container node-pools create a100-inference-v132-batch${batch} \
    --cluster=ml-platform-cluster \
    --machine-type=a2-highgpu-2g \
    --accelerator=type=nvidia-tesla-a100,count=2 \
    --num-nodes=95 \
    --node-version=1.32.0 \
    --node-labels=gpu-type=a100,workload=inference,batch=${batch} \
    --enable-autoscaling \
    --max-nodes=120
done
```

### Traffic Management:
```yaml
# Inference service with gradual traffic shift
apiVersion: v1
kind: Service
metadata:
  name: ml-inference-service
  annotations:
    cloud.google.com/neg: '{"ingress": true}'
spec:
  type: LoadBalancer
  selector:
    app: ml-inference
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ml-inference-v132
spec:
  replicas: 100
  selector:
    matchLabels:
      app: ml-inference
      version: v132
  template:
    spec:
      nodeSelector:
        gpu-type: a100
        workload: inference
      containers:
      - name: inference-server
        image: nvcr.io/nvidia/tritonserver:23.12-py3
        resources:
          limits:
            nvidia.com/gpu: 1
```

### Validation per batch:
```bash
# Health check script
#!/bin/bash
BATCH=$1
echo "Validating A100 batch ${BATCH}"

# Check GPU availability
kubectl get nodes -l batch=${BATCH} -o custom-columns=NAME:.metadata.name,GPU:.status.allocatable.nvidia\.com/gpu

# Test inference latency
kubectl run inference-test-${BATCH} \
  --image=curlimages/curl \
  --rm -it --restart=Never \
  -- curl -X POST http://ml-inference-service/v2/models/test/infer
```

## Phase 4: Training Infrastructure (Days 9-14)
**Target: 2,000 H100 nodes - HIGHEST PRIORITY**

### Strategy: Coordinated maintenance windows
```yaml
# Training-aware upgrade scheduling
apiVersion: v1
kind: ConfigMap
metadata:
  name: training-schedule
data:
  upgrade-windows: |
    # Coordinate with ML teams for training job scheduling
    - window: "2024-01-15 02:00-06:00 UTC"
      nodes: "h100-pool-1 (500 nodes)"
      impact: "Large model training pause"
    - window: "2024-01-16 02:00-06:00 UTC" 
      nodes: "h100-pool-2 (500 nodes)"
      impact: "Distributed training checkpoint"
```

### H100 Pool Creation:
```bash
# Create H100 pools with training-optimized networking
for pool in {1..4}; do
  gcloud container node-pools create h100-training-v132-pool${pool} \
    --cluster=ml-platform-cluster \
    --machine-type=a3-highgpu-8g \
    --accelerator=type=nvidia-h100-80gb,count=8 \
    --num-nodes=63 \
    --node-version=1.32.0 \
    --node-labels=gpu-type=h100,workload=training,pool=${pool} \
    --placement-type=COMPACT \
    --enable-gvnic \
    --disk-size=1000GB \
    --disk-type=pd-ssd
done
```

### Training Job Migration:
```yaml
# Training job with checkpoint recovery
apiVersion: batch/v1
kind: Job
metadata:
  name: distributed-training-migration
spec:
  parallelism: 64
  template:
    spec:
      nodeSelector:
        gpu-type: h100
        workload: training
      containers:
      - name: training-worker
        image: nvcr.io/nvidia/pytorch:23.12-py3
        env:
        - name: CHECKPOINT_PATH
          value: "/shared/checkpoints/latest"
        - name: NCCL_DEBUG
          value: "INFO"
        volumeMounts:
        - name: checkpoint-storage
          mountPath: /shared/checkpoints
        resources:
          limits:
            nvidia.com/gpu: 8
      volumes:
      - name: checkpoint-storage
        persistentVolumeClaim:
          claimName: training-checkpoints-pvc
```

## Migration Automation Scripts

### Node Pool Transition Script:
```bash
#!/bin/bash
# migrate_workloads.sh

OLD_POOL=$1
NEW_POOL=$2
WORKLOAD_TYPE=$3

echo "Migrating ${WORKLOAD_TYPE} workloads from ${OLD_POOL} to ${NEW_POOL}"

# Cordon old nodes
kubectl get nodes -l node-pool=${OLD_POOL} --no-headers | awk '{print $1}' | \
  xargs -I {} kubectl cordon {}

# Drain with grace period based on workload type
if [[ "$WORKLOAD_TYPE" == "training" ]]; then
  GRACE_PERIOD=3600  # 1 hour for training jobs
elif [[ "$WORKLOAD_TYPE" == "inference" ]]; then
  GRACE_PERIOD=300   # 5 minutes for inference
else
  GRACE_PERIOD=60    # 1 minute for other workloads
fi

kubectl get nodes -l node-pool=${OLD_POOL} --no-headers | awk '{print $1}' | \
  xargs -I {} kubectl drain {} --grace-period=${GRACE_PERIOD} --delete-emptydir-data --ignore-daemonsets

# Wait for workloads to reschedule
echo "Waiting for workloads to reschedule..."
sleep 180

# Verify new nodes are healthy
kubectl get nodes -l node-pool=${NEW_POOL} | grep Ready
kubectl get pods -A -o wide | grep ${NEW_POOL}

echo "Migration complete for ${OLD_POOL} -> ${NEW_POOL}"
```

### Health Validation Script:
```bash
#!/bin/bash
# validate_upgrade.sh

NODE_POOL=$1
WORKLOAD_TYPE=$2

echo "Validating upgrade for ${NODE_POOL} (${WORKLOAD_TYPE})"

# Check node readiness
READY_NODES=$(kubectl get nodes -l node-pool=${NODE_POOL} | grep Ready | wc -l)
TOTAL_NODES=$(kubectl get nodes -l node-pool=${NODE_POOL} | tail -n +2 | wc -l)

echo "Nodes ready: ${READY_NODES}/${TOTAL_NODES}"

# GPU-specific validation
if [[ "$NODE_POOL" =~ gpu ]]; then
  echo "Validating GPU availability..."
  kubectl get nodes -l node-pool=${NODE_POOL} \
    -o custom-columns=NAME:.metadata.name,GPU:.status.allocatable.nvidia\.com/gpu
  
  # Run GPU test pod
  kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: gpu-test-${NODE_POOL}
spec:
  nodeSelector:
    node-pool: ${NODE_POOL}
  containers:
  - name: gpu-test
    image: nvidia/cuda:12.0-runtime-ubuntu20.04
    command: ["nvidia-smi"]
    resources:
      limits:
        nvidia.com/gpu: 1
  restartPolicy: Never
EOF

  # Wait and check results
  kubectl wait --for=condition=complete pod/gpu-test-${NODE_POOL} --timeout=300s
  kubectl logs gpu-test-${NODE_POOL}
  kubectl delete pod gpu-test-${NODE_POOL}
fi

echo "Validation complete for ${NODE_POOL}"
```

## Rollback Strategy

### Immediate Rollback Triggers:
```yaml
# Automated rollback conditions
conditions:
  - training_jobs_failed > 5%
  - inference_latency > 150% baseline
  - gpu_utilization < 80% of previous
  - node_not_ready > 2% for 10 minutes
```

### Rollback Execution:
```bash
#!/bin/bash
# rollback_upgrade.sh

AFFECTED_POOL=$1
BACKUP_POOL=$2

echo "EMERGENCY ROLLBACK: ${AFFECTED_POOL} -> ${BACKUP_POOL}"

# Immediate traffic shift for inference
if [[ "$AFFECTED_POOL" =~ inference ]]; then
  kubectl patch service ml-inference-service -p '{"spec":{"selector":{"node-pool":"'${BACKUP_POOL}'"}}}'
fi

# Restore node pools
gcloud container node-pools create ${BACKUP_POOL}-restored \
  --cluster=ml-platform-cluster \
  --node-version=1.31.0 \
  --num-nodes=100

# Migrate workloads back
./migrate_workloads.sh ${AFFECTED_POOL} ${BACKUP_POOL}-restored

echo "Rollback completed"
```

## Success Metrics & Validation

### Key Performance Indicators:
```yaml
success_criteria:
  training_continuity:
    - Zero training job data loss
    - < 4 hour total training downtime
    - Checkpoint recovery success rate > 99%
  
  inference_availability:
    - < 30 seconds service interruption per batch
    - Latency increase < 10% during migration
    - 99.9% API availability maintained
  
  overall_upgrade:
    - Zero data loss across all workloads
    - GPU utilization recovery within 2 hours
    - All nodes healthy post-upgrade
```

### Final Validation Checklist:
```bash
# Comprehensive validation script
#!/bin/bash
echo "=== FINAL UPGRADE VALIDATION ==="

# 1. All nodes on v1.32
kubectl get nodes -o wide | grep -v "v1.32" | wc -l

# 2. GPU functionality
kubectl apply -f gpu-validation-jobs.yaml
kubectl wait --for=condition=complete job/gpu-validation --timeout=600s

# 3. Training jobs resumable
kubectl get jobs -A | grep training | grep -E "(Running|Completed)"

# 4. Inference services responding
for svc in $(kubectl get svc -l app=inference -o name); do
  kubectl port-forward $svc 8080:80 &
  curl -f http://localhost:8080/health || echo "FAILURE: $svc"
  kill %1
done

# 5. Resource utilization normal
kubectl top nodes | awk 'NR>1 {print $3}' | sed 's/%//' | \
  awk '{sum+=$1} END {print "Average CPU:", sum/NR "%"}'

echo "=== VALIDATION COMPLETE ==="
```

## Timeline Summary

| Phase | Duration | Nodes | Risk Level | Key Focus |
|-------|----------|--------|------------|-----------|
| 1 | Days 1-2 | 1,000 CPU | Low | Foundation stability |
| 2 | Days 3-4 | 500 T4 | Low | Development continuity |
| 3 | Days 5-8 | 1,500 A100 | High | Inference availability |
| 4 | Days 9-14 | 2,000 H100 | Critical | Training continuity |

**Total Upgrade Window: 14 days**
**Expected Downtime per Workload: < 4 hours**

This plan ensures your critical AI/ML workloads maintain maximum availability while systematically upgrading the entire 5,000-node fleet to Kubernetes 1.32.
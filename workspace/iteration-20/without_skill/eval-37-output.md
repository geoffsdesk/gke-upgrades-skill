# GKE 1.31 → 1.32 Upgrade Plan for Mixed AI/ML Platform

## Executive Summary
This phased upgrade plan prioritizes training continuity and inference availability through strategic sequencing, redundancy preservation, and comprehensive rollback procedures.

## Pre-Upgrade Preparation

### 1. Environment Assessment
```bash
# Audit current workloads
kubectl get pods --all-namespaces -o wide | grep -E "(training|inference)"
kubectl top nodes --sort-by=memory
kubectl get pdb --all-namespaces

# Check GPU utilization
nvidia-smi dmon -s pucvmet -d 10 -c 6
```

### 2. Backup & Safety Measures
```yaml
# Critical workload backup script
#!/bin/bash
BACKUP_DATE=$(date +%Y%m%d)
kubectl get all --all-namespaces -o yaml > cluster-state-${BACKUP_DATE}.yaml
kubectl get pv,pvc --all-namespaces -o yaml > storage-state-${BACKUP_DATE}.yaml
etcd snapshot save cluster-backup-${BACKUP_DATE}.db
```

### 3. Pre-upgrade Testing
- Deploy 1.32 test cluster with representative workloads
- Validate GPU driver compatibility (NVIDIA 525.x+ for H100/A100)
- Test critical ML frameworks (TensorFlow, PyTorch, CUDA compatibility)

## Phase 1: CPU Services Nodes (Days 1-2)
**Target: 1,000 CPU nodes**

### Rationale
- Least impact on core ML workloads
- Validates upgrade process
- Maintains support services for GPU nodes

### Execution Strategy
```bash
# Create new CPU node pools with 1.32
gcloud container node-pools create cpu-services-v132 \
  --cluster=ml-cluster \
  --machine-type=n2-standard-16 \
  --num-nodes=200 \
  --node-version=1.32.x \
  --max-pods-per-node=110

# Gradual migration in 200-node batches
kubectl cordon <old-cpu-nodes>
kubectl drain <old-cpu-nodes> --ignore-daemonsets --delete-emptydir-data
```

### Monitoring
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: upgrade-monitoring
data:
  check-services.sh: |
    #!/bin/bash
    kubectl get pods -n kube-system | grep -v Running
    kubectl get svc --all-namespaces | grep pending
    kubectl top nodes | grep cpu-services
```

## Phase 2: T4 Development Nodes (Days 3-4)
**Target: 500 T4 nodes**

### Rationale
- Development workloads can tolerate brief interruptions
- Further validates GPU compatibility
- Smaller blast radius than production GPU nodes

### Execution Strategy
```bash
# Create T4 node pool with 1.32
gcloud container node-pools create t4-dev-v132 \
  --cluster=ml-cluster \
  --machine-type=g2-standard-12 \
  --accelerator=type=nvidia-tesla-t4,count=1 \
  --num-nodes=100 \
  --node-version=1.32.x \
  --maintenance-policy=MIGRATE
```

### GPU Validation
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: gpu-validation-t4
spec:
  template:
    spec:
      containers:
      - name: gpu-test
        image: nvidia/cuda:12.3-devel-ubuntu22.04
        command: ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv"]
        resources:
          limits:
            nvidia.com/gpu: 1
      restartPolicy: Never
```

## Phase 3: A100 Inference Nodes (Days 5-8)
**Target: 1,500 A100 nodes**

### Rationale
- Critical for production inference
- Requires careful capacity management
- Shorter workloads than training jobs

### Execution Strategy - Rolling Blue-Green
```bash
# Phase 3A: Create 50% capacity with 1.32 (750 nodes)
gcloud container node-pools create a100-inference-v132-primary \
  --cluster=ml-cluster \
  --machine-type=a2-highgpu-1g \
  --accelerator=type=nvidia-tesla-a100,count=1 \
  --num-nodes=750 \
  --node-version=1.32.x \
  --preemptible=false

# Phase 3B: Migrate inference workloads
kubectl label nodes -l node-pool=a100-inference-v132 workload-type=inference-primary
```

### Load Balancer Configuration
```yaml
apiVersion: v1
kind: Service
metadata:
  name: inference-service
  annotations:
    cloud.google.com/load-balancer-type: "Internal"
spec:
  type: LoadBalancer
  selector:
    app: inference
  ports:
  - port: 8080
    targetPort: 8080
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: inference-ingress
  annotations:
    kubernetes.io/ingress.class: "gce"
    kubernetes.io/ingress.allow-http: "false"
spec:
  rules:
  - host: inference.ml-platform.com
    http:
      paths:
      - path: /*
        pathType: ImplementationSpecific
        backend:
          service:
            name: inference-service
            port:
              number: 8080
```

### Monitoring & Validation
```bash
# Inference latency monitoring
kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: inference-monitoring
data:
  monitor.py: |
    import requests
    import time
    import json
    
    def test_inference_endpoint():
        start_time = time.time()
        response = requests.post('http://inference-service:8080/predict', 
                               json={'data': 'test'})
        latency = time.time() - start_time
        return response.status_code == 200, latency
    
    # Log metrics
    success, latency = test_inference_endpoint()
    print(f"Status: {success}, Latency: {latency}ms")
EOF
```

## Phase 4: H100 Training Nodes (Days 9-14)
**Target: 2,000 H100 nodes - MOST CRITICAL**

### Rationale
- Highest priority workloads
- Longest-running jobs
- Most expensive to interrupt

### Pre-Phase 4 Preparation
```bash
# Identify long-running training jobs
kubectl get pods --all-namespaces --field-selector=status.phase=Running \
  --sort-by=.metadata.creationTimestamp | grep training

# Check training job checkpointing status
kubectl get jobs -l workload-type=training -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.startTime}{"\n"}{end}'
```

### Execution Strategy - Checkpoint-Aware Rolling Upgrade
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: training-checkpoint-manager
spec:
  template:
    spec:
      containers:
      - name: checkpoint-manager
        image: your-registry/checkpoint-manager:v1.0
        command: ["/bin/bash"]
        args:
        - -c
        - |
          # Wait for training jobs to reach checkpoint
          for job in $(kubectl get jobs -l workload-type=training -o name); do
            echo "Waiting for $job to checkpoint..."
            kubectl wait --for=condition=checkpoint-ready $job --timeout=3600s
          done
          echo "All training jobs checkpointed successfully"
      restartPolicy: Never
```

### Node Pool Creation & Migration
```bash
# Create H100 1.32 node pools in 400-node batches
for i in {1..5}; do
  gcloud container node-pools create h100-training-v132-batch$i \
    --cluster=ml-cluster \
    --machine-type=a3-highgpu-8g \
    --accelerator=type=nvidia-h100-80gb,count=8 \
    --num-nodes=400 \
    --node-version=1.32.x \
    --disk-size=200GB \
    --disk-type=pd-ssd \
    --preemptible=false \
    --maintenance-policy=TERMINATE
done

# Gradual migration with training-aware draining
kubectl drain h100-old-node-1 \
  --ignore-daemonsets \
  --delete-emptydir-data \
  --grace-period=3600 \
  --timeout=7200s
```

### Training Job Migration Script
```python
#!/usr/bin/env python3
import kubernetes
from kubernetes import client, config
import time
import logging

class TrainingJobMigrator:
    def __init__(self):
        config.load_incluster_config()
        self.v1 = client.CoreV1Api()
        self.batch_v1 = client.BatchV1Api()
    
    def migrate_training_job(self, job_name, namespace):
        # Get current job
        job = self.batch_v1.read_namespaced_job(job_name, namespace)
        
        # Check if job has reached checkpoint
        if not self.is_checkpointed(job):
            logging.info(f"Waiting for {job_name} to checkpoint...")
            self.wait_for_checkpoint(job_name, namespace)
        
        # Update job to target new nodes
        job.spec.template.spec.node_selector = {
            'node-pool': 'h100-training-v132'
        }
        
        # Apply update
        self.batch_v1.patch_namespaced_job(job_name, namespace, job)
        logging.info(f"Migrated {job_name} to new nodes")
    
    def is_checkpointed(self, job):
        # Implementation depends on your checkpointing mechanism
        return job.metadata.annotations.get('checkpoint.ml/status') == 'ready'
    
    def wait_for_checkpoint(self, job_name, namespace, timeout=3600):
        start_time = time.time()
        while time.time() - start_time < timeout:
            job = self.batch_v1.read_namespaced_job(job_name, namespace)
            if self.is_checkpointed(job):
                return True
            time.sleep(30)
        raise TimeoutError(f"Job {job_name} did not checkpoint within {timeout} seconds")

if __name__ == "__main__":
    migrator = TrainingJobMigrator()
    # Migrate all training jobs
    jobs = migrator.batch_v1.list_job_for_all_namespaces(
        label_selector="workload-type=training"
    )
    for job in jobs.items:
        migrator.migrate_training_job(job.metadata.name, job.metadata.namespace)
```

## Rollback Procedures

### Immediate Rollback (Per Phase)
```bash
# Emergency rollback script
#!/bin/bash
PHASE=$1
case $PHASE in
  "cpu")
    gcloud container node-pools delete cpu-services-v132 --cluster=ml-cluster
    kubectl uncordon $(kubectl get nodes -l node-pool=cpu-services-v131 -o name)
    ;;
  "t4")
    gcloud container node-pools delete t4-dev-v132 --cluster=ml-cluster
    kubectl uncordon $(kubectl get nodes -l node-pool=t4-dev-v131 -o name)
    ;;
  "a100")
    # Redirect traffic back to old nodes
    kubectl label nodes -l node-pool=a100-inference-v131 workload-type=inference-primary
    kubectl label nodes -l node-pool=a100-inference-v132 workload-type=inference-secondary
    ;;
  "h100")
    # Critical: Restore training jobs from checkpoints
    kubectl apply -f training-jobs-backup.yaml
    gcloud container node-pools delete h100-training-v132-batch* --cluster=ml-cluster
    ;;
esac
```

### Health Checks & Success Criteria

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: upgrade-health-checks
data:
  health-check.sh: |
    #!/bin/bash
    
    # Check cluster health
    kubectl get nodes | grep -v Ready | wc -l
    if [ $? -gt 0 ]; then
      echo "FAIL: Nodes not ready"
      exit 1
    fi
    
    # Check GPU availability
    kubectl get nodes -o json | jq '.items[].status.allocatable."nvidia.com/gpu"' | grep -v null | wc -l
    echo "GPU nodes available: $?"
    
    # Check critical workloads
    kubectl get pods -l workload-type=training --field-selector=status.phase=Running | wc -l
    kubectl get pods -l workload-type=inference --field-selector=status.phase=Running | wc -l
    
    # Performance validation
    kubectl apply -f gpu-benchmark-job.yaml
    kubectl wait --for=condition=complete job/gpu-benchmark --timeout=300s
```

## Timeline Summary

| Phase | Duration | Nodes | Risk Level | Rollback Time |
|-------|----------|--------|------------|---------------|
| 1: CPU Services | 2 days | 1,000 | Low | 30 minutes |
| 2: T4 Development | 2 days | 500 | Medium | 45 minutes |
| 3: A100 Inference | 4 days | 1,500 | High | 1-2 hours |
| 4: H100 Training | 6 days | 2,000 | Critical | 2-4 hours |
| **Total** | **14 days** | **5,000** | | |

## Success Metrics
- Zero training job failures during upgrade
- <5% increase in inference latency during Phase 3
- 100% GPU utilization restoration within 24 hours of each phase
- No data loss or corruption
- Complete upgrade with <1% unplanned downtime

This plan ensures business continuity while systematically upgrading your entire ML platform infrastructure.
# GKE Fleet Upgrade Plan: v1.31 → v1.32
## Mixed AI/ML Platform (5,000 nodes)

## Executive Summary
This plan prioritizes **training continuity** and **inference availability** through a 4-phase approach, upgrading lowest-risk components first while maintaining operational integrity.

## Pre-Upgrade Preparation

### 1. Compatibility Assessment
```bash
# Check workload compatibility
kubectl get pods --all-namespaces -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[*].image}{"\n"}{end}' | grep -E "(training|inference)"

# Verify GPU operator compatibility
kubectl get nodes -l accelerator=nvidia-tesla-h100 -o yaml | grep -E "(nvidia|cuda)"
```

### 2. Backup Strategy
```yaml
# Critical backup checklist
- [ ] ETCD snapshots
- [ ] Training checkpoints to persistent storage
- [ ] Model artifacts and weights
- [ ] Configuration maps and secrets
- [ ] Custom resource definitions
- [ ] Network policies and RBAC
```

### 3. Monitoring Setup
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: upgrade-monitoring
data:
  alerts.yaml: |
    - alert: NodeUpgradeFailure
      expr: kube_node_status_condition{condition="Ready",status="false"} == 1
    - alert: GPUWorkloadDisruption  
      expr: nvidia_gpu_duty_cycle < 0.8
    - alert: TrainingJobFailure
      expr: kube_job_failed > 0
```

## Phase 1: CPU Services Nodes (1,000 nodes)
**Duration: 2-3 days** | **Risk: Low**

### Objective
Upgrade supporting infrastructure without impacting GPU workloads.

### Pre-Phase Actions
```bash
# Identify CPU-only workloads
kubectl get pods --all-namespaces --field-selector spec.nodeName="" -o wide | grep -v "nvidia\|gpu"

# Ensure CPU services have sufficient redundancy
kubectl get deployments --all-namespaces -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.replicas}{"\n"}{end}'
```

### Node Pool Configuration
```yaml
apiVersion: container.v1
kind: NodePool
metadata:
  name: cpu-services-pool
spec:
  version: "1.32"
  initialNodeCount: 200
  autoscaling:
    enabled: true
    minNodeCount: 200
    maxNodeCount: 1000
  config:
    machineType: "n2-standard-16"
    labels:
      workload-type: "services"
      upgrade-phase: "1"
    taints:
    - key: "services-only"
      value: "true"
      effect: "NoSchedule"
```

### Rolling Update Strategy
```bash
# Update in batches of 200 nodes
for batch in {1..5}; do
  echo "Upgrading CPU batch $batch"
  gcloud container node-pools upgrade cpu-services-pool \
    --cluster=ai-ml-cluster \
    --zone=us-central1-a \
    --batch-size=200 \
    --max-surge=50 \
    --max-unavailable=20
  
  # Wait for batch completion
  kubectl wait --for=condition=Ready nodes -l upgrade-batch=$batch --timeout=600s
done
```

## Phase 2: T4 Development Nodes (500 nodes)
**Duration: 1-2 days** | **Risk: Low-Medium**

### Objective
Upgrade development environment with minimal developer disruption.

### Pre-Phase Actions
```bash
# Notify development teams
kubectl create configmap dev-maintenance \
  --from-literal=message="T4 development nodes upgrading. Please save work and expect brief interruptions."

# Identify active development workloads
kubectl get pods -l workload-type=development --all-namespaces
```

### Upgrade Approach
```bash
# Cordon development nodes in batches
kubectl get nodes -l accelerator=nvidia-tesla-t4 | head -100 | xargs kubectl cordon

# Graceful workload migration
kubectl get pods -l workload-type=development -o wide | grep t4-node | \
  xargs -I {} kubectl delete pod {} --grace-period=300

# Upgrade batch
gcloud container node-pools upgrade t4-dev-pool \
  --cluster=ai-ml-cluster \
  --batch-size=100 \
  --max-surge=25 \
  --max-unavailable=50
```

### Validation Script
```bash
#!/bin/bash
# validate-t4-upgrade.sh
echo "Validating T4 node functionality..."

kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: t4-validation-job
spec:
  template:
    spec:
      nodeSelector:
        accelerator: nvidia-tesla-t4
      containers:
      - name: gpu-test
        image: nvidia/cuda:11.8-runtime-ubuntu20.04
        command: ["nvidia-smi"]
        resources:
          limits:
            nvidia.com/gpu: 1
      restartPolicy: Never
EOF

kubectl wait --for=condition=complete job/t4-validation-job --timeout=300s
```

## Phase 3: A100 Inference Nodes (1,500 nodes)
**Duration: 3-4 days** | **Risk: High**

### Objective
Maintain inference availability while upgrading production serving infrastructure.

### High-Availability Strategy
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inference-service
spec:
  replicas: 6  # Increased from normal 4 during upgrade
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
      maxSurge: 2
  template:
    spec:
      nodeSelector:
        accelerator: nvidia-tesla-a100
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
          - labelSelector:
              matchExpressions:
              - key: app
                operator: In
                values: ["inference-service"]
            topologyKey: kubernetes.io/hostname
```

### Blue-Green Node Pool Strategy
```bash
# Create new A100 node pool with v1.32
gcloud container node-pools create a100-inference-v132 \
  --cluster=ai-ml-cluster \
  --machine-type=a2-highgpu-1g \
  --accelerator=type=nvidia-tesla-a100,count=1 \
  --num-nodes=300 \
  --enable-autoscaling \
  --min-nodes=300 \
  --max-nodes=1500 \
  --node-version=1.32 \
  --node-labels=pool-version=v132,workload-type=inference

# Gradual traffic shifting
kubectl patch deployment inference-service -p '{"spec":{"template":{"spec":{"nodeSelector":{"pool-version":"v132"}}}}}'
```

### Load Balancer Health Checks
```yaml
apiVersion: v1
kind: Service
metadata:
  name: inference-lb
  annotations:
    cloud.google.com/load-balancer-type: "External"
    service.alpha.kubernetes.io/tolerate-unready-endpoints: "true"
spec:
  type: LoadBalancer
  sessionAffinity: None
  ports:
  - port: 80
    targetPort: 8080
    protocol: TCP
  selector:
    app: inference-service
  # Health check configuration
  healthCheckNodePort: 32000
```

### Monitoring During Upgrade
```bash
# Real-time inference monitoring
kubectl top nodes -l accelerator=nvidia-tesla-a100
watch "kubectl get pods -l app=inference-service -o wide"

# Performance validation
curl -X POST http://inference-lb/health \
  -H "Content-Type: application/json" \
  -d '{"test": "upgrade-validation"}'
```

## Phase 4: H100 Training Nodes (2,000 nodes)
**Duration: 5-7 days** | **Risk: Critical**

### Objective
Minimize training job disruption through careful orchestration and checkpointing.

### Training Job Assessment
```bash
# Identify long-running training jobs
kubectl get jobs --all-namespaces -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.startTime}{"\t"}{.status.active}{"\n"}{end}' | \
  awk '$3 > 0 {print $1}'

# Check checkpoint status
kubectl logs -l job-name=training-job --tail=100 | grep -i checkpoint
```

### Maintenance Windows Strategy
```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: training-checkpoint-trigger
spec:
  schedule: "0 2 * * *"  # 2 AM daily
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: checkpoint-trigger
            image: kubectl:latest
            command:
            - /bin/sh
            - -c
            - |
              # Signal training jobs to checkpoint
              kubectl annotate jobs -l workload-type=training \
                checkpoint.ai/trigger="$(date -Iseconds)"
```

### Cluster-Aware Training Migration
```python
# training-migration-controller.py
import kubernetes
from kubernetes import client, config

def migrate_training_workload(job_name, source_nodes, target_nodes):
    """Migrate training job between node pools"""
    
    # Save checkpoint
    trigger_checkpoint(job_name)
    
    # Wait for checkpoint completion
    wait_for_checkpoint_complete(job_name)
    
    # Update job node selector
    patch_job_node_selector(job_name, target_nodes)
    
    # Restart job on new nodes
    restart_job_from_checkpoint(job_name)

def staged_h100_upgrade():
    """Upgrade H100 nodes in stages"""
    h100_batches = get_h100_node_batches(batch_size=400)
    
    for batch_num, nodes in enumerate(h100_batches):
        print(f"Processing H100 batch {batch_num + 1}")
        
        # Move workloads off batch nodes
        migrate_workloads_from_nodes(nodes)
        
        # Upgrade batch
        upgrade_node_batch(nodes, "1.32")
        
        # Validate batch
        validate_h100_batch(nodes)
        
        # Allow workloads back
        enable_scheduling_on_nodes(nodes)
```

### Multi-Node Training Considerations
```yaml
apiVersion: kubeflow.org/v1
kind: PyTorchJob
metadata:
  name: distributed-training
spec:
  pytorchReplicaSpecs:
    Master:
      replicas: 1
      template:
        spec:
          nodeSelector:
            accelerator: nvidia-tesla-h100
            upgrade-status: "completed"  # Only use upgraded nodes
    Worker:
      replicas: 16
      template:
        spec:
          nodeSelector:
            accelerator: nvidia-tesla-h100
            upgrade-status: "completed"
          # Anti-affinity to spread across upgraded nodes
          affinity:
            podAntiAffinity:
              preferredDuringSchedulingIgnoredDuringExecution:
              - weight: 100
                podAffinityTerm:
                  labelSelector:
                    matchExpressions:
                    - key: job-name
                      operator: In
                      values: ["distributed-training"]
                  topologyKey: kubernetes.io/hostname
```

## Rollback Strategy

### Automated Rollback Triggers
```bash
#!/bin/bash
# rollback-monitor.sh

FAILURE_THRESHOLD=10
CURRENT_FAILURES=0

while true; do
  # Check node health
  UNHEALTHY_NODES=$(kubectl get nodes --no-headers | grep NotReady | wc -l)
  
  # Check GPU availability
  GPU_FAILURES=$(kubectl describe nodes | grep "nvidia.com/gpu: 0" | wc -l)
  
  # Check training job failures
  JOB_FAILURES=$(kubectl get jobs --all-namespaces -o jsonpath='{.items[?(@.status.failed>0)].metadata.name}' | wc -w)
  
  TOTAL_FAILURES=$((UNHEALTHY_NODES + GPU_FAILURES + JOB_FAILURES))
  
  if [ $TOTAL_FAILURES -gt $FAILURE_THRESHOLD ]; then
    echo "Failure threshold exceeded. Initiating rollback..."
    ./initiate-rollback.sh
    break
  fi
  
  sleep 30
done
```

### Quick Rollback Procedure
```bash
#!/bin/bash
# initiate-rollback.sh

echo "EMERGENCY ROLLBACK INITIATED"

# Identify problematic node pools
FAILED_POOLS=$(gcloud container node-pools list --cluster=ai-ml-cluster --filter="version=1.32 AND status!=RUNNING")

for pool in $FAILED_POOLS; do
  echo "Rolling back node pool: $pool"
  
  # Create emergency node pool with v1.31
  gcloud container node-pools create "${pool}-rollback" \
    --cluster=ai-ml-cluster \
    --node-version=1.31 \
    --num-nodes=10 \
    --enable-autoscaling
  
  # Migrate critical workloads
  kubectl get pods -o wide | grep $pool | \
    xargs kubectl delete pod --grace-period=60
done

# Alert stakeholders
kubectl create event rollback-initiated --message="Automated rollback initiated due to upgrade failures"
```

## Validation and Testing

### Comprehensive Test Suite
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: upgrade-test-suite
data:
  test-runner.sh: |
    #!/bin/bash
    
    echo "Running post-upgrade validation..."
    
    # Test 1: GPU Functionality
    kubectl apply -f gpu-test-job.yaml
    kubectl wait --for=condition=complete job/gpu-test --timeout=300s
    
    # Test 2: Training Job
    kubectl apply -f sample-training-job.yaml
    kubectl wait --for=condition=complete job/sample-training --timeout=600s
    
    # Test 3: Inference Service
    kubectl rollout restart deployment/inference-service
    kubectl rollout status deployment/inference-service --timeout=300s
    
    # Test 4: Multi-node Communication
    kubectl apply -f distributed-test-job.yaml
    kubectl wait --for=condition=complete job/distributed-test --timeout=900s
    
    # Test 5: Storage Performance
    kubectl apply -f storage-benchmark-job.yaml
    kubectl wait --for=condition=complete job/storage-benchmark --timeout=600s
    
    echo "All validation tests completed successfully"
```

## Timeline Summary

| Phase | Duration | Nodes | Risk Level | Key Activities |
|-------|----------|--------|------------|----------------|
| **Phase 1** | 2-3 days | 1,000 CPU | Low | Services upgrade, monitoring setup |
| **Phase 2** | 1-2 days | 500 T4 | Low-Medium | Development environment upgrade |
| **Phase 3** | 3-4 days | 1,500 A100 | High | Blue-green inference upgrade |
| **Phase 4** | 5-7 days | 2,000 H100 | Critical | Training workload migration |
| **Total** | **11-16 days** | **5,000** | | Full fleet upgraded |

## Success Criteria
- ✅ Zero training job data loss
- ✅ <2% inference availability impact
- ✅ All GPU workloads functional post-upgrade
- ✅ <5% performance regression
- ✅ Successful rollback capability maintained

This plan ensures your critical AI/ML workloads remain operational while systematically upgrading your entire 5,000-node GKE fleet.
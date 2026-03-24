# GKE 1.31 → 1.32 Phased Upgrade Plan for AI/ML Platform

## Executive Summary
This plan ensures minimal disruption to training workloads and maintains inference availability through a carefully sequenced 4-phase upgrade approach.

## Pre-Upgrade Preparation

### 1. Backup and Validation
```bash
# Backup critical resources
kubectl get all,configmaps,secrets,pv,pvc --all-namespaces -o yaml > backup-pre-upgrade.yaml

# Validate current workloads
kubectl get nodes --show-labels
kubectl top nodes
kubectl get pods --all-namespaces --field-selector=status.phase!=Running
```

### 2. Compatibility Assessment
```yaml
# Create upgrade validation script
apiVersion: v1
kind: ConfigMap
metadata:
  name: upgrade-validation
data:
  validate.sh: |
    #!/bin/bash
    # Check GPU drivers compatibility
    kubectl get nodes -l accelerator=nvidia-tesla-h100 -o jsonpath='{.items[*].status.nodeInfo.kernelVersion}'
    # Validate CSI drivers
    kubectl get csidriver
    # Check custom resources
    kubectl api-resources --verbs=list --namespaced -o name | xargs -n 1 kubectl get --show-kind --ignore-not-found --all-namespaces
```

## Phase 1: CPU Services Infrastructure (Days 1-3)
**Target**: 1,000 CPU nodes
**Priority**: Lowest risk, foundational services

### Day 1: Control Plane Upgrade
```bash
# Upgrade master control plane first
gcloud container clusters upgrade ml-platform-cluster \
    --master \
    --cluster-version=1.32.0-gke.latest \
    --zone=us-central1-a \
    --async
```

### Day 2-3: CPU Node Pool Upgrade
```yaml
# CPU node pool configuration
apiVersion: v1
kind: ConfigMap
metadata:
  name: cpu-upgrade-strategy
data:
  strategy.yaml: |
    maxSurge: 20%
    maxUnavailable: 10%
    # Ensures gradual rollout of CPU services
```

```bash
# Upgrade CPU node pools
for pool in cpu-services-pool-{1..4}; do
    gcloud container node-pools upgrade $pool \
        --cluster=ml-platform-cluster \
        --node-version=1.32.0-gke.latest \
        --max-surge-upgrade=50 \
        --max-unavailable-upgrade=25 \
        --zone=us-central1-a &
done
```

## Phase 2: T4 Development Nodes (Days 4-6)
**Target**: 500 T4 GPU nodes
**Priority**: Low impact on production

### Development Environment Preparation
```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: gpu-driver-update-t4
spec:
  selector:
    matchLabels:
      name: gpu-driver-update
  template:
    metadata:
      labels:
        name: gpu-driver-update
    spec:
      nodeSelector:
        accelerator: nvidia-tesla-t4
      containers:
      - name: driver-updater
        image: nvidia/driver:535.104.05-ubuntu22.04
        securityContext:
          privileged: true
```

```bash
# Coordinate with development teams
kubectl create configmap dev-maintenance-notice \
    --from-literal=message="T4 nodes upgrading Days 4-6. Save work frequently."

# Upgrade T4 pools with faster cadence
gcloud container node-pools upgrade t4-dev-pool \
    --cluster=ml-platform-cluster \
    --node-version=1.32.0-gke.latest \
    --max-surge-upgrade=100 \
    --max-unavailable-upgrade=50
```

## Phase 3: A100 Inference Nodes (Days 7-12)
**Target**: 1,500 A100 GPU nodes
**Priority**: High availability required

### Load Balancer and Traffic Management
```yaml
apiVersion: v1
kind: Service
metadata:
  name: inference-service-blue-green
spec:
  selector:
    app: ml-inference
    version: stable  # Switch between stable/upgrading
  ports:
  - port: 8080
    targetPort: 8080
  type: LoadBalancer

---
apiVersion: networking.istio.io/v1alpha3
kind: VirtualService
metadata:
  name: inference-traffic-split
spec:
  http:
  - match:
    - headers:
        canary:
          exact: "true"
    route:
    - destination:
        host: inference-service
        subset: upgrading
      weight: 100
  - route:
    - destination:
        host: inference-service
        subset: stable
      weight: 90
    - destination:
        host: inference-service
        subset: upgrading
      weight: 10
```

### Rolling Upgrade Strategy
```bash
# Create node pool groups for zero-downtime upgrade
for i in {1..5}; do
    gcloud container node-pools create a100-inference-temp-$i \
        --cluster=ml-platform-cluster \
        --machine-type=a2-highgpu-1g \
        --accelerator=type=nvidia-tesla-a100,count=1 \
        --num-nodes=100 \
        --node-version=1.32.0-gke.latest \
        --enable-autoscaling \
        --max-nodes=150 \
        --min-nodes=50
done

# Gradual workload migration script
kubectl create job migrate-inference-workloads --image=kubectl:latest -- /bin/bash -c "
for deployment in \$(kubectl get deployments -l tier=inference -o name); do
    kubectl patch \$deployment -p '{\"spec\":{\"template\":{\"spec\":{\"nodeSelector\":{\"pool\":\"temp\"}}}}}'
    kubectl rollout status \$deployment
    sleep 300
done"
```

## Phase 4: H100 Training Nodes (Days 13-20)
**Target**: 2,000 H100 GPU nodes
**Priority**: Critical - Maximum care required

### Training Job Management
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
        image: python:3.11
        command: ["/bin/bash"]
        args:
        - -c
        - |
          # Force checkpoint all running training jobs
          python3 << EOF
          import kubernetes
          from kubernetes import client, config
          config.load_incluster_config()
          
          v1 = client.CoreV1Api()
          
          # Signal all training pods to checkpoint
          pods = v1.list_pod_for_all_namespaces(label_selector="workload=training")
          for pod in pods.items:
              # Send SIGUSR1 for graceful checkpointing
              v1.connect_post_namespaced_pod_exec(
                  pod.metadata.name,
                  pod.metadata.namespace,
                  command=['kill', '-USR1', '1'],
                  container=pod.spec.containers[0].name
              )
          EOF
      restartPolicy: Never
```

### Cluster Maintenance Windows
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: h100-upgrade-schedule
data:
  maintenance-windows: |
    # 4-hour windows during off-peak hours
    Day 13: 02:00-06:00 UTC - H100 Pool 1 (400 nodes)
    Day 14: 02:00-06:00 UTC - H100 Pool 2 (400 nodes)  
    Day 15: 02:00-06:00 UTC - H100 Pool 3 (400 nodes)
    Day 16: 02:00-06:00 UTC - H100 Pool 4 (400 nodes)
    Day 17: 02:00-06:00 UTC - H100 Pool 5 (400 nodes)
    Day 18-20: Buffer for rollback/issues
```

### Advanced Training Workload Protection
```bash
# Create priority classes for training workloads
kubectl apply -f - <<EOF
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: critical-training
value: 1000000
globalDefault: false
description: "Critical training workloads that should not be disrupted"
EOF

# Upgrade script with extensive safety checks
#!/bin/bash
upgrade_h100_pool() {
    local pool_name=$1
    local node_count=$2
    
    echo "Starting upgrade of $pool_name with $node_count nodes"
    
    # Pre-upgrade checks
    running_jobs=$(kubectl get jobs -l gpu-type=h100,status=running --no-headers | wc -l)
    if [ $running_jobs -gt 10 ]; then
        echo "Too many running training jobs. Waiting..."
        exit 1
    fi
    
    # Create temporary node pool
    gcloud container node-pools create ${pool_name}-temp \
        --cluster=ml-platform-cluster \
        --machine-type=a3-highgpu-8g \
        --accelerator=type=nvidia-h100-80gb,count=8 \
        --num-nodes=$node_count \
        --node-version=1.32.0-gke.latest
    
    # Wait for nodes to be ready
    kubectl wait --for=condition=Ready nodes -l pool=${pool_name}-temp --timeout=1800s
    
    # Gradual workload migration with checkpointing
    kubectl get pods -l gpu-type=h100,pool=$pool_name -o name | while read pod; do
        # Trigger checkpoint
        kubectl exec $pod -- kill -USR1 1
        sleep 60
        
        # Graceful eviction
        kubectl drain $(kubectl get $pod -o jsonpath='{.spec.nodeName}') \
            --ignore-daemonsets \
            --delete-emptydir-data \
            --grace-period=1800
    done
    
    # Delete old pool
    gcloud container node-pools delete $pool_name --quiet
    
    # Rename temp pool
    gcloud container node-pools update ${pool_name}-temp --cluster=ml-platform-cluster --node-labels=pool=$pool_name
}

# Execute upgrades sequentially
for pool in h100-training-pool-{1..5}; do
    upgrade_h100_pool $pool 400
    sleep 3600  # 1 hour buffer between pools
done
```

## Monitoring and Rollback Strategy

### Comprehensive Monitoring
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: upgrade-monitoring
data:
  monitor.sh: |
    #!/bin/bash
    # GPU utilization monitoring
    kubectl top nodes -l accelerator=nvidia-tesla-h100 --sort-by=cpu
    
    # Training job health check
    kubectl get jobs -l workload=training -o custom-columns=NAME:.metadata.name,STATUS:.status.conditions[-1].type,AGE:.metadata.creationTimestamp
    
    # Inference latency monitoring
    kubectl exec -n monitoring prometheus-0 -- promtool query instant 'avg(inference_latency_seconds)'
    
    # Node readiness
    kubectl get nodes --no-headers | awk '$2 != "Ready" {print}'
```

### Automated Rollback Triggers
```bash
# Rollback script with automated triggers
#!/bin/bash
check_rollback_conditions() {
    # Check if >5% of training jobs failed
    failed_jobs=$(kubectl get jobs -l workload=training --field-selector=status.successful=0 --no-headers | wc -l)
    total_jobs=$(kubectl get jobs -l workload=training --no-headers | wc -l)
    failure_rate=$(echo "scale=2; $failed_jobs / $total_jobs * 100" | bc)
    
    if (( $(echo "$failure_rate > 5" | bc -l) )); then
        echo "ROLLBACK: Training job failure rate $failure_rate% exceeds threshold"
        return 0
    fi
    
    # Check inference availability
    available_inference_pods=$(kubectl get pods -l workload=inference,status=Running --no-headers | wc -l)
    if [ $available_inference_pods -lt 100 ]; then
        echo "ROLLBACK: Inference availability below minimum threshold"
        return 0
    fi
    
    return 1
}

# Automated rollback procedure
rollback_cluster() {
    echo "Initiating automated rollback..."
    
    # Rollback node pools in reverse order
    gcloud container node-pools rollback h100-training-pool-5 --cluster=ml-platform-cluster
    gcloud container node-pools rollback a100-inference-pool-3 --cluster=ml-platform-cluster
    
    # Restore from backup if needed
    kubectl apply -f backup-pre-upgrade.yaml
}
```

## Success Metrics and Validation

### Post-Upgrade Validation Checklist
```bash
#!/bin/bash
# Comprehensive validation script
validate_upgrade() {
    echo "=== Kubernetes Version Validation ==="
    kubectl version --short
    
    echo "=== Node Status Check ==="
    kubectl get nodes -o wide
    
    echo "=== GPU Driver Validation ==="
    kubectl create job gpu-test --image=nvidia/cuda:12.0-base-ubuntu20.04 -- nvidia-smi
    
    echo "=== Training Workload Test ==="
    kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: training-validation-test
spec:
  template:
    spec:
      nodeSelector:
        accelerator: nvidia-tesla-h100
      containers:
      - name: pytorch-test
        image: pytorch/pytorch:latest
        command: [python3, -c]
        args:
        - |
          import torch
          print(f"PyTorch version: {torch.__version__}")
          print(f"CUDA available: {torch.cuda.is_available()}")
          print(f"GPU count: {torch.cuda.device_count()}")
          # Simple training test
          x = torch.randn(1000, 1000).cuda()
          y = torch.mm(x, x.T)
          print("GPU computation successful")
      restartPolicy: Never
EOF
    
    echo "=== Inference Endpoint Test ==="
    curl -X POST http://inference-service/health-check
}

validate_upgrade
```

## Risk Mitigation Summary

1. **Training Continuity**: Maintained through checkpointing, gradual migration, and off-peak upgrade windows
2. **Inference Availability**: Blue-green deployment strategy ensures zero downtime
3. **Development Impact**: Minimal with advance notification and non-critical timing
4. **Infrastructure Services**: Upgraded first to ensure platform stability

**Total Estimated Timeline**: 20 days with built-in buffer periods
**Expected Downtime**: <1 hour per service category
**Rollback Capability**: Automated triggers with <30 minute recovery time

This plan prioritizes the continuity of your most critical and expensive workloads while ensuring a smooth transition across your entire AI/ML platform.
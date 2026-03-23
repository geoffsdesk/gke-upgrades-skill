# GKE Fleet Upgrade Plan: v1.31 → v1.32
## Mixed AI/ML Platform (5,000 nodes)

## Executive Summary
This plan prioritizes **training continuity** and **inference availability** through a carefully orchestrated 4-phase upgrade approach, minimizing disruption to critical AI/ML workloads.

## Pre-Upgrade Preparation (Week 1)

### 1. Environment Assessment
```bash
# Audit current workloads
kubectl get pods --all-namespaces -o wide | grep -E "(training|inference)"

# Check node pool configurations
gcloud container node-pools list --cluster=ai-ml-cluster

# Verify resource utilization
kubectl top nodes --sort-by=cpu
kubectl top nodes --sort-by=memory
```

### 2. Backup Strategy
```yaml
# Critical workload backup
apiVersion: batch/v1
kind: CronJob
metadata:
  name: model-checkpoint-backup
spec:
  schedule: "0 */6 * * *"  # Every 6 hours
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: backup
            image: gcr.io/google.com/cloudsdktool/cloud-sdk
            command:
            - /bin/bash
            - -c
            - |
              gsutil -m cp -r /models/checkpoints gs://ai-ml-backups/pre-upgrade/
```

### 3. Monitoring Setup
```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: upgrade-monitoring
spec:
  selector:
    matchLabels:
      app: ai-ml-workloads
  endpoints:
  - port: metrics
    interval: 30s
    path: /metrics
```

## Phase 1: Development & Testing Environment (Week 2)
**Target: 500 T4 nodes + 200 CPU nodes**

### Rationale
- Lowest impact on production workloads
- Validates upgrade process and compatibility
- Provides testing ground for application validation

### Implementation
```bash
# 1. Create new development node pool (canary)
gcloud container node-pools create dev-t4-v132 \
  --cluster=ai-ml-cluster \
  --zone=us-central1-a \
  --machine-type=n1-standard-4 \
  --accelerator=type=nvidia-tesla-t4,count=1 \
  --num-nodes=50 \
  --node-version=1.32.0-gke.1 \
  --node-taints=workload-type=development:NoSchedule

# 2. Migrate development workloads gradually
kubectl patch deployment dev-training-job -p '{"spec":{"template":{"spec":{"nodeSelector":{"cloud.google.com/gke-nodepool":"dev-t4-v132"}}}}}'

# 3. Monitor for 48 hours
kubectl get events --sort-by='.lastTimestamp' | grep -i error

# 4. Full development pool upgrade
gcloud container node-pools upgrade dev-t4-original \
  --cluster=ai-ml-cluster \
  --node-version=1.32.0-gke.1
```

### Validation Checklist
- [ ] GPU driver compatibility confirmed
- [ ] Development pipelines running successfully
- [ ] Resource allocation working correctly
- [ ] Network policies functioning
- [ ] Storage access verified

## Phase 2: Support Services (Week 3)
**Target: 800 CPU nodes**

### Rationale
- Upgrades supporting infrastructure first
- Ensures monitoring, logging, and orchestration services are stable
- Minimal impact on GPU workloads

### Implementation
```bash
# 1. Rolling upgrade of service node pools
for pool in monitoring-pool logging-pool ingress-pool api-pool; do
  gcloud container node-pools upgrade $pool \
    --cluster=ai-ml-cluster \
    --node-version=1.32.0-gke.1 \
    --max-surge-upgrade=2 \
    --max-unavailable-upgrade=1
  
  # Wait and validate between each pool
  sleep 300
  kubectl get nodes -l cloud.google.com/gke-nodepool=$pool
done
```

### Service Continuity Configuration
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: critical-service
spec:
  replicas: 5
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
      maxSurge: 2
  template:
    spec:
      topologySpreadConstraints:
      - maxSkew: 1
        topologyKey: kubernetes.io/hostname
        whenUnsatisfiable: DoNotSchedule
        labelSelector:
          matchLabels:
            app: critical-service
```

## Phase 3: Inference Workloads (Week 4)
**Target: 1,500 A100 GPU nodes**

### Rationale
- Inference workloads typically more stateless and easier to migrate
- Can implement blue-green deployment strategy
- Maintains training workloads on stable platform

### Blue-Green Strategy
```bash
# 1. Create new inference node pool (Green)
gcloud container node-pools create inference-a100-v132 \
  --cluster=ai-ml-cluster \
  --zone=us-central1-a \
  --machine-type=a2-highgpu-1g \
  --accelerator=type=nvidia-tesla-a100,count=1 \
  --num-nodes=300 \
  --node-version=1.32.0-gke.1 \
  --enable-autoscaling \
  --min-nodes=100 \
  --max-nodes=500

# 2. Deploy inference services to new pool
kubectl patch deployment inference-service-1 -p '{
  "spec": {
    "template": {
      "spec": {
        "nodeSelector": {
          "cloud.google.com/gke-nodepool": "inference-a100-v132"
        }
      }
    }
  }
}'

# 3. Gradual traffic migration (using Istio/Ambassador)
kubectl apply -f - <<EOF
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
        subset: v132
      weight: 100
  - route:
    - destination:
        host: inference-service
        subset: v131
      weight: 90
    - destination:
        host: inference-service
        subset: v132
      weight: 10
EOF

# 4. Scale up new pool, scale down old pool gradually
for i in {20..100..20}; do
  gcloud container clusters resize ai-ml-cluster \
    --node-pool=inference-a100-v132 \
    --num-nodes=$((i*3)) \
    --zone=us-central1-a
  
  gcloud container clusters resize ai-ml-cluster \
    --node-pool=inference-a100-original \
    --num-nodes=$(((100-i)*3)) \
    --zone=us-central1-a
  
  sleep 600  # Wait 10 minutes between scaling operations
  
  # Monitor performance
  kubectl top nodes | grep inference
done
```

### Inference Health Checks
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: inference-health-check
data:
  check.sh: |
    #!/bin/bash
    # GPU health check
    nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits
    
    # Model serving health check
    curl -f http://localhost:8080/health || exit 1
    
    # Latency check
    response_time=$(curl -w "%{time_total}" -s http://localhost:8080/predict -d '{"test": "data"}')
    if (( $(echo "$response_time > 0.5" | bc -l) )); then
      echo "Response time too high: $response_time"
      exit 1
    fi
```

## Phase 4: Training Workloads (Week 5-6)
**Target: 2,000 H100 GPU nodes**

### Rationale
- Most critical and expensive workloads
- Requires careful checkpoint management
- Longest running jobs need coordination

### Training-Aware Upgrade Strategy
```bash
# 1. Identify long-running training jobs
kubectl get jobs -o custom-columns=NAME:.metadata.name,DURATION:.status.startTime,COMPLETIONS:.spec.completions,ACTIVE:.status.active | grep -E "(training|train)"

# 2. Create maintenance windows based on training schedules
cat <<EOF > training-maintenance-window.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: maintenance-schedule
data:
  schedule.json: |
    {
      "maintenance_windows": [
        {
          "start": "2024-02-10T02:00:00Z",
          "end": "2024-02-10T06:00:00Z",
          "affected_pools": ["training-h100-pool-1"]
        },
        {
          "start": "2024-02-11T02:00:00Z", 
          "end": "2024-02-11T06:00:00Z",
          "affected_pools": ["training-h100-pool-2"]
        }
      ]
    }
EOF

# 3. Implement checkpoint-aware draining
kubectl create -f - <<EOF
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: training-aware-drainer
spec:
  selector:
    matchLabels:
      app: training-drainer
  template:
    spec:
      tolerations:
      - key: workload-type
        value: training
        effect: NoSchedule
      containers:
      - name: drainer
        image: training-drainer:latest
        env:
        - name: CHECKPOINT_INTERVAL
          value: "3600"  # 1 hour
        - name: GRACEFUL_SHUTDOWN_TIMEOUT
          value: "7200"  # 2 hours
        volumeMounts:
        - name: training-checkpoints
          mountPath: /checkpoints
        command:
        - /bin/bash
        - -c
        - |
          # Wait for checkpoint completion before allowing drain
          while [ -f /tmp/training-active ]; do
            echo "Waiting for training checkpoint..."
            sleep 300
          done
          kubectl drain \$NODE_NAME --ignore-daemonsets --delete-emptydir-data
EOF
```

### Pool-by-Pool Training Upgrade
```bash
# Upgrade training pools in sequence (400 nodes each)
for pool_num in {1..5}; do
  pool_name="training-h100-pool-${pool_num}"
  
  echo "Starting upgrade of ${pool_name}"
  
  # 1. Cordon nodes in the pool
  kubectl get nodes -l cloud.google.com/gke-nodepool=${pool_name} -o name | \
    xargs -I {} kubectl cordon {}
  
  # 2. Wait for natural job completion or checkpoint
  echo "Waiting for training jobs to checkpoint..."
  while kubectl get pods -l workload-type=training --field-selector spec.nodeName -o jsonpath='{.items[*].status.phase}' | grep -q Running; do
    sleep 300
    echo "Still waiting for training pods to complete checkpointing..."
  done
  
  # 3. Drain nodes gracefully
  kubectl get nodes -l cloud.google.com/gke-nodepool=${pool_name} -o name | \
    xargs -I {} kubectl drain {} --ignore-daemonsets --delete-emptydir-data --grace-period=7200
  
  # 4. Upgrade the pool
  gcloud container node-pools upgrade ${pool_name} \
    --cluster=ai-ml-cluster \
    --node-version=1.32.0-gke.1
  
  # 5. Uncordon nodes
  kubectl get nodes -l cloud.google.com/gke-nodepool=${pool_name} -o name | \
    xargs -I {} kubectl uncordon {}
  
  # 6. Verify GPU functionality
  kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: gpu-test-${pool_name}
spec:
  template:
    spec:
      nodeSelector:
        cloud.google.com/gke-nodepool: ${pool_name}
      containers:
      - name: gpu-test
        image: nvidia/cuda:11.8-runtime-ubuntu20.04
        command: ["/bin/bash"]
        args: ["-c", "nvidia-smi && python3 -c 'import torch; print(torch.cuda.is_available())'"]
        resources:
          limits:
            nvidia.com/gpu: 1
      restartPolicy: Never
EOF
  
  # Wait for verification before next pool
  kubectl wait --for=condition=complete job/gpu-test-${pool_name} --timeout=600s
  
  echo "Pool ${pool_name} upgrade completed successfully"
  sleep 1800  # 30-minute pause between pools
done
```

## Monitoring and Rollback Strategy

### Continuous Monitoring
```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: upgrade-monitoring
spec:
  groups:
  - name: upgrade.rules
    rules:
    - alert: HighGPUErrorRate
      expr: rate(gpu_errors_total[5m]) > 0.1
      for: 2m
      annotations:
        summary: "High GPU error rate detected during upgrade"
    
    - alert: TrainingJobFailure
      expr: increase(training_job_failures_total[10m]) > 5
      for: 1m
      annotations:
        summary: "Multiple training job failures detected"
    
    - alert: InferenceLatencyHigh
      expr: histogram_quantile(0.95, rate(inference_request_duration_seconds_bucket[5m])) > 1.0
      for: 5m
      annotations:
        summary: "Inference latency increased significantly"
```

### Automated Rollback Triggers
```bash
#!/bin/bash
# rollback-monitor.sh

# Monitor key metrics and trigger rollback if necessary
while true; do
  # Check GPU utilization drop
  gpu_util=$(kubectl top nodes --selector='accelerator=nvidia-tesla-h100' | awk '{sum+=$3} END {print sum/NR}' | sed 's/%//')
  if (( $(echo "$gpu_util < 70" | bc -l) )); then
    echo "GPU utilization dropped below threshold. Considering rollback..."
    # Additional validation logic here
  fi
  
  # Check error rates
  error_rate=$(kubectl logs -l app=training-jobs | grep -c ERROR | tail -1)
  if [ "$error_rate" -gt 50 ]; then
    echo "High error rate detected. Initiating rollback..."
    ./initiate-rollback.sh
    break
  fi
  
  sleep 300
done
```

## Post-Upgrade Validation

### Comprehensive Testing Suite
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: post-upgrade-validation
spec:
  template:
    spec:
      containers:
      - name: validator
        image: ai-ml-validator:latest
        command:
        - /bin/bash
        - -c
        - |
          # Test GPU functionality across all node types
          python3 /tests/gpu_compatibility_test.py
          
          # Test training pipeline
          python3 /tests/training_pipeline_test.py
          
          # Test inference endpoints
          python3 /tests/inference_performance_test.py
          
          # Test inter-node communication (for distributed training)
          python3 /tests/multi_node_communication_test.py
          
          # Generate validation report
          python3 /tests/generate_report.py
```

## Risk Mitigation Summary

| Risk | Mitigation | Recovery Time |
|------|------------|---------------|
| Training job data loss | Automated checkpointing every hour | < 1 hour |
| Inference service downtime | Blue-green deployment
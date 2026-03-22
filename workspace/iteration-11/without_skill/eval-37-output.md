# GKE Fleet Upgrade Plan: v1.31 → v1.32
## 5,000 Node Mixed AI/ML Platform

### Executive Summary
This phased upgrade plan prioritizes training continuity and inference availability while minimizing business disruption across your AI/ML workloads.

## Pre-Upgrade Preparation (Week -2 to -1)

### Infrastructure Readiness
```bash
# Backup critical configurations
kubectl get all --all-namespaces -o yaml > pre-upgrade-backup.yaml
kubectl get pvc --all-namespaces -o yaml > pvc-backup.yaml

# Verify cluster health
kubectl get nodes --no-headers | wc -l  # Should show 5,000
kubectl top nodes | grep NotReady       # Should be empty

# Check resource utilization
kubectl describe nodes | grep -A 5 "Allocated resources"
```

### Pre-upgrade Validation
- [ ] Backup all training checkpoints and model artifacts
- [ ] Document current workload distribution
- [ ] Test v1.32 compatibility in staging environment
- [ ] Verify GPU driver compatibility with new Kubernetes version
- [ ] Prepare rollback procedures for each node pool

## Phase 1: Foundation Services (Days 1-2)
**Target: 1,000 CPU nodes**
**Maintenance Window: Off-peak hours**

### Rationale
CPU nodes typically host supporting services (monitoring, logging, CI/CD) that can tolerate brief interruptions without affecting core ML workloads.

```yaml
# CPU Node Pool Upgrade Strategy
apiVersion: container.cnative.com/v1
kind: NodePool
metadata:
  name: cpu-services-pool
spec:
  upgradeSettings:
    maxSurge: 100
    maxUnavailable: 50
  strategy: rolling-update
```

### Execution Steps
```bash
# 1. Upgrade in batches of 200 nodes
gcloud container node-pools upgrade cpu-services-pool \
  --cluster=ml-platform-cluster \
  --node-pool=cpu-services-pool \
  --max-surge-upgrade=100 \
  --max-unavailable-upgrade=50

# 2. Monitor upgrade progress
kubectl get nodes -l node-pool=cpu-services -w

# 3. Validate services post-upgrade
kubectl get pods --all-namespaces --field-selector=spec.nodeName=<upgraded-node>
```

### Success Criteria
- [ ] All CPU nodes running v1.32
- [ ] Supporting services (Prometheus, Grafana, CI/CD) operational
- [ ] No impact on GPU workloads
- [ ] All PVCs accessible

## Phase 2: Development Environment (Days 3-4)
**Target: 500 T4 nodes**
**Maintenance Window: Extended (can handle longer disruption)**

### Rationale
Development workloads are typically more tolerant to interruption and can be rescheduled easily.

```yaml
# T4 Development Pool Configuration
apiVersion: v1
kind: ConfigMap
metadata:
  name: dev-upgrade-config
data:
  preStop: |
    #!/bin/bash
    # Save development work
    kubectl exec -it $(kubectl get pods -l tier=development -o name) -- /save-work.sh
```

### Execution Steps
```bash
# 1. Notify development teams
# 2. Drain development workloads gracefully
kubectl drain <t4-node> --ignore-daemonsets --delete-emptydir-data --grace-period=300

# 3. Upgrade T4 pool
gcloud container node-pools upgrade t4-dev-pool \
  --cluster=ml-platform-cluster \
  --max-surge-upgrade=50 \
  --max-unavailable-upgrade=25

# 4. Restore development environments
kubectl apply -f dev-workloads/
```

### Success Criteria
- [ ] All T4 nodes upgraded successfully
- [ ] Development Jupyter notebooks accessible
- [ ] GPU development tools functional
- [ ] No impact on production training/inference

## Phase 3: Inference Services (Days 5-8)
**Target: 1,500 A100 nodes**
**Maintenance Window: Rolling during low-traffic periods**

### Rationale
Inference services require high availability but can leverage load balancing and gradual traffic shifting during upgrades.

```yaml
# A100 Inference Pool - Blue/Green Strategy
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inference-service
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 25%
      maxSurge: 25%
```

### Execution Steps
```bash
# 1. Implement inference service redundancy
kubectl scale deployment inference-service --replicas=2000

# 2. Upgrade in small batches (100 nodes at a time)
for batch in {1..15}; do
  echo "Upgrading A100 batch $batch"
  
  # Select 100 nodes for upgrade
  NODES=$(kubectl get nodes -l node-pool=a100-inference --no-headers | \
          head -100 | awk '{print $1}')
  
  # Graceful drain with inference-aware timing
  for node in $NODES; do
    kubectl drain $node --grace-period=600 --ignore-daemonsets
  done
  
  # Wait for upgrade completion
  gcloud container node-pools upgrade a100-inference-pool \
    --node-locations=us-central1-a \
    --max-surge-upgrade=10 \
    --max-unavailable-upgrade=5
  
  # Validate inference capacity
  kubectl get pods -l app=inference-service -o wide | grep Running
  
  sleep 1800  # 30-minute stabilization period
done
```

### Monitoring During Upgrade
```bash
# Real-time inference metrics
kubectl get --raw "/apis/metrics.k8s.io/v1beta1/nodes" | \
  jq '.items[] | select(.metadata.name | contains("a100")) | 
     {name: .metadata.name, gpu_util: .usage.gpu}'

# Service availability check
curl -f http://inference-service/health || echo "Service degraded"
```

### Success Criteria
- [ ] <5% inference latency increase during upgrade
- [ ] No service downtime exceeding 30 seconds
- [ ] All A100 nodes operational on v1.32
- [ ] Model serving throughput maintained

## Phase 4: Training Infrastructure (Days 9-14)
**Target: 2,000 H100 nodes**
**Maintenance Window: Coordinated with ML teams**

### Rationale
Training workloads are the most sensitive but also the most predictable. Coordinate upgrades with natural training cycle boundaries.

```yaml
# H100 Training Pool - Checkpoint-Aware Strategy
apiVersion: batch/v1
kind: Job
metadata:
  name: pre-upgrade-checkpoint
spec:
  template:
    spec:
      containers:
      - name: checkpoint-saver
        image: ml-platform/checkpoint-tool:v2.1
        command: ["/bin/sh", "-c"]
        args:
        - |
          echo "Saving training checkpoints..."
          kubectl get pods -l workload=training -o json | \
          jq -r '.items[].metadata.name' | \
          xargs -I {} kubectl exec {} -- /save-checkpoint.sh
```

### Pre-Training Upgrade Protocol
```bash
# 1. Coordinate with ML teams for training schedules
# 2. Ensure all critical training jobs have recent checkpoints
kubectl get jobs -l priority=critical --all-namespaces

# 3. Implement training job migration strategy
cat > training-migration.yaml << EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: training-migration-config
data:
  migration-script: |
    #!/bin/bash
    # Graceful training job migration
    for job in $(kubectl get jobs -l tier=training -o name); do
      # Trigger checkpoint save
      kubectl patch $job -p '{"spec":{"template":{"metadata":{"annotations":{"checkpoint-trigger":"true"}}}}}'
      
      # Wait for checkpoint completion
      while ! kubectl logs $job | grep -q "Checkpoint saved"; do
        sleep 30
      done
      
      # Mark for migration
      kubectl label $job migration-ready=true
    done
EOF
```

### Execution Steps
```bash
# Phase 4A: Upgrade 500 H100 nodes (Days 9-10)
# Focus on non-critical training workloads first
BATCH_1_NODES=$(kubectl get nodes -l node-pool=h100-training,priority!=critical \
                --no-headers | head -500 | awk '{print $1}')

for node in $BATCH_1_NODES; do
  # Save training state
  kubectl exec -it $(kubectl get pods --field-selector=spec.nodeName=$node -o name) \
    -- /checkpoint-and-save.sh
  
  # Drain node
  kubectl drain $node --grace-period=1200 --ignore-daemonsets
done

# Upgrade batch 1
gcloud container node-pools upgrade h100-training-pool \
  --node-locations=us-central1-a,us-central1-b \
  --max-surge-upgrade=50 \
  --max-unavailable-upgrade=25

# Phase 4B-D: Remaining 1,500 nodes in 500-node batches
# (Repeat similar process for remaining nodes)
```

### Training Continuity Validation
```bash
# Monitor training job recovery
kubectl get jobs -l tier=training --watch

# Verify GPU utilization post-upgrade
nvidia-smi dmon -s pucvmet -d 10 -c 60

# Check training throughput
kubectl logs -l app=training-monitor --tail=100 | grep "samples/sec"
```

### Success Criteria
- [ ] <4 hours maximum training interruption per job
- [ ] All training jobs resumed from checkpoints
- [ ] GPU utilization returns to >85% within 2 hours
- [ ] No training data loss
- [ ] All H100 nodes operational on v1.32

## Post-Upgrade Validation (Days 15-16)

### Cluster-Wide Health Check
```bash
#!/bin/bash
# Comprehensive post-upgrade validation

echo "=== Node Status ==="
kubectl get nodes | grep -c Ready  # Should equal 5,000

echo "=== GPU Node Validation ==="
kubectl get nodes -l accelerator=nvidia-h100 | grep -c Ready    # Should equal 2,000
kubectl get nodes -l accelerator=nvidia-a100 | grep -c Ready    # Should equal 1,500
kubectl get nodes -l accelerator=nvidia-t4 | grep -c Ready      # Should equal 500

echo "=== Workload Status ==="
kubectl get pods --all-namespaces --field-selector=status.phase!=Running | wc -l  # Should be minimal

echo "=== Performance Metrics ==="
kubectl top nodes --sort-by=cpu | head -20
kubectl top nodes --sort-by=memory | head -20

echo "=== GPU Utilization ==="
kubectl exec -it $(kubectl get pods -l app=gpu-monitoring -o name | head -1) -- nvidia-smi
```

### Performance Validation
```bash
# Training performance benchmark
kubectl apply -f - << EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: post-upgrade-benchmark
spec:
  template:
    spec:
      nodeSelector:
        accelerator: nvidia-h100
      containers:
      - name: benchmark
        image: ml-platform/benchmark:v2.1
        resources:
          limits:
            nvidia.com/gpu: 8
        command: ["/run-training-benchmark.sh"]
EOF

# Inference latency test
kubectl apply -f - << EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inference-load-test
spec:
  replicas: 10
  selector:
    matchLabels:
      app: load-test
  template:
    metadata:
      labels:
        app: load-test
    spec:
      containers:
      - name: load-tester
        image: ml-platform/load-test:v1.5
        env:
        - name: TARGET_SERVICE
          value: "inference-service:8080"
        - name: CONCURRENT_REQUESTS
          value: "100"
EOF
```

## Rollback Procedures

### Emergency Rollback Protocol
```bash
# If critical issues are detected during any phase:

# 1. Immediate node pool rollback
gcloud container node-pools rollback <affected-pool> \
  --cluster=ml-platform-cluster

# 2. Restore from backup if needed
kubectl apply -f pre-upgrade-backup.yaml

# 3. Restore training checkpoints
kubectl create job checkpoint-restore \
  --image=ml-platform/restore:v1.0 \
  -- /restore-all-checkpoints.sh

# 4. Validate rollback success
kubectl get nodes -o wide | grep -v v1.32 | wc -l
```

## Risk Mitigation Strategies

### 1. Training Continuity
- **Checkpoint Frequency**: Increase checkpoint frequency 24 hours before upgrade
- **Multi-Region Backup**: Ensure training data and checkpoints replicated across regions
- **Priority Queuing**: Implement priority-based scheduling for critical training jobs

### 2. Inference Availability
- **Load Balancer Configuration**: Configure external load balancers to handle node rotation
- **Service Mesh**: Use Istio for intelligent traffic routing during upgrades
- **Auto-scaling**: Enable cluster autoscaler to handle capacity fluctuations

### 3. Data Protection
- **Persistent Volume Backup**: Snapshot all PVCs before upgrade
- **Database Replication**: Ensure metadata stores have real-time replicas
- **Artifact Registry**: Verify all model artifacts stored in external registry

## Monitoring and Alerting

### Upgrade Progress Dashboard
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: upgrade-monitoring
data:
  prometheus-rules: |
    groups:
    - name: kubernetes-upgrade
      rules:
      - alert: NodeUpgradeStalled
        expr: kube_node_info{kubelet_version!="v1.32.0"} > 0
        for: 30m
        labels:
          severity: warning
        annotations:
          summary: "Node upgrade appears stalled"
      
      - alert: GPUUtilizationDrop
        expr: nvidia_gpu_duty_cycle < 50
        for: 15m
        labels:
          severity: critical
        annotations:
          summary: "GPU utilization dropped significantly during upgrade"
      
      - alert: InferenceLatencyIncrease
        expr: histogram_quantile(0.95, inference_request_duration_seconds) > 2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Inference latency increased during upgrade"
```

## Timeline Summary

| Phase | Target | Duration | Risk Level | Business Impact |
|-------|--------|----------|------------|----------------|
| 1 | CPU Nodes (1,000) | 2 days | Low | Minimal |
| 2 | T4 Dev (500) | 2 days | Low | Development only |
| 3 | A100 Inference (1,500) | 4 days | Medium | Managed degradation |
| 4 | H100 Training (2,000) | 6 days | High | Planned interruption |
| Validation | All nodes | 2 days | Low | Performance verification |

**Total Duration**: 16 days
**Expected Downtime**: <30 seconds per service during rolling updates
**Training Interruption**: <4 hours per job with checkpoint recovery

This phased approach ensures minimal business impact while maintaining the high availability requirements of your AI/ML platform.
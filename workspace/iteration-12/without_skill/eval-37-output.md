# GKE Fleet Upgrade Plan: 1.31 → 1.32
## Mixed AI/ML Platform (5,000 nodes)

## Pre-Upgrade Assessment & Preparation

### 1. Infrastructure Audit
```bash
# Validate current state
kubectl get nodes --show-labels | grep -E "gpu|cpu" | wc -l
kubectl get pods --all-namespaces -o wide | grep -E "training|inference"

# Check resource utilization
kubectl top nodes --sort-by=cpu
kubectl top nodes --sort-by=memory
```

### 2. Backup & Safety Measures
- **Control Plane**: Automated GKE backup enabled
- **Persistent Volumes**: Snapshot all training data and model storage
- **Configuration**: Export all critical workload manifests
- **Monitoring**: Enhanced alerting during upgrade window

## Phased Upgrade Strategy

### Phase 1: CPU Services Nodes (1,000 nodes)
**Duration**: 2-3 days | **Risk**: Low | **Priority**: First

```yaml
# CPU node pool upgrade configuration
apiVersion: container.googleapis.com/v1
kind: NodePool
metadata:
  name: cpu-services-pool
spec:
  upgradeSettings:
    maxSurge: 50
    maxUnavailable: 10
  management:
    autoUpgrade: false
    autoRepair: true
```

**Execution Plan**:
- **Day 1**: Upgrade 500 nodes (50% capacity)
- **Day 2**: Upgrade remaining 500 nodes
- **Validation**: Ensure all microservices, monitoring, and support systems operational

### Phase 2: T4 Development Nodes (500 nodes)
**Duration**: 1 day | **Risk**: Low | **Priority**: Second

```yaml
# T4 development pool upgrade
apiVersion: container.googleapis.com/v1
kind: NodePool
metadata:
  name: t4-dev-pool
spec:
  upgradeSettings:
    maxSurge: 100  # Higher surge for dev environment
    maxUnavailable: 25
```

**Execution Plan**:
- **Maintenance Window**: Off-peak hours
- **Communication**: 48-hour advance notice to development teams
- **Rollback**: Ready if development workflows disrupted

### Phase 3: A100 Inference Nodes (1,500 nodes)
**Duration**: 3-4 days | **Risk**: Medium-High | **Priority**: Third

```yaml
# A100 inference pool - high availability focus
apiVersion: container.googleapis.com/v1
kind: NodePool
metadata:
  name: a100-inference-pool
spec:
  upgradeSettings:
    maxSurge: 25   # Conservative to maintain service levels
    maxUnavailable: 5
  strategy: "SURGE"  # Add nodes before removing old ones
```

**Execution Plan**:
- **Day 1**: Upgrade 375 nodes (25% capacity)
- **Day 2**: Upgrade 375 nodes (25% capacity)  
- **Day 3**: Upgrade 375 nodes (25% capacity)
- **Day 4**: Upgrade final 375 nodes (25% capacity)

**High Availability Measures**:
```yaml
# Inference service PDB
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: inference-pdb
spec:
  minAvailable: 80%
  selector:
    matchLabels:
      app: inference-service
```

### Phase 4: H100 Training Nodes (2,000 nodes)
**Duration**: 4-5 days | **Risk**: Highest | **Priority**: Last

```yaml
# H100 training pool - maximum protection
apiVersion: container.googleapis.com/v1
kind: NodePool
metadata:
  name: h100-training-pool
spec:
  upgradeSettings:
    maxSurge: 10   # Very conservative
    maxUnavailable: 2
  strategy: "SURGE"
```

**Execution Plan**:
- **Pre-upgrade**: Coordinate with ML teams for training job scheduling
- **Day 1**: Upgrade 200 nodes (10% capacity)
- **Day 2**: Upgrade 400 nodes (20% capacity)
- **Day 3**: Upgrade 600 nodes (30% capacity)
- **Day 4**: Upgrade 600 nodes (30% capacity)
- **Day 5**: Upgrade final 200 nodes (10% capacity)

## Critical Safeguards

### 1. Training Job Protection
```yaml
# Training workload management
apiVersion: batch/v1
kind: Job
metadata:
  name: training-checkpoint-manager
spec:
  template:
    spec:
      tolerations:
      - key: "upgrading"
        operator: "Equal"
        value: "true"
        effect: "NoSchedule"
      containers:
      - name: checkpoint-saver
        image: training-checkpoint:latest
        command: ["./save-checkpoint.sh"]
```

### 2. Inference SLA Maintenance
```yaml
# Inference availability requirements
apiVersion: v1
kind: Service
metadata:
  name: inference-lb
  annotations:
    service.beta.kubernetes.io/do-loadbalancer-healthcheck-path: "/health"
spec:
  type: LoadBalancer
  sessionAffinity: None
  ports:
  - port: 80
    targetPort: 8080
```

### 3. Monitoring & Alerting
```yaml
# Upgrade monitoring alerts
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: upgrade-monitoring
spec:
  groups:
  - name: upgrade.rules
    rules:
    - alert: HighNodeUpgradeFailure
      expr: increase(gke_node_upgrade_failures_total[5m]) > 5
      for: 2m
      labels:
        severity: critical
    - alert: InferenceLatencyHigh
      expr: histogram_quantile(0.95, inference_request_duration_seconds) > 2
      for: 5m
```

## Rollback Strategy

### Immediate Rollback Triggers
- **Training Jobs**: >10% job failure rate
- **Inference SLA**: Latency >2x baseline or availability <95%
- **Node Health**: >5% nodes in NotReady state
- **GPU Utilization**: Unexpected drops >20%

### Rollback Execution
```bash
# Emergency rollback commands
gcloud container node-pools rollback [POOL_NAME] \
    --cluster=[CLUSTER_NAME] \
    --zone=[ZONE]

# Workload migration
kubectl drain [NODE_NAME] --ignore-daemonsets --delete-emptydir-data
```

## Post-Upgrade Validation

### 1. Comprehensive Testing
```bash
# GPU functionality verification
kubectl apply -f gpu-test-workload.yaml
kubectl logs gpu-test-pod | grep "CUDA device count"

# Performance benchmarking
kubectl apply -f inference-load-test.yaml
kubectl apply -f training-benchmark.yaml
```

### 2. Success Metrics
- **Training Throughput**: Within 5% of baseline
- **Inference Latency**: P95 < 500ms
- **GPU Utilization**: >85% for active workloads
- **Node Health**: 100% Ready state
- **Workload Success Rate**: >99%

## Timeline Summary
- **Week 1**: Phase 1 (CPU) + Phase 2 (T4 Dev)
- **Week 2**: Phase 3 (A100 Inference)
- **Week 3**: Phase 4 (H100 Training)
- **Week 4**: Validation & optimization

**Total Duration**: 3-4 weeks
**Business Impact**: Minimized through careful sequencing and surge capacity

This plan prioritizes your most critical workloads (training continuity and inference availability) while providing multiple safety nets and rollback options at each phase.
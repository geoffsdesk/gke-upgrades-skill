# GKE Fleet Upgrade Plan: 1.31 → 1.32
## Mixed AI/ML Platform (5,000 nodes)

## Executive Summary
This phased upgrade plan prioritizes training continuity and inference availability while minimizing business impact. The strategy follows a **low-risk-first** approach, starting with development environments and gradually moving to production workloads.

## Pre-Upgrade Prerequisites

### 1. Control Plane Upgrade
```bash
# Upgrade control plane first (minimal downtime)
gcloud container clusters upgrade [CLUSTER-NAME] \
    --master \
    --cluster-version=1.32.x \
    --zone=[ZONE]
```

### 2. Backup & Validation
```bash
# Backup critical workloads
kubectl get all -A -o yaml > pre-upgrade-backup.yaml

# Validate GPU drivers compatibility
kubectl describe nodes -l accelerator=nvidia-tesla-h100 | grep -A5 "nvidia.com/gpu"
```

### 3. Monitoring Setup
- Deploy upgrade monitoring dashboards
- Set up alerting for node health and workload disruption
- Prepare rollback procedures

## Phase 1: Development Environment (Week 1)
**Target: 500 T4 Development Nodes**

### Rationale
- Lowest business impact
- Validates upgrade process
- Tests GPU driver compatibility

### Execution
```bash
# Create new T4 node pool with 1.32
gcloud container node-pools create t4-dev-132 \
    --cluster=[CLUSTER-NAME] \
    --machine-type=n1-standard-4 \
    --accelerator=type=nvidia-tesla-t4,count=1 \
    --num-nodes=100 \
    --enable-autoscaling \
    --min-nodes=50 \
    --max-nodes=150

# Gradually migrate dev workloads
kubectl drain [OLD-NODES] --ignore-daemonsets --delete-emptydir-data
```

### Success Criteria
- ✅ All dev workloads running on 1.32
- ✅ GPU drivers functional
- ✅ No performance regression
- ✅ Development teams confirm functionality

### Timeline: 3-4 days

---

## Phase 2: CPU Services Layer (Week 2)
**Target: 1,000 CPU Nodes**

### Rationale
- Foundation services must be stable before GPU upgrades
- Supports logging, monitoring, and orchestration
- No GPU driver dependencies

### Execution Strategy
**Blue-Green Deployment per Service Type:**

```bash
# Upgrade in batches of 200 nodes
for batch in {1..5}; do
    # Create new node pool
    gcloud container node-pools create cpu-services-132-batch-$batch \
        --cluster=[CLUSTER-NAME] \
        --machine-type=n2-standard-8 \
        --num-nodes=200
    
    # Migrate services with anti-affinity
    kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: critical-service
spec:
  template:
    spec:
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
            - matchExpressions:
              - key: kubernetes.io/version
                operator: In
                values: ["v1.32.x"]
EOF
done
```

### Service Priority Order
1. **Batch 1**: Monitoring, logging (Prometheus, Grafana, Fluentd)
2. **Batch 2**: Service mesh, ingress controllers
3. **Batch 3**: CI/CD pipelines
4. **Batch 4**: Storage controllers, backup services
5. **Batch 5**: Auxiliary services

### Timeline: 5-6 days

---

## Phase 3: A100 Inference Nodes (Week 3)
**Target: 1,500 A100 Inference Nodes**

### Rationale
- Critical for production inference
- Rolling upgrade to maintain availability
- SLA protection through staged deployment

### Execution Strategy
**Rolling Upgrade with Availability Zones:**

```bash
# Upgrade 300 nodes per day across AZs
for zone in us-central1-a us-central1-b us-central1-c; do
    # Create new A100 pool per zone
    gcloud container node-pools create a100-inf-132-$zone \
        --cluster=[CLUSTER-NAME] \
        --zone=$zone \
        --machine-type=a2-highgpu-1g \
        --accelerator=type=nvidia-tesla-a100,count=1 \
        --num-nodes=500 \
        --enable-autoscaling
done
```

### Deployment Configuration
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inference-service
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 10%
      maxSurge: 20%
  template:
    spec:
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
          - labelSelector:
              matchLabels:
                app: inference-service
            topologyKey: kubernetes.io/hostname
      nodeSelector:
        kubernetes.io/version: "v1.32.x"
        accelerator: nvidia-tesla-a100
```

### Monitoring & Validation
- Real-time inference latency monitoring
- Model serving availability checks
- GPU utilization metrics
- Customer traffic impact analysis

### Timeline: 5 days (300 nodes/day)

---

## Phase 4: H100 Training Nodes (Week 4)
**Target: 2,000 H100 Training Nodes**

### Rationale
- Highest priority for business continuity
- Most expensive infrastructure
- Requires coordination with ML teams

### Pre-Phase Coordination
```bash
# Identify long-running training jobs
kubectl get pods -l workload-type=training \
    --field-selector=status.phase=Running \
    -o custom-columns=NAME:.metadata.name,AGE:.status.startTime

# Coordinate with ML teams for job scheduling
```

### Execution Strategy
**Checkpoint-Aware Rolling Upgrade:**

```bash
# Create upgrade-friendly training job template
apiVersion: batch/v1
kind: Job
metadata:
  name: distributed-training
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
      - name: training
        command: ["/bin/bash", "-c"]
        args:
        - |
          # Auto-checkpoint on SIGTERM
          trap 'python save_checkpoint.py' TERM
          python train.py --resume-from-checkpoint
      tolerations:
      - key: "upgrade-in-progress"
        operator: "Exists"
        effect: "NoSchedule"
```

### Upgrade Process (400 nodes/day)
```bash
# Daily batch upgrade
for day in {1..5}; do
    echo "Day $day: Upgrading 400 H100 nodes"
    
    # Taint nodes for upcoming upgrade
    kubectl taint nodes -l batch=day-$day \
        upgrade-in-progress=true:NoSchedule
    
    # Wait for training jobs to checkpoint
    sleep 1800  # 30 minutes
    
    # Drain and upgrade
    kubectl drain -l batch=day-$day \
        --ignore-daemonsets \
        --delete-emptydir-data \
        --timeout=3600s
    
    # Create new H100 pool
    gcloud container node-pools create h100-train-132-day-$day \
        --machine-type=a3-highgpu-8g \
        --accelerator=type=nvidia-h100-80gb,count=8 \
        --num-nodes=50  # 400 nodes / 8 GPUs per node
done
```

### Training Job Management
- **Week before upgrade**: Notify ML teams of schedule
- **Day of upgrade**: Coordinate job scheduling windows
- **During upgrade**: Monitor checkpoint saves and restores
- **Post-upgrade**: Validate training resumption

### Timeline: 5 days (400 nodes/day)

---

## Risk Mitigation & Rollback Procedures

### Rollback Triggers
- GPU driver incompatibility
- >5% performance degradation
- Critical service unavailability >15 minutes
- Training job failure rate >10%

### Quick Rollback Process
```bash
# Emergency rollback script
#!/bin/bash
PHASE=$1  # t4-dev, cpu-services, a100-inf, h100-train

case $PHASE in
    "a100-inf"|"h100-train")
        # Immediate traffic redirect to old nodes
        kubectl patch service inference-service -p \
            '{"spec":{"selector":{"kubernetes.io/version":"v1.31.x"}}}'
        ;;
    "cpu-services")
        # Rollback critical services first
        kubectl rollout undo deployment/prometheus
        kubectl rollout undo deployment/ingress-controller
        ;;
esac
```

### Monitoring & Alerting
```yaml
# Critical alerts during upgrade
groups:
- name: upgrade-monitoring
  rules:
  - alert: NodeUpgradeStuck
    expr: kube_node_status_condition{condition="Ready",status="false"} > 0
    for: 10m
    
  - alert: GPUUtilizationDrop
    expr: nvidia_gpu_utilization < 0.8 * nvidia_gpu_utilization offset 1h
    for: 5m
    
  - alert: InferenceLatencyIncrease
    expr: inference_latency_p99 > 1.2 * inference_latency_p99 offset 1h
    for: 3m
```

## Resource Requirements & Cost Impact

### Temporary Additional Resources
- **Peak overlap**: ~30% additional nodes during blue-green phases
- **Estimated cost increase**: $50,000-75,000 during upgrade weeks
- **Network transfer**: Minimal (same cluster upgrades)

### Team Coordination
- **ML Engineering**: Training schedule coordination
- **Platform Engineering**: Upgrade execution
- **SRE**: Monitoring and incident response
- **DevOps**: CI/CD pipeline updates

## Success Metrics

### Technical KPIs
- Zero data loss during upgrade
- <2% inference availability impact
- <4 hours total training job disruption
- 100% successful node upgrades

### Business KPIs
- No customer-facing service disruptions
- Maintained SLA compliance
- No revenue impact from inference downtime

## Post-Upgrade Validation

### Comprehensive Testing
```bash
# GPU functionality validation
kubectl apply -f gpu-test-jobs.yaml
kubectl wait --for=condition=complete job/gpu-validation --timeout=600s

# Performance benchmarking
kubectl apply -f performance-benchmarks.yaml

# Model serving validation
curl -X POST https://inference-endpoint/v1/predict \
     -H "Content-Type: application/json" \
     -d @test-payload.json
```

This phased approach ensures minimal business disruption while maintaining the high availability requirements of your AI/ML platform. The upgrade can be completed within 4 weeks with proper coordination and monitoring.
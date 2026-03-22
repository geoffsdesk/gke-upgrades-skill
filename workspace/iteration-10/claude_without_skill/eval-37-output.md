# GKE Fleet Upgrade Plan: 1.31 → 1.32
## Mixed AI/ML Platform - 5,000 Node Fleet

## Executive Summary
This phased upgrade plan prioritizes **training continuity** and **inference availability** while minimizing business impact across your 5,000-node GKE fleet.

---

## Pre-Upgrade Preparation (Week 1)

### 1. Validation Environment
```bash
# Create validation cluster
gcloud container clusters create upgrade-validation \
  --zone=us-central1-a \
  --release-channel=rapid \
  --cluster-version=1.32 \
  --node-locations=us-central1-a \
  --num-nodes=1

# Test representative workloads
kubectl apply -f validation-workloads/
```

### 2. Backup and Documentation
- **Cluster configurations**: Export all cluster specs
- **Node pool configurations**: Document current settings
- **Critical workload states**: Checkpoint training jobs
- **Monitoring baselines**: Capture current performance metrics

### 3. Pre-flight Checks
```bash
# Check for deprecated APIs
kubectl get events --field-selector reason=FailedMount
kubectl get pods --all-namespaces -o yaml | grep -i "deprecated"

# Validate GPU drivers compatibility
kubectl describe nodes -l cloud.google.com/gke-nodepool | grep -A5 "nvidia"
```

---

## Phase 1: Development Environment (Week 2)
**Target: 500 T4 nodes - Lowest business impact**

### Approach: Blue-Green Node Pool Replacement
```bash
# Create new T4 node pool with 1.32
gcloud container node-pools create t4-dev-v132 \
  --cluster=ml-platform-cluster \
  --machine-type=n1-standard-4 \
  --accelerator=type=nvidia-tesla-t4,count=1 \
  --num-nodes=500 \
  --node-version=1.32 \
  --enable-autoscaling \
  --min-nodes=50 \
  --max-nodes=500

# Taint old nodes for controlled migration
kubectl taint nodes -l nodepool=t4-dev-v131 upgrade=in-progress:NoSchedule
```

### Migration Process
1. **Drain strategy**: 50 nodes at a time
2. **Workload migration**: Allow natural pod rescheduling
3. **Validation**: Run development test suite
4. **Timeline**: 2-3 days

### Success Criteria
- All T4 workloads running on 1.32 nodes
- No performance degradation in development workflows
- GPU utilization maintained

---

## Phase 2: Support Services (Week 3)
**Target: 1,000 CPU nodes - Foundation services**

### Approach: Rolling Update with Service Continuity
```bash
# Update control plane first (minimal downtime)
gcloud container clusters update ml-platform-cluster \
  --cluster-version=1.32 \
  --zone=us-central1-a

# Staged node pool updates
for pool in monitoring logging ingress storage; do
  gcloud container node-pools update $pool-nodes \
    --cluster=ml-platform-cluster \
    --node-version=1.32
done
```

### Migration Strategy
1. **Update sequence**:
   - Monitoring/observability services (25% capacity)
   - Ingress controllers (50% capacity)
   - Storage services (25% capacity)
   - Remaining CPU services (100% capacity)

2. **Service mesh considerations**:
```yaml
apiVersion: v1
kind: Service
metadata:
  name: service-upgrade-lb
spec:
  selector:
    upgrade-phase: "active"
  ports:
  - port: 80
    targetPort: 8080
```

### Timeline: 4-5 days

---

## Phase 3: Inference Fleet (Week 4-5)
**Target: 1,500 A100 nodes - High availability priority**

### Approach: Canary Deployment with Traffic Splitting
```bash
# Create canary node pool (10% capacity)
gcloud container node-pools create a100-inference-v132-canary \
  --cluster=ml-platform-cluster \
  --machine-type=a2-highgpu-1g \
  --accelerator=type=nvidia-tesla-a100,count=1 \
  --num-nodes=150 \
  --node-version=1.32
```

### Staged Rollout
1. **Week 4: Canary Phase (10%)**
   - Deploy 150 A100 nodes with 1.32
   - Route 10% inference traffic
   - Monitor latency, throughput, error rates

2. **Week 5: Progressive Rollout**
   - 30% → 50% → 70% → 100% capacity migration
   - Maintain N+1 redundancy throughout

### Traffic Management
```yaml
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
```

### Monitoring Dashboard
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: inference-upgrade-dashboard
data:
  dashboard.json: |
    {
      "panels": [
        {
          "title": "Inference Latency by Version",
          "targets": [
            {
              "expr": "histogram_quantile(0.95, sum(rate(inference_duration_seconds_bucket[5m])) by (le, version))"
            }
          ]
        },
        {
          "title": "GPU Utilization",
          "targets": [
            {
              "expr": "avg(nvidia_gpu_utilization) by (node_version)"
            }
          ]
        }
      ]
    }
```

---

## Phase 4: Training Fleet (Week 6-8)
**Target: 2,000 H100 nodes - Maximum continuity focus**

### Approach: Maintenance Window Strategy
```bash
# Schedule maintenance windows
gcloud container node-pools update h100-training-pool \
  --cluster=ml-platform-cluster \
  --node-version=1.32 \
  --max-surge=1 \
  --max-unavailable=0
```

### Training-Aware Migration
1. **Job Coordination**:
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: training-checkpoint-coordinator
spec:
  template:
    spec:
      containers:
      - name: coordinator
        image: training-coordinator:latest
        command:
        - /bin/bash
        - -c
        - |
          # Signal training jobs to checkpoint
          kubectl patch jobs -l type=training -p '{"spec":{"parallelism":0}}'
          # Wait for graceful shutdown
          sleep 300
          # Trigger node upgrade
          kubectl taint nodes $NODE_NAME upgrade=ready:NoSchedule
```

2. **Checkpoint Management**:
```bash
# Automated checkpoint verification
for job in $(kubectl get jobs -l type=training -o name); do
  kubectl logs $job --tail=100 | grep "Checkpoint saved" || echo "WARNING: $job may need manual checkpoint"
done
```

### Migration Timeline
- **Week 6**: Training job audit and checkpoint validation
- **Week 7**: 50% capacity migration (1,000 nodes)
- **Week 8**: Remaining 50% capacity migration

### Recovery Planning
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: training-recovery-runbook
data:
  recovery.sh: |
    #!/bin/bash
    # Emergency rollback procedure
    gcloud container node-pools rollback h100-training-pool \
      --cluster=ml-platform-cluster
    
    # Restart failed training jobs
    kubectl get jobs -l type=training,status=Failed \
      -o name | xargs kubectl delete
    kubectl apply -f training-jobs-backup/
```

---

## Monitoring and Validation

### Key Metrics Dashboard
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: upgrade-monitoring
data:
  prometheus-rules.yaml: |
    groups:
    - name: upgrade-monitoring
      rules:
      - alert: NodeUpgradeStuck
        expr: kube_node_info{kubelet_version!="1.32"} > 0
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "Node upgrade appears stuck"
      
      - alert: GPUUtilizationDrop
        expr: avg(nvidia_gpu_utilization) < 0.7 * avg(nvidia_gpu_utilization offset 1d)
        for: 15m
        labels:
          severity: critical
        annotations:
          summary: "GPU utilization dropped significantly during upgrade"
      
      - alert: InferenceLatencyIncrease
        expr: histogram_quantile(0.95, rate(inference_duration_seconds_bucket[5m])) > 1.2 * histogram_quantile(0.95, rate(inference_duration_seconds_bucket[5m] offset 1d))
        for: 10m
        labels:
          severity: warning
```

### Automated Testing
```bash
#!/bin/bash
# Continuous validation script
run_validation_suite() {
  echo "Running GPU workload validation..."
  kubectl apply -f tests/gpu-burn-test.yaml
  kubectl wait --for=condition=complete job/gpu-burn-test --timeout=300s
  
  echo "Running inference endpoint tests..."
  curl -X POST http://inference-service/v1/predict \
    -H "Content-Type: application/json" \
    -d '{"test": "data"}' | jq '.latency_ms'
  
  echo "Checking training job health..."
  kubectl get jobs -l type=training --field-selector=status.failed=0
}
```

---

## Rollback Strategy

### Immediate Rollback (< 1 hour)
```bash
# Emergency rollback script
#!/bin/bash
PHASE=$1  # t4, cpu, a100, h100

case $PHASE in
  "t4"|"cpu")
    gcloud container node-pools rollback ${PHASE}-nodes-v132 \
      --cluster=ml-platform-cluster
    ;;
  "a100")
    # Shift traffic back to v1.31 nodes
    kubectl patch virtualservice inference-traffic-split \
      -p '{"spec":{"http":[{"route":[{"destination":{"subset":"v131"},"weight":100}]}]}}'
    ;;
  "h100")
    # Stop new workload scheduling on v1.32 nodes
    kubectl taint nodes -l nodepool=h100-v132 rollback=true:NoSchedule
    # Restore from checkpoints
    kubectl apply -f training-jobs-backup/
    ;;
esac
```

### Rollback Decision Matrix
| Issue Type | Severity | Action | Timeline |
|------------|----------|--------|----------|
| GPU driver failure | Critical | Immediate rollback | < 30 min |
| Performance degradation >20% | High | Phase rollback | < 1 hour |
| Training job failures | High | Checkpoint restore | < 2 hours |
| Minor compatibility issues | Medium | Continue with monitoring | Document for next phase |

---

## Success Metrics

### Training Continuity (H100)
- **Target**: <2% total training time lost
- **Measure**: Aggregate GPU-hours lost during upgrade
- **Threshold**: Rollback if >5% time lost

### Inference Availability (A100)
- **Target**: 99.9% uptime maintained
- **Measure**: P95 latency increase <10%
- **Threshold**: Rollback if uptime <99.5%

### Development Velocity (T4)
- **Target**: No blocking issues for developers
- **Measure**: Job completion rate maintained
- **Threshold**: Alert if completion rate drops >15%

---

## Timeline Summary

| Phase | Duration | Nodes | Risk Level | Rollback Time |
|-------|----------|-------|------------|---------------|
| **Preparation** | Week 1 | 0 | Low | N/A |
| **Development (T4)** | Week 2 | 500 | Low | 30 minutes |
| **Services (CPU)** | Week 3 | 1,000 | Medium | 1 hour |
| **Inference (A100)** | Week 4-5 | 1,500 | High | 30 minutes |
| **Training (H100)** | Week 6-8 | 2,000 | Critical | 2 hours |
| **Validation** | Week 9 | All | Low | N/A |

**Total Duration**: 9 weeks
**Business Impact**: Minimized through careful sequencing and redundancy maintenance

This plan ensures your critical AI/ML workloads remain operational while systematically upgrading your entire 5,000-node fleet to Kubernetes 1.32.
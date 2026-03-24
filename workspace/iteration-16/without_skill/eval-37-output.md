I'll create a comprehensive phased upgrade plan that prioritizes your critical workloads while minimizing disruption to training and inference operations.

## GKE Fleet Upgrade Plan: 1.31 → 1.32

### Pre-Upgrade Assessment & Preparation

**Phase 0: Planning & Validation (Week 1)**
```bash
# Audit current workloads and dependencies
kubectl get nodes -o wide --show-labels
kubectl get pods --all-namespaces -o wide

# Test 1.32 compatibility in dev environment
# Validate GPU drivers and ML frameworks compatibility
# Check CSI drivers, networking plugins, and monitoring stack
```

### Phase 1: CPU Services Nodes (Week 2)
**Priority: Low Risk | Duration: 2-3 days**

```yaml
# cpu-services-nodepool-upgrade.yaml
apiVersion: container.v1
kind: NodePool
metadata:
  name: cpu-services
spec:
  version: "1.32"
  upgradeSettings:
    maxSurge: 2
    maxUnavailable: 1
    strategy: ROLLING_UPDATE
```

**Execution Steps:**
1. Upgrade 200 nodes at a time (20% batches)
2. Monitor service mesh, ingress controllers, and monitoring
3. Validate logging and observability pipelines
4. Complete DNS and cert-manager functionality tests

### Phase 2: T4 Development Nodes (Week 2-3)
**Priority: Medium Risk | Duration: 2 days**

```bash
# Coordinate with dev teams for maintenance windows
# Upgrade in 25% increments (125 nodes per batch)
gcloud container node-pools upgrade t4-dev-pool \
  --cluster=ml-platform-cluster \
  --zone=us-central1-a \
  --max-surge-upgrade=2 \
  --max-unavailable-upgrade=1
```

**Key Considerations:**
- Schedule during off-peak development hours
- Backup development environments and notebooks
- Test Jupyter Hub and development tool connectivity

### Phase 3: A100 Inference Nodes (Week 3-4)
**Priority: HIGH RISK | Duration: 4-5 days**

```yaml
# a100-inference-upgrade-strategy.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: inference-upgrade-config
data:
  strategy: |
    # Blue-Green approach for inference clusters
    # Maintain 70% capacity during upgrade
    batch_size: "150"  # 10% of inference nodes
    parallel_upgrades: "2"
    health_check_interval: "30s"
    rollback_threshold: "5%"
```

**Detailed Execution:**
```bash
# Pre-upgrade: Scale up inference replicas
kubectl scale deployment inference-service --replicas=20

# Upgrade batches of 150 nodes with careful monitoring
for batch in {1..10}; do
  echo "Upgrading A100 batch $batch"
  # Drain nodes gracefully
  kubectl drain a100-node-batch-$batch --ignore-daemonsets --delete-emptydir-data
  # Perform upgrade
  gcloud container node-pools upgrade a100-inference \
    --cluster=ml-platform-cluster \
    --batch-size=150
  # Validate inference endpoints
  curl -f http://inference-lb/health
  sleep 300  # 5-minute cool-down between batches
done
```

**Monitoring & Validation:**
- Real-time inference latency monitoring
- Model serving availability checks
- Load balancer health verification
- Rollback plan if >5% performance degradation

### Phase 4: H100 Training Nodes (Week 4-6)
**Priority: CRITICAL | Duration: 7-10 days**

```yaml
# h100-training-upgrade.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: training-checkpoint-backup
spec:
  template:
    spec:
      containers:
      - name: checkpoint-backup
        image: gcr.io/ml-platform/backup-tool:v1.2
        command: ["/bin/bash"]
        args:
        - -c
        - |
          # Backup all training checkpoints
          gsutil -m cp -r /training-data/checkpoints gs://backup-bucket/pre-upgrade/
          # Create training state snapshots
          kubectl get jobs -n training -o yaml > training-jobs-snapshot.yaml
```

**Training-Specific Strategy:**
```bash
# Phase 4a: Coordinate with ML teams (2 days)
# - Schedule checkpoint saves
# - Identify long-running training jobs
# - Plan job migration strategy

# Phase 4b: Upgrade non-active training nodes (3 days)
# Target nodes without active training jobs first
kubectl get nodes -l node-type=h100-training,status=idle

# Phase 4c: Rolling upgrade of active training nodes (5 days)
# Upgrade 100 nodes per day (5% daily)
for day in {1..5}; do
  # Graceful training job migration
  kubectl patch job large-model-training \
    -p '{"spec":{"suspend":true}}'
  
  # Checkpoint and pause jobs on target nodes
  ./scripts/checkpoint-and-migrate-jobs.sh
  
  # Upgrade node batch
  gcloud container node-pools upgrade h100-training \
    --cluster=ml-platform-cluster \
    --batch-size=400 \
    --max-unavailable=100
  
  # Resume training jobs
  kubectl patch job large-model-training \
    -p '{"spec":{"suspend":false}}'
done
```

### Monitoring & Rollback Strategy

**Real-time Monitoring Dashboard:**
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: upgrade-monitoring
data:
  grafana-dashboard.json: |
    {
      "dashboard": {
        "title": "GKE Upgrade Monitoring",
        "panels": [
          {
            "title": "Node Upgrade Progress",
            "targets": [
              "sum(kube_node_info{kubelet_version='1.32'}) by (node_pool)"
            ]
          },
          {
            "title": "Training Job Health",
            "targets": [
              "sum(rate(training_job_completion_total[5m])) by (job_type)"
            ]
          },
          {
            "title": "Inference Latency P95",
            "targets": [
              "histogram_quantile(0.95, inference_request_duration_seconds)"
            ]
          }
        ]
      }
    }
```

**Automated Rollback Triggers:**
```bash
#!/bin/bash
# rollback-monitor.sh

while true; do
  # Check inference error rate
  ERROR_RATE=$(curl -s "http://prometheus:9090/api/v1/query?query=rate(inference_errors_total[5m])" | jq '.data.result[0].value[1]')
  
  if (( $(echo "$ERROR_RATE > 0.05" | bc -l) )); then
    echo "Error rate exceeded 5%, initiating rollback"
    gcloud container clusters upgrade ml-platform-cluster --node-version=1.31
    break
  fi
  
  # Check training job failure rate
  TRAINING_FAILURES=$(kubectl get jobs -n training --field-selector=status.failed=1 | wc -l)
  if [ "$TRAINING_FAILURES" -gt 5 ]; then
    echo "Training job failures exceeded threshold"
    ./scripts/rollback-training-nodes.sh
  fi
  
  sleep 60
done
```

### Post-Upgrade Validation

**Comprehensive Testing Suite:**
```bash
#!/bin/bash
# post-upgrade-validation.sh

echo "=== Post-Upgrade Validation ==="

# 1. GPU Functionality Test
kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: gpu-test-suite
spec:
  template:
    spec:
      containers:
      - name: gpu-test
        image: nvidia/cuda:11.8-devel-ubuntu20.04
        command: ["nvidia-smi", "-L"]
        resources:
          limits:
            nvidia.com/gpu: 1
      restartPolicy: Never
      nodeSelector:
        accelerator: nvidia-h100
EOF

# 2. Training Pipeline Test
kubectl apply -f tests/training-pipeline-test.yaml

# 3. Inference Endpoint Validation
for endpoint in $(kubectl get ingress -o jsonpath='{.items[*].spec.rules[*].host}'); do
  echo "Testing endpoint: $endpoint"
  curl -f "https://$endpoint/health" || echo "FAILED: $endpoint"
done

# 4. Performance Benchmark
kubectl apply -f tests/performance-benchmark.yaml

echo "=== Validation Complete ==="
```

### Timeline Summary

| Phase | Duration | Risk Level | Nodes | Key Activities |
|-------|----------|------------|--------|----------------|
| 0 | Week 1 | - | - | Planning, testing, preparation |
| 1 | Week 2 | Low | 1,000 CPU | Service infrastructure upgrade |
| 2 | Week 2-3 | Medium | 500 T4 | Development environment upgrade |
| 3 | Week 3-4 | High | 1,500 A100 | Inference cluster upgrade |
| 4 | Week 4-6 | Critical | 2,000 H100 | Training cluster upgrade |

**Total Duration:** 6 weeks
**Business Continuity:** >95% training uptime, >99% inference availability

This plan ensures minimal disruption to your critical ML workloads while maintaining the ability to rollback at any phase if issues arise.
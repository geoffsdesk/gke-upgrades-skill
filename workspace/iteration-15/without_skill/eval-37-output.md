I'll create a comprehensive phased upgrade plan that prioritizes your training continuity and inference availability. Here's the strategic approach:

## Phase 1: Development & Staging (Days 1-3)

### Target: T4 Development Nodes (500 nodes)
```yaml
# Phase 1 - Development upgrade
apiVersion: container.googleapis.com/v1
kind: NodePool
metadata:
  name: dev-t4-pool
spec:
  upgradeSettings:
    maxSurge: 20
    maxUnavailable: 10
    strategy: BLUE_GREEN
  management:
    autoUpgrade: false
```

**Actions:**
- Upgrade 100 T4 nodes first as canary (20% of dev fleet)
- Monitor for 24 hours, validate ML development workflows
- Complete remaining 400 T4 nodes in batches of 100
- Test training job scheduling and development pipelines

## Phase 2: CPU Services Foundation (Days 4-6)

### Target: CPU Service Nodes (1,000 nodes)
```yaml
# Phase 2 - Services upgrade with high availability
apiVersion: container.googleapis.com/v1
kind: NodePool
metadata:
  name: cpu-services-pool
spec:
  upgradeSettings:
    maxSurge: 30
    maxUnavailable: 5  # Keep services highly available
    strategy: ROLLING_UPDATE
```

**Critical Service Protection:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: critical-ml-services
spec:
  replicas: 6  # Increase during upgrade
  template:
    spec:
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
          - labelSelector:
              matchLabels:
                app: critical-ml-services
            topologyKey: kubernetes.io/hostname
```

**Actions:**
- Upgrade in 200-node batches with 4-hour intervals
- Maintain 95% CPU capacity throughout upgrade
- Monitor API gateways, model serving orchestrators, and storage services

## Phase 3: A100 Inference Nodes (Days 7-12)

### Target: A100 Inference Nodes (1,500 nodes)
```yaml
# Phase 3 - Inference with zero-downtime strategy
apiVersion: container.googleapis.com/v1
kind: NodePool
metadata:
  name: a100-inference-pool
spec:
  upgradeSettings:
    maxSurge: 25  # Add extra capacity first
    maxUnavailable: 0  # Zero downtime for inference
    strategy: BLUE_GREEN
```

**Inference Load Balancing:**
```yaml
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: inference-traffic-split
spec:
  host: ml-inference-service
  trafficPolicy:
    connectionPool:
      tcp:
        maxConnections: 100
    outlierDetection:
      consecutiveErrors: 3
      interval: 30s
      baseEjectionTime: 30s
```

**Actions:**
- Upgrade in 5 sub-phases of 300 nodes each
- Pre-provision surge capacity before each batch
- Implement traffic shifting between old and new nodes
- Validate inference latency and throughput after each batch
- Maintain SLA compliance throughout

## Phase 4: H100 Training Nodes (Days 13-20)

### Target: H100 Training Nodes (2,000 nodes) - Most Critical Phase

```yaml
# Phase 4 - Training nodes with checkpoint protection
apiVersion: container.googleapis.com/v1
kind: NodePool
metadata:
  name: h100-training-pool
spec:
  upgradeSettings:
    maxSurge: 10  # Conservative approach
    maxUnavailable: 5
    strategy: BLUE_GREEN
```

**Training Job Protection:**
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
        image: training-ops:latest
        env:
        - name: CHECKPOINT_FREQUENCY
          value: "300"  # 5-minute checkpoints during upgrade
        - name: UPGRADE_MODE
          value: "true"
```

**Upgrade Sequence:**
1. **Days 13-14:** Upgrade 400 nodes (20%) - Non-critical training workloads
2. **Days 15-16:** Upgrade 400 nodes (20%) - Medium priority training
3. **Days 17-18:** Upgrade 400 nodes (20%) - Schedule around training cycles
4. **Days 19-20:** Upgrade remaining 800 nodes (40%) - Coordinate with ML teams

**Training Continuity Measures:**
- Force checkpoint saves before node upgrades
- Implement job migration to available H100 nodes
- Maintain 80% H100 capacity during each upgrade window
- Schedule upgrades during natural training breakpoints

## Pre-Upgrade Preparations

### Backup Strategy
```bash
#!/bin/bash
# Comprehensive backup before upgrade
kubectl create backup cluster-state-pre-132 \
  --include-cluster-resources=true \
  --include-secrets=true \
  --storage-location=gs://ml-platform-backups

# Backup training checkpoints
gsutil -m cp -r gs://training-checkpoints gs://training-checkpoints-backup-$(date +%Y%m%d)
```

### Monitoring Setup
```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: upgrade-monitoring
spec:
  groups:
  - name: upgrade.rules
    rules:
    - alert: TrainingJobFailure
      expr: increase(training_job_failures_total[5m]) > 0
      for: 0m
      labels:
        severity: critical
    - alert: InferenceLatencyHigh
      expr: inference_request_duration_p95 > 500
      for: 2m
      labels:
        severity: warning
    - alert: NodeUpgradeStuck
      expr: kube_node_status_condition{condition="Ready",status="false"} > 0
      for: 10m
```

## Risk Mitigation & Rollback Plan

### Automated Rollback Triggers
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: upgrade-rollback-controller
spec:
  analysis:
    templates:
    - templateName: success-rate
    args:
    - name: service-name
      value: ml-inference
  triggers:
  - when: "success-rate < 0.95"
    action: rollback
```

### Emergency Procedures
```bash
# Emergency rollback script
#!/bin/bash
PHASE=$1
case $PHASE in
  "inference")
    gcloud container node-pools rollback a100-inference-pool \
      --cluster=ml-platform --zone=us-central1-a
    ;;
  "training")
    # Immediate checkpoint and pause
    kubectl patch job training-jobs --type=merge \
      -p='{"spec":{"suspend":true}}'
    gcloud container node-pools rollback h100-training-pool \
      --cluster=ml-platform --zone=us-central1-a
    ;;
esac
```

## Success Criteria & Validation

### Phase Validation Checklist
- [ ] All nodes report Ready status
- [ ] GPU visibility: `nvidia-smi` accessible on all GPU nodes
- [ ] Training jobs resume within 10 minutes
- [ ] Inference latency remains < 95th percentile baseline
- [ ] No persistent volume mounting issues
- [ ] Network policies functioning correctly

### Final Validation
```bash
# Comprehensive health check
kubectl get nodes --no-headers | wc -l  # Should equal 5000
kubectl top nodes | grep -E "(H100|A100|T4)" | wc -l  # Should equal 4000
kubectl get pods --all-namespaces --field-selector=status.phase=Running | wc -l
```

This plan ensures minimal disruption to your ML workloads while systematically upgrading your entire 5,000-node fleet. The phased approach protects your most critical training operations while maintaining inference availability throughout the upgrade process.
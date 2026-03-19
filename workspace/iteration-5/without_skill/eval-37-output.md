# GKE Fleet Upgrade Plan: v1.29 → v1.30
## Mixed AI/ML Platform (5,000 nodes)

## 📊 Fleet Overview
- **Training**: 2,000 H100 nodes (critical - long-running jobs)
- **Inference**: 1,500 A100 nodes (high availability required)
- **Development**: 500 T4 nodes (flexible)
- **Services**: 1,000 CPU nodes (supporting infrastructure)

## 🎯 Upgrade Strategy

### Phase 1: Foundation & Development (Week 1)
**Target**: CPU services + T4 dev nodes (1,500 nodes)

#### 1.1 Control Plane Upgrade
```bash
# Upgrade cluster control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --master \
  --cluster-version=1.30.x \
  --zone=ZONE
```

#### 1.2 CPU Services Nodes (1,000 nodes)
```bash
# Upgrade CPU node pools with surge settings
gcloud container node-pools update cpu-services-pool \
  --cluster=CLUSTER_NAME \
  --zone=ZONE \
  --max-surge-upgrade=10 \
  --max-unavailable-upgrade=5
```

**Batching**: 200 nodes per batch, 5 batches total
- Monitor service mesh, logging, monitoring
- Validate DNS, ingress controllers
- Check resource quotas and RBAC

#### 1.3 T4 Development Nodes (500 nodes)
```bash
gcloud container node-pools update t4-dev-pool \
  --cluster=CLUSTER_NAME \
  --zone=ZONE \
  --max-surge-upgrade=15 \
  --max-unavailable-upgrade=10
```

**Batching**: 100 nodes per batch, 5 batches total
- Coordinate with dev teams for job scheduling
- Test GPU driver compatibility
- Validate development workflows

### Phase 2: Inference Infrastructure (Week 2-3)
**Target**: A100 inference nodes (1,500 nodes)

#### Pre-Phase 2 Checklist
- [ ] Validate Phase 1 stability (72 hours)
- [ ] Confirm inference traffic patterns
- [ ] Set up enhanced monitoring

#### 2.1 A100 Inference Upgrade Strategy
```yaml
# Blue-Green approach for inference pools
apiVersion: v1
kind: ConfigMap
metadata:
  name: inference-upgrade-config
data:
  strategy: "rolling-with-surge"
  batch-size: "150"
  surge-percentage: "20"
  max-unavailable: "5%"
```

```bash
# Create temporary surge capacity
gcloud container node-pools create a100-inference-temp \
  --cluster=CLUSTER_NAME \
  --machine-type=a2-ultragpu-1g \
  --accelerator=type=nvidia-a100-80gb,count=1 \
  --num-nodes=300 \
  --node-version=1.30.x

# Upgrade original pool in batches
for batch in {1..10}; do
  echo "Upgrading A100 batch $batch"
  gcloud container node-pools upgrade a100-inference-pool \
    --cluster=CLUSTER_NAME \
    --batch-size=150 \
    --max-surge-upgrade=20 \
    --max-unavailable-upgrade=5
  
  # Wait and validate
  sleep 1800  # 30 minutes between batches
done
```

#### 2.2 Inference Validation Script
```bash
#!/bin/bash
# validate-inference.sh

# Check inference endpoints
for endpoint in $(kubectl get ingress -o jsonpath='{.items[*].spec.rules[*].host}'); do
  response=$(curl -s -o /dev/null -w "%{http_code}" https://$endpoint/health)
  if [ $response -ne 200 ]; then
    echo "ALERT: Endpoint $endpoint not healthy"
    exit 1
  fi
done

# Validate GPU availability
kubectl get nodes -l node-type=inference \
  -o custom-columns=NAME:.metadata.name,GPU:.status.allocatable.'nvidia\.com/gpu'

# Check inference workload distribution
kubectl top nodes -l node-type=inference --sort-by=cpu
```

### Phase 3: Training Infrastructure (Week 4-6)
**Target**: H100 training nodes (2,000 nodes)

#### Pre-Phase 3 Preparation
```bash
# Create training job checkpoint backup
kubectl create job training-checkpoint-backup \
  --image=gcr.io/PROJECT/checkpoint-backup:latest

# Set up dedicated training upgrade monitoring
kubectl apply -f - <<EOF
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: training-upgrade-monitor
spec:
  selector:
    matchLabels:
      node-type: training
  endpoints:
  - port: metrics
    interval: 30s
EOF
```

#### 3.1 Training Node Upgrade Strategy
**Ultra-conservative approach**: 5% batches with extensive validation

```bash
#!/bin/bash
# training-upgrade.sh

TOTAL_TRAINING_NODES=2000
BATCH_SIZE=100
BATCHES=$((TOTAL_TRAINING_NODES / BATCH_SIZE))

for batch in $(seq 1 $BATCHES); do
  echo "=== Training Batch $batch/$BATCHES ==="
  
  # Pre-upgrade: Save training states
  kubectl annotate nodes -l batch=training-$batch \
    upgrade.ai/checkpoint-required=true
  
  # Trigger checkpoint save
  kubectl patch cronjob training-checkpoint \
    -p '{"spec":{"suspend":false}}'
  
  # Wait for checkpoint completion
  kubectl wait --for=condition=complete job/training-checkpoint-$(date +%s) \
    --timeout=3600s
  
  # Upgrade batch
  gcloud container node-pools upgrade h100-training-pool \
    --cluster=CLUSTER_NAME \
    --batch-size=$BATCH_SIZE \
    --max-surge-upgrade=5 \
    --max-unavailable-upgrade=2
  
  # Post-upgrade validation
  ./validate-training-batch.sh $batch
  
  # Wait 24 hours between batches for stability
  if [ $batch -lt $BATCHES ]; then
    echo "Waiting 24 hours before next batch..."
    sleep 86400
  fi
done
```

#### 3.2 Training Validation
```bash
#!/bin/bash
# validate-training-batch.sh

BATCH=$1

# Check GPU health
kubectl get nodes -l batch=training-$BATCH \
  -o custom-columns=NAME:.metadata.name,STATUS:.status.conditions[-1].type

# Validate NCCL communication
kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: nccl-test-batch-$BATCH
spec:
  template:
    spec:
      nodeSelector:
        batch: training-$BATCH
      containers:
      - name: nccl-test
        image: nvcr.io/nvidia/pytorch:23.10-py3
        command: ["python", "-m", "torch.distributed.launch"]
        args: ["--nproc_per_node=8", "/opt/nccl-test.py"]
        resources:
          limits:
            nvidia.com/gpu: 8
EOF

# Wait for NCCL test completion
kubectl wait --for=condition=complete job/nccl-test-batch-$BATCH --timeout=1800s

# Check training job resumption
kubectl get pods -l job-type=training,batch=training-$BATCH \
  --field-selector=status.phase=Running
```

## 🚨 Rollback Procedures

### Emergency Rollback Script
```bash
#!/bin/bash
# emergency-rollback.sh

POOL_NAME=$1
BACKUP_VERSION="1.29.x"

echo "EMERGENCY ROLLBACK: $POOL_NAME"

# Stop current upgrade
gcloud container operations cancel \
  $(gcloud container operations list --filter="status=RUNNING" --format="value(name)") \
  --zone=ZONE

# Rollback node pool
gcloud container node-pools rollback $POOL_NAME \
  --cluster=CLUSTER_NAME \
  --zone=ZONE

# Restore from backup if needed
kubectl apply -f backup-configs/$POOL_NAME-pre-upgrade.yaml

# Alert teams
curl -X POST "$SLACK_WEBHOOK" \
  -d "{\"text\":\"🚨 EMERGENCY: Rolled back $POOL_NAME to $BACKUP_VERSION\"}"
```

## 📊 Monitoring & Validation

### Comprehensive Monitoring Dashboard
```yaml
# monitoring-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: upgrade-monitoring
data:
  prometheus.yml: |
    rule_files:
      - "/etc/prometheus/upgrade-rules.yml"
    
    scrape_configs:
    - job_name: 'kubernetes-nodes-upgrade'
      kubernetes_sd_configs:
      - role: node
      relabel_configs:
      - source_labels: [__meta_kubernetes_node_label_upgrade_phase]
        target_label: upgrade_phase
    
    - job_name: 'gpu-metrics'
      static_configs:
      - targets: ['dcgm-exporter:9400']
  
  upgrade-rules.yml: |
    groups:
    - name: upgrade.rules
      rules:
      - alert: NodeUpgradeFailed
        expr: kube_node_status_condition{condition="Ready",status="false"} == 1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Node upgrade failed"
      
      - alert: GPUNotReady
        expr: dcgm_gpu_utilization == 0
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "GPU not utilized post-upgrade"
```

### Health Check Automation
```bash
#!/bin/bash
# continuous-health-check.sh

while true; do
  # Node health
  UNHEALTHY_NODES=$(kubectl get nodes --no-headers | grep -v Ready | wc -l)
  
  # GPU availability
  TOTAL_GPUS=$(kubectl get nodes -o json | jq '.items[].status.allocatable."nvidia.com/gpu"' | jq -s 'map(tonumber) | add')
  ALLOCATED_GPUS=$(kubectl describe nodes | grep "nvidia.com/gpu" | awk '{sum += $2} END {print sum}')
  
  # Training job health
  FAILED_TRAINING=$(kubectl get jobs -l type=training --field-selector=status.failed=1 | wc -l)
  
  # Inference latency
  INFERENCE_P99=$(curl -s http://prometheus:9090/api/v1/query?query=histogram_quantile\(0.99,inference_duration_seconds\) | jq '.data.result[0].value[1]')
  
  # Report status
  cat > /tmp/upgrade-status.json <<EOF
{
  "timestamp": "$(date -Iseconds)",
  "unhealthy_nodes": $UNHEALTHY_NODES,
  "gpu_utilization": $(echo "scale=2; $ALLOCATED_GPUS / $TOTAL_GPUS * 100" | bc),
  "failed_training_jobs": $FAILED_TRAINING,
  "inference_p99_latency": $INFERENCE_P99
}
EOF
  
  # Alert if thresholds exceeded
  if [ $UNHEALTHY_NODES -gt 50 ] || [ $FAILED_TRAINING -gt 5 ]; then
    curl -X POST "$ALERT_WEBHOOK" -d @/tmp/upgrade-status.json
  fi
  
  sleep 300  # Check every 5 minutes
done
```

## ⏱️ Timeline Summary

| Phase | Duration | Nodes | Risk Level | Downtime |
|-------|----------|-------|------------|----------|
| **Phase 1** | 1 week | 1,500 | Low | ~2 hours |
| **Phase 2** | 2 weeks | 1,500 | Medium | <30 minutes |
| **Phase 3** | 3 weeks | 2,000 | High | Minimal |
| **Total** | **6 weeks** | **5,000** | **Managed** | **<3 hours** |

## 🎯 Success Criteria

- ✅ Zero training job data loss
- ✅ <99.9% inference availability maintained
- ✅ <5% performance degradation during upgrade
- ✅ All GPU drivers compatible with K8s 1.30
- ✅ Complete upgrade within 6-week window

This plan prioritizes your critical training workloads while ensuring inference availability through careful batching and surge capacity management.
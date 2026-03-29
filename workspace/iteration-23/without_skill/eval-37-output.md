# GKE 1.31 → 1.32 Upgrade Plan for AI/ML Platform

## Executive Summary
This phased upgrade plan prioritizes training continuity and inference availability while minimizing disruption to your 5,000-node AI/ML platform.

## Pre-Upgrade Preparation

### Phase 0: Environment Preparation (Week 1)
```bash
# 1. Backup cluster configurations
kubectl get nodes -o yaml > nodes-backup-$(date +%Y%m%d).yaml
kubectl get pods --all-namespaces -o yaml > pods-backup-$(date +%Y%m%d).yaml

# 2. Validate current workload health
kubectl top nodes
kubectl get pods --all-namespaces --field-selector=status.phase!=Running

# 3. Test upgrade on smaller staging cluster
gcloud container clusters create staging-upgrade-test \
  --zone=us-central1-a \
  --cluster-version=1.31 \
  --num-nodes=3

# 4. Update critical workload tolerations for upgrade
kubectl patch deployment critical-inference-service -p \
  '{"spec":{"template":{"spec":{"tolerations":[{"key":"node.kubernetes.io/unschedulable","operator":"Exists","effect":"NoSchedule"}]}}}}'
```

## Phased Upgrade Strategy

### Phase 1: Control Plane Upgrade (Week 2, Day 1-2)
**Target: All clusters control planes**
**Downtime: ~5-10 minutes per cluster**

```bash
# Upgrade control plane (no node disruption)
gcloud container clusters upgrade $CLUSTER_NAME \
  --master \
  --cluster-version=1.32 \
  --zone=$ZONE \
  --quiet
```

**Validation:**
```bash
# Verify API server version
kubectl version --short
# Verify all nodes still reporting ready
kubectl get nodes
```

### Phase 2: CPU Service Nodes (Week 2, Day 3-4)
**Target: 1,000 CPU nodes**
**Strategy: Blue-green with 25% capacity buffer**

```yaml
# cpu-nodepool-upgrade.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: upgrade-config
data:
  phase: "cpu-services"
  batch-size: "200"
  max-unavailable: "10%"
```

```bash
# Create new CPU node pool
gcloud container node-pools create cpu-services-132 \
  --cluster=$CLUSTER_NAME \
  --machine-type=n2-standard-32 \
  --num-nodes=250 \
  --node-version=1.32 \
  --node-pool-max-nodes=1200

# Migrate services gradually
kubectl cordon $(kubectl get nodes -l node-pool=cpu-services-131 -o name | head -200)

# Wait for pods to reschedule, then delete old nodes
kubectl delete $(kubectl get nodes -l node-pool=cpu-services-131 -o name | head -200)
```

### Phase 3: Development T4 Nodes (Week 2, Day 5 - Week 3, Day 1)
**Target: 500 T4 nodes**
**Strategy: Rolling upgrade with maintenance windows**

```bash
# Schedule maintenance window notification
kubectl create configmap maintenance-notice \
  --from-literal=message="T4 development nodes upgrading. Save your work."

# Upgrade in 100-node batches
for batch in {1..5}; do
  gcloud container node-pools upgrade t4-dev-pool \
    --cluster=$CLUSTER_NAME \
    --node-version=1.32 \
    --max-nodes-per-upgrade=100 \
    --zone=$ZONE
  
  # Wait and validate between batches
  sleep 600
  kubectl get nodes -l node-pool=t4-dev-pool
done
```

### Phase 4: A100 Inference Nodes (Week 3, Day 2-5)
**Target: 1,500 A100 nodes**
**Strategy: Zone-by-zone with traffic shifting**

```yaml
# inference-upgrade-strategy.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: inference-upgrade-config
data:
  strategy: "zone-by-zone"
  health-check-endpoint: "/health"
  min-available-replicas: "80%"
```

```bash
# Zone A upgrade (500 nodes)
# 1. Scale up capacity in other zones
kubectl scale deployment inference-service --replicas=120

# 2. Drain zone A gradually
kubectl drain $(kubectl get nodes -l zone=zone-a,node-type=a100 -o name | head -50) \
  --ignore-daemonsets \
  --delete-emptydir-data \
  --grace-period=300

# 3. Upgrade zone A nodes
gcloud container node-pools upgrade a100-inference-zone-a \
  --cluster=$CLUSTER_NAME \
  --node-version=1.32

# 4. Validate inference health
curl -f http://inference-service/health
kubectl get pods -l app=inference-service -o wide

# Repeat for zones B and C
```

**Inference Health Monitoring:**
```bash
# Continuous health monitoring script
while true; do
  HEALTHY_PODS=$(kubectl get pods -l app=inference-service --field-selector=status.phase=Running | wc -l)
  if [ $HEALTHY_PODS -lt 80 ]; then
    echo "ALERT: Only $HEALTHY_PODS inference pods healthy"
    # Trigger rollback if needed
  fi
  sleep 30
done
```

### Phase 5: H100 Training Nodes (Week 4-5)
**Target: 2,000 H100 nodes**
**Strategy: Checkpoint-aware, coordinated with ML teams**

```yaml
# training-upgrade-coordination.yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: checkpoint-coordinator
spec:
  schedule: "0 2 * * *"  # 2 AM daily
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: checkpoint
            image: training-coordinator:latest
            command:
            - /bin/bash
            - -c
            - |
              # Notify training jobs to checkpoint
              kubectl annotate pods -l job-type=training checkpoint-requested=true
              # Wait for confirmation
              sleep 3600
              # Proceed with node upgrades
```

```bash
# Training-aware upgrade process
# 1. Identify long-running training jobs
kubectl get pods -l job-type=training --field-selector=status.phase=Running \
  -o custom-columns=NAME:.metadata.name,AGE:.status.startTime

# 2. Coordinate with ML teams for checkpoint windows
# Schedule upgrades during natural checkpoint intervals

# 3. Upgrade in small batches (100 nodes) during checkpoint windows
for day in {1..20}; do
  echo "Day $day: Upgrading 100 H100 nodes"
  
  # Wait for checkpoint window (e.g., 2-4 AM)
  while [ $(date +%H) -lt 02 ] || [ $(date +%H) -gt 04 ]; do
    sleep 300
  done
  
  # Gracefully drain nodes
  NODES_TO_UPGRADE=$(kubectl get nodes -l node-type=h100,upgrade-batch=$day -o name | head -100)
  
  for node in $NODES_TO_UPGRADE; do
    kubectl drain $node \
      --ignore-daemonsets \
      --delete-emptydir-data \
      --grace-period=600 \
      --timeout=1200s
  done
  
  # Upgrade the batch
  gcloud container node-pools upgrade h100-training-pool \
    --cluster=$CLUSTER_NAME \
    --node-version=1.32 \
    --max-nodes-per-upgrade=100
    
  # Validate before next batch
  sleep 1800  # 30 min validation window
done
```

## Rollback Procedures

### Emergency Rollback Script
```bash
#!/bin/bash
# emergency-rollback.sh

PHASE=$1
case $PHASE in
  "control-plane")
    echo "Control plane rollback not supported - contact Google Cloud Support"
    ;;
  "cpu-services")
    kubectl scale deployment -l tier=services --replicas=0
    gcloud container node-pools rollback cpu-services-132
    ;;
  "inference")
    # Immediate traffic shift to healthy zones
    kubectl patch service inference-service -p \
      '{"spec":{"selector":{"version":"stable"}}}'
    ;;
  "training")
    # Restore from latest checkpoints
    kubectl create job training-restore --from=cronjob/checkpoint-coordinator
    ;;
esac
```

## Monitoring and Validation

### Continuous Monitoring Dashboard
```yaml
# monitoring-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: upgrade-monitoring
data:
  queries: |
    # Node readiness
    up{job="kubernetes-nodes"}
    # GPU utilization
    nvidia_gpu_utilization
    # Training job health
    kube_pod_status_phase{pod=~"training-.*"}
    # Inference latency
    http_request_duration_seconds{service="inference"}
```

### Health Check Script
```bash
#!/bin/bash
# cluster-health-check.sh

echo "=== Cluster Health Check ==="
echo "Nodes Ready: $(kubectl get nodes | grep Ready | wc -l)/5000"
echo "GPU Nodes Available: $(kubectl get nodes -l accelerator=nvidia-tesla-h100,accelerator=nvidia-tesla-a100,accelerator=nvidia-tesla-t4 | grep Ready | wc -l)"
echo "Training Jobs Running: $(kubectl get pods -l job-type=training --field-selector=status.phase=Running | wc -l)"
echo "Inference Service Health: $(curl -s -o /dev/null -w "%{http_code}" http://inference-service/health)"
echo "Average GPU Utilization: $(kubectl exec -n monitoring prometheus-0 -- promtool query instant 'avg(nvidia_gpu_utilization)')"
```

## Timeline Summary

| Week | Phase | Target | Expected Impact |
|------|--------|---------|-----------------|
| 1 | Preparation | Environment setup | Minimal |
| 2 | Control plane + CPU + T4 | 1,500 nodes | Low impact on ML workloads |
| 3 | A100 Inference | 1,500 nodes | Managed inference interruption |
| 4-5 | H100 Training | 2,000 nodes | Coordinated training pauses |

## Success Criteria

- ✅ Zero unplanned training job failures
- ✅ Inference availability > 99.5%
- ✅ Upgrade completion within 5 weeks
- ✅ All GPU accelerators functioning post-upgrade
- ✅ No data loss from persistent volumes

This plan ensures training continuity through careful checkpoint coordination and maintains inference availability through zone-by-zone upgrades with capacity buffers.
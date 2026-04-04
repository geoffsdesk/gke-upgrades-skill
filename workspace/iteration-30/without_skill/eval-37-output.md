# GKE Fleet Upgrade Plan: v1.31 → v1.32
## 5,000-Node Mixed AI/ML Platform

## Executive Summary
This phased upgrade plan prioritizes training continuity and inference availability while systematically upgrading your entire GKE fleet with minimal disruption.

---

## Phase 1: Infrastructure & Development (Days 1-3)
**Target: CPU nodes + T4 development nodes**

### Day 1: CPU Services Nodes (1,000 nodes)
```bash
# Pre-upgrade validation
kubectl get nodes -l node-type=cpu-services
kubectl top nodes -l node-type=cpu-services

# Upgrade control plane first
gcloud container clusters upgrade ml-platform-cluster \
  --master --zone=us-central1-a

# Upgrade CPU node pools (rolling update)
gcloud container node-pools upgrade cpu-services-pool \
  --cluster=ml-platform-cluster \
  --zone=us-central1-a \
  --max-surge-upgrade=10 \
  --max-unavailable-upgrade=5
```

### Days 2-3: T4 Development Nodes (500 nodes)
```bash
# Coordinate with dev teams for maintenance window
kubectl drain t4-dev-nodes --ignore-daemonsets --delete-emptydir-data

# Upgrade T4 development pools
gcloud container node-pools upgrade t4-dev-pool \
  --cluster=ml-platform-cluster \
  --zone=us-central1-a \
  --max-surge-upgrade=5 \
  --max-unavailable-upgrade=2
```

---

## Phase 2: A100 Inference Nodes (Days 4-8)
**Target: 1,500 A100 GPU nodes - Maintain 70% availability**

### Pre-Phase 2 Setup
```yaml
# Configure PodDisruptionBudgets for inference services
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: inference-service-pdb
spec:
  minAvailable: 70%
  selector:
    matchLabels:
      app: inference-service
      gpu-type: a100
```

### Upgrade Strategy: Zone-by-Zone
```bash
# Day 4-5: Zone A (500 nodes)
kubectl cordon -l zone=us-central1-a,gpu-type=a100

# Gracefully drain inference pods
kubectl drain -l zone=us-central1-a,gpu-type=a100 \
  --ignore-daemonsets \
  --delete-emptydir-data \
  --timeout=600s

gcloud container node-pools upgrade a100-inference-pool-a \
  --cluster=ml-platform-cluster \
  --zone=us-central1-a \
  --max-surge-upgrade=3 \
  --max-unavailable-upgrade=1

# Day 6-7: Zone B (500 nodes)
# Repeat process for Zone B

# Day 8: Zone C (500 nodes)
# Repeat process for Zone C
```

---

## Phase 3: H100 Training Nodes (Days 9-15)
**Target: 2,000 H100 GPU nodes - Zero training job interruption**

### Pre-Phase 3 Preparation
```bash
# Enable checkpoint automation
kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: CronJob
metadata:
  name: training-checkpoint-trigger
spec:
  schedule: "*/30 * * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: checkpoint
            image: checkpoint-manager:latest
            command: ["/bin/sh"]
            args: ["-c", "trigger-checkpoint --all-training-jobs"]
EOF
```

### Node Pool Upgrade Strategy
```bash
# Create new H100 node pool with v1.32
gcloud container node-pools create h100-training-pool-v132 \
  --cluster=ml-platform-cluster \
  --machine-type=a3-highgpu-8g \
  --accelerator=type=nvidia-h100-80gb,count=8 \
  --node-version=1.32.x \
  --num-nodes=0 \
  --enable-autoscaling \
  --max-nodes=500 \
  --min-nodes=0 \
  --zone=us-central1-a

# Gradual migration script
#!/bin/bash
BATCH_SIZE=100
TOTAL_NODES=2000
BATCHES=$((TOTAL_NODES / BATCH_SIZE))

for i in $(seq 1 $BATCHES); do
  echo "Processing batch $i of $BATCHES"
  
  # Scale up new pool
  gcloud container clusters resize ml-platform-cluster \
    --node-pool=h100-training-pool-v132 \
    --num-nodes=$((i * BATCH_SIZE)) \
    --zone=us-central1-a
    
  # Wait for nodes to be ready
  kubectl wait --for=condition=Ready \
    nodes -l cloud.google.com/gke-nodepool=h100-training-pool-v132 \
    --timeout=600s
    
  # Migrate training jobs
  ./migrate-training-jobs.sh --batch=$i
  
  # Verify job stability
  sleep 300
  
  # Scale down old pool
  OLD_POOL_SIZE=$((TOTAL_NODES - (i * BATCH_SIZE)))
  gcloud container clusters resize ml-platform-cluster \
    --node-pool=h100-training-pool-v131 \
    --num-nodes=$OLD_POOL_SIZE \
    --zone=us-central1-a
    
  echo "Batch $i completed successfully"
done
```

---

## Training Job Migration Script
```python
#!/usr/bin/env python3
# migrate-training-jobs.sh implementation

import subprocess
import time
import json

def get_training_jobs():
    """Get all running training jobs on old nodes"""
    cmd = [
        "kubectl", "get", "pods", 
        "-l", "app=training,gpu-type=h100",
        "-o", "json"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(result.stdout)

def trigger_checkpoint(job_name):
    """Trigger checkpoint for specific job"""
    cmd = [
        "kubectl", "exec", f"deployment/{job_name}",
        "--", "python", "save_checkpoint.py"
    ]
    subprocess.run(cmd)

def migrate_job(job_spec, new_node_selector):
    """Migrate job to new nodes"""
    # Update node selector
    job_spec['spec']['template']['spec']['nodeSelector'] = new_node_selector
    
    # Apply updated spec
    cmd = ["kubectl", "apply", "-f", "-"]
    subprocess.run(cmd, input=json.dumps(job_spec), text=True)

def main():
    batch = int(sys.argv[2])  # --batch=X
    jobs = get_training_jobs()
    
    jobs_per_batch = len(jobs['items']) // 20  # 20 batches total
    start_idx = (batch - 1) * jobs_per_batch
    end_idx = batch * jobs_per_batch
    
    batch_jobs = jobs['items'][start_idx:end_idx]
    
    for job in batch_jobs:
        print(f"Migrating job: {job['metadata']['name']}")
        
        # Trigger checkpoint
        trigger_checkpoint(job['metadata']['name'])
        time.sleep(30)  # Wait for checkpoint
        
        # Update job to target new nodes
        new_selector = {
            "cloud.google.com/gke-nodepool": "h100-training-pool-v132",
            "gpu-type": "h100"
        }
        migrate_job(job, new_selector)
        
        # Verify job restart
        time.sleep(60)
        print(f"Job {job['metadata']['name']} migrated successfully")

if __name__ == "__main__":
    main()
```

---

## Monitoring & Validation

### Real-time Monitoring Dashboard
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: upgrade-monitoring
data:
  queries.yaml: |
    training_jobs_running:
      query: 'sum(kube_pod_status_phase{phase="Running", app="training"})'
      alert_threshold: 0.8  # 80% of normal capacity
    
    inference_latency:
      query: 'histogram_quantile(0.95, rate(inference_request_duration_seconds_bucket[5m]))'
      alert_threshold: 2.0  # 2 second P95 latency
    
    node_upgrade_progress:
      query: 'kube_node_info{kubelet_version="1.32.*"} / kube_node_info'
      
    gpu_utilization:
      query: 'nvidia_gpu_duty_cycle'
      alert_threshold: 0.6  # Maintain 60% utilization
```

### Automated Rollback Triggers
```bash
#!/bin/bash
# rollback-detector.sh

# Monitor key metrics
TRAINING_JOBS=$(kubectl get pods -l app=training --field-selector=status.phase=Running | wc -l)
INFERENCE_ERRORS=$(kubectl logs -l app=inference --since=5m | grep ERROR | wc -l)

# Rollback conditions
if [ $TRAINING_JOBS -lt 50 ]; then
  echo "ALERT: Training jobs below threshold, triggering rollback"
  ./rollback-h100-upgrade.sh
fi

if [ $INFERENCE_ERRORS -gt 100 ]; then
  echo "ALERT: High inference error rate, triggering rollback"
  ./rollback-a100-upgrade.sh
fi
```

---

## Timeline Summary

| Phase | Duration | Nodes | Risk Level | Availability Target |
|-------|----------|--------|------------|-------------------|
| 1: Infrastructure | Days 1-3 | 1,500 | Low | 95% |
| 2: A100 Inference | Days 4-8 | 1,500 | Medium | 70% |
| 3: H100 Training | Days 9-15 | 2,000 | High | 100% |

**Total Timeline: 15 days**
**Zero training interruption guarantee**
**Minimum 70% inference availability maintained**

## Success Criteria
- ✅ All 5,000 nodes upgraded to GKE 1.32
- ✅ Zero training job failures
- ✅ <5% inference latency degradation
- ✅ All GPU workloads maintain performance baselines
- ✅ Complete rollback capability at each phase
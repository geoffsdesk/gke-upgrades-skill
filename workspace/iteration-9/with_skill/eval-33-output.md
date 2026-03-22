# GKE GPU Inference Cluster Upgrade Plan

**Cluster:** ML Inference Platform | **Mode:** Standard | **Upgrade:** 1.31 → 1.32

## Executive Summary

For your high-availability inference workloads with mixed GPU pools, I recommend a **rolling upgrade strategy with inference-optimized settings**. The L4 pool (inference-focused) uses conservative surge settings to maintain serving capacity, while the A100 pool (mixed inference + training) uses a drain-first approach to protect long-running jobs.

## GPU-Specific Constraints

- **No live migration:** All GPU nodes require pod restart during upgrades
- **Driver coupling:** GKE 1.32 will auto-install updated GPU drivers, potentially changing CUDA versions
- **Capacity assumptions:** GPU reservations typically have no surge headroom

## Upgrade Strategy by Node Pool

### L4 Pool (Inference Priority)
- **Strategy:** Rolling with minimal surge
- **Settings:** `maxSurge=0, maxUnavailable=1` 
- **Rationale:** Maintains maximum serving capacity, upgrades one node at a time
- **Duration:** ~200 nodes × 10-15 min/node = 33-50 hours total

### A100 Pool (Training + Inference Mixed)
- **Strategy:** Coordinated maintenance windows
- **Settings:** `maxSurge=0, maxUnavailable=3` during training gaps
- **Rationale:** Protects long-running fine-tuning jobs, faster completion during safe windows

## Pre-Upgrade Validation

```bash
# Test GPU driver compatibility in staging
gcloud container clusters create test-cluster-132 \
  --zone us-central1-a \
  --cluster-version 1.32.x-gke.latest \
  --num-nodes 1 \
  --machine-type g2-standard-4 \
  --accelerator type=nvidia-l4,count=1

# Verify inference serving works with new driver stack
kubectl apply -f your-inference-workload.yaml
```

## Detailed Upgrade Runbook

### Phase 1: Control Plane (15 minutes)

```bash
# Upgrade control plane first
gcloud container clusters upgrade ml-inference-cluster \
  --zone us-central1-a \
  --master \
  --cluster-version 1.32.x-gke.latest

# Verify control plane health
kubectl get pods -n kube-system | grep -v Running
```

### Phase 2: L4 Inference Pool (~36 hours)

```bash
# Configure conservative surge for inference availability
gcloud container node-pools update l4-inference-pool \
  --cluster ml-inference-cluster \
  --zone us-central1-a \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1

# Start upgrade during low-traffic period
gcloud container node-pools upgrade l4-inference-pool \
  --cluster ml-inference-cluster \
  --zone us-central1-a \
  --cluster-version 1.32.x-gke.latest

# Monitor inference latency during upgrade
# Each node takes ~10-15 min: cordon → drain → replace → ready
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=l4-inference-pool'
```

### Phase 3: A100 Mixed Pool (Coordinated with Training Schedule)

```bash
# Wait for training job gap or coordinate with ML team
# Check for active fine-tuning jobs
kubectl get pods -n training --field-selector=status.phase=Running

# Configure faster upgrade during safe window
gcloud container node-pools update a100-mixed-pool \
  --cluster ml-inference-cluster \
  --zone us-central1-a \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 3

# Execute upgrade
gcloud container node-pools upgrade a100-mixed-pool \
  --cluster ml-inference-cluster \
  --zone us-central1-a \
  --cluster-version 1.32.x-gke.latest
```

## Availability Protection Measures

### PDB Configuration for Inference Services
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: inference-pdb
spec:
  selector:
    matchLabels:
      app: inference-service
  maxUnavailable: 20%  # Allows rolling upgrade while maintaining 80% capacity
```

### HPA Buffer for Traffic Spikes
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
spec:
  minReplicas: 10  # Increased from normal to buffer during upgrade
  maxReplicas: 50
  targetCPUUtilizationPercentage: 60  # Lower threshold during upgrade
```

## Training Job Protection

### Option A: Maintenance Exclusion (Recommended)
```bash
# Block node upgrades during active training campaign
gcloud container clusters update ml-inference-cluster \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "training-campaign-jan" \
  --add-maintenance-exclusion-start-time "2024-01-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-01-22T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

### Option B: Coordinated Upgrade Windows
```bash
# Schedule A100 upgrades only during 2-hour gaps between training jobs
# Example: 6-8 AM daily when training jobs typically finish
```

## Risk Mitigation

### GPU Driver Compatibility
- **Pre-test:** Validate your inference containers work with GKE 1.32's GPU driver
- **CUDA version:** Check if the driver update changes CUDA runtime versions
- **Framework compatibility:** Test TensorFlow, PyTorch, JAX with new driver stack

### Traffic Management During Upgrade
```yaml
# Increase replica count 20% before starting node upgrades
kubectl scale deployment inference-service --replicas=12  # from 10

# Configure aggressive health checks to detect issues quickly
livenessProbe:
  httpGet:
    path: /health
    port: 8080
  initialDelaySeconds: 10
  periodSeconds: 5  # More frequent during upgrade
```

### Monitoring & Alerting
```bash
# Key metrics to watch during upgrade:
# - Inference request latency (p95, p99)
# - Error rate by model
# - GPU utilization per node
# - Queue depth for fine-tuning jobs
# - Available inference replicas
```

## Rollback Plan

### Immediate Actions if Issues Arise
```bash
# Stop in-progress upgrade
gcloud container operations cancel OPERATION_ID

# Scale up replicas on healthy nodes
kubectl scale deployment inference-service --replicas=20

# Route traffic away from problematic nodes
kubectl cordon NODE_NAME
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data
```

### GPU Pool Rollback (Last Resort)
```bash
# Create new A100 pool at 1.31 if 1.32 has driver issues
gcloud container node-pools create a100-rollback-pool \
  --cluster ml-inference-cluster \
  --zone us-central1-a \
  --cluster-version 1.31.x-gke.latest \
  --machine-type a2-highgpu-1g \
  --num-nodes 10 \
  --enable-autoscaling \
  --max-nodes 100

# Migrate training workloads to rollback pool
# Delete problematic pool after migration
```

## Timeline & Coordination

| Phase | Duration | Coordination Required |
|-------|----------|---------------------|
| **Control plane** | 15 min | Minimal - brief kubectl disruption |
| **L4 pool upgrade** | 30-40 hours | Monitor inference latency, scale up replicas |
| **A100 pool upgrade** | 8-12 hours | Coordinate with ML team for training gaps |
| **Total window** | 2-3 days | Stagger phases, maintain 24/7 inference availability |

## Success Criteria

✅ **Inference availability >95%** throughout upgrade  
✅ **P95 latency increase <20%** during node transitions  
✅ **Zero training job interruptions** (coordinate timing)  
✅ **All GPU drivers functional** post-upgrade  
✅ **Auto-scaling responsive** to traffic patterns  

Would you like me to create specific monitoring queries for your observability stack, or detail the PDB configurations for your inference workloads?
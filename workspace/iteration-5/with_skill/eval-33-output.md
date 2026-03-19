# GKE Upgrade Plan: ML Inference Platform (1.29 → 1.30)

## Environment Summary
- **Cluster**: GKE Standard with GPU workloads (inference + fine-tuning)
- **Current version**: 1.29 → **Target version**: 1.30 
- **Node pools**: 200x L4 (inference), 100x A100 (inference + fine-tuning)
- **Workload characteristics**: Latency-sensitive inference, 4-8h fine-tuning jobs
- **Scaling**: Auto-scaling based on traffic

## GPU-Specific Upgrade Considerations

### Critical GPU constraints
- **No live migration**: GPU VMs require pod restart for every node upgrade
- **Driver version change**: GKE 1.30 may ship different CUDA drivers than 1.29
- **Surge capacity**: GPU nodes (especially A100) are scarce — surge upgrades may fail if replacement nodes can't be provisioned

### Recommended upgrade strategy by pool

**L4 Pool (Inference)**
```bash
# Conservative surge settings for inference SLA protection
gcloud container node-pools update l4-inference-pool \
  --cluster ML_CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```
- `maxSurge=2`: Creates 2 replacement nodes at a time
- `maxUnavailable=0`: Never reduces inference capacity during upgrade
- Relies on auto-scaler to maintain traffic-based scaling during upgrade

**A100 Pool (Mixed workloads)**
```bash
# Minimal surge for expensive A100s
gcloud container node-pools update a100-mixed-pool \
  --cluster ML_CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```
- `maxSurge=1`: Only 1 extra A100 at a time (quota conservation)
- Fine-tuning jobs protected by PDBs (see workload readiness below)

## Pre-Upgrade Preparation

### 1. GPU driver compatibility testing
**Critical**: Test target GKE 1.30 in a staging cluster first
```bash
# Create staging cluster with identical GPU setup
gcloud container clusters create ml-staging \
  --zone ZONE \
  --cluster-version 1.30.x-gke.XXXX \
  --enable-autoscaling \
  --min-nodes 0 --max-nodes 5

# Test inference workloads + fine-tuning jobs on GKE 1.30
# Verify CUDA version, driver compatibility, framework compatibility
```

### 2. Fine-tuning job protection
```yaml
# PDB for fine-tuning jobs (prevents mid-job eviction)
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: fine-tuning-pdb
  namespace: ml-workloads
spec:
  minAvailable: 100%  # No disruption allowed during active training
  selector:
    matchLabels:
      workload-type: fine-tuning
```

### 3. Inference workload resilience
```bash
# Verify inference deployments have adequate replicas
kubectl get deployments -n inference -o wide
# Ensure >1 replica per model to survive single-node restart

# Check HPA configuration
kubectl get hpa -n inference
# Confirm auto-scaling can compensate for temporary capacity reduction
```

### 4. Maintenance exclusion for active training
```bash
# Block node pool upgrades during critical fine-tuning campaigns
gcloud container clusters update ML_CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-campaign-q1" \
  --add-maintenance-exclusion-start-time "2024-MM-DDTHH:MM:SSZ" \
  --add-maintenance-exclusion-end-time "2024-MM-DDTHH:MM:SSZ" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

## Upgrade Execution Plan

### Phase 1: Control plane (non-disruptive)
```bash
# Upgrade control plane first — no pod restarts
gcloud container clusters upgrade ML_CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.30.x-gke.XXXX

# Validate control plane (10-15 min)
gcloud container clusters describe ML_CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

### Phase 2: L4 pool upgrade (inference priority)
```bash
# Upgrade L4 pool during low-traffic window
gcloud container node-pools upgrade l4-inference-pool \
  --cluster ML_CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30.x-gke.XXXX

# Monitor inference latency during upgrade
# Auto-scaler should maintain serving capacity via surge nodes
```

### Phase 3: A100 pool upgrade (coordinate with ML team)
```bash
# Wait for fine-tuning job completion or checkpoint
# Cordon A100 nodes with active training (optional)
kubectl cordon -l cloud.google.com/gke-nodepool=a100-mixed-pool

# Upgrade A100 pool
gcloud container node-pools upgrade a100-mixed-pool \
  --cluster ML_CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30.x-gke.XXXX
```

## Fallback Strategies

### If GPU surge capacity is unavailable
Switch to blue-green upgrade for the affected pool:
```bash
# Create replacement A100 pool at target version
gcloud container node-pools create a100-mixed-pool-v130 \
  --cluster ML_CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30.x-gke.XXXX \
  --machine-type a2-ultragpu-8g \
  --num-nodes 100 \
  --enable-autoscaling \
  --min-nodes 10 --max-nodes 150

# Migrate workloads gradually
kubectl cordon -l cloud.google.com/gke-nodepool=a100-mixed-pool

# Delete old pool after validation
gcloud container node-pools delete a100-mixed-pool \
  --cluster ML_CLUSTER_NAME --zone ZONE
```

### If fine-tuning job gets disrupted
```bash
# Check training job checkpoints
kubectl logs -n ml-workloads TRAINING_POD | grep checkpoint

# Resume from last checkpoint on upgraded node
# Most training frameworks (PyTorch, JAX) support automatic resumption
```

## Monitoring During Upgrade

### Key metrics to watch
```bash
# Inference latency (p95, p99)
# Model serving errors/timeouts
# GPU utilization across pools
# Training job progress (if active)
# Node autoscaler events
```

### Validation commands
```bash
# GPU driver version on upgraded nodes
kubectl get nodes -o wide -L cloud.google.com/gke-nodepool
kubectl describe nodes NODE_NAME | grep -A 5 "nvidia.com/gpu"

# All inference services responding
kubectl get ingress -n inference
curl -X POST https://INFERENCE_ENDPOINT/health

# Fine-tuning job status
kubectl get pods -n ml-workloads -l workload-type=fine-tuning
```

## Timeline & Communication

**Estimated duration**: 4-6 hours total
- Control plane: 15 minutes
- L4 pool (200 nodes): 2-3 hours  
- A100 pool (100 nodes): 2-3 hours

**Recommended window**: Weekend early morning (low inference traffic)

**Stakeholder coordination**:
- [ ] ML engineers: checkpoint active training jobs
- [ ] Product teams: expect brief inference latency spikes during L4 upgrade
- [ ] On-call: monitor GPU driver compatibility post-upgrade

This plan prioritizes inference availability through surge upgrades while protecting long-running training workloads via PDBs and maintenance exclusions. The staged approach (L4 first, then A100) allows you to validate GPU driver compatibility before upgrading your more expensive A100 fleet.
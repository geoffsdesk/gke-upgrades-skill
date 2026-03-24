# GKE GPU Inference Cluster Upgrade Plan: 1.31 → 1.32

## Cluster Profile
- **Environment:** ML inference + fine-tuning platform
- **Scale:** 300 GPU nodes (200 L4 inference + 100 A100 inference/training)
- **Current:** GKE 1.31 → **Target:** 1.32
- **Workloads:** Auto-scaling inference (latency-sensitive) + 4-8h fine-tuning jobs
- **Priority:** Minimize inference disruption

## Executive Summary

This upgrade requires **different strategies per node pool** due to mixed workload types:
- **L4 inference pool:** Autoscaled blue-green upgrade (preserves serving capacity)
- **A100 mixed pool:** Maintenance exclusion + coordinated upgrade during fine-tuning gaps
- **Estimated timeline:** 2-3 days total with proper coordination

## Version Compatibility Check

```bash
# Verify 1.32 availability in your release channel
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels)" | grep -A 10 "REGULAR\|STABLE"

# Check for deprecated API usage (auto-upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Verify no version skew issues
gcloud container clusters describe CLUSTER_NAME --zone ZONE \
  --format="table(currentMasterVersion, nodePools[].name, nodePools[].version)"
```

## Upgrade Strategy by Node Pool

### L4 Inference Pool (200 nodes) - Autoscaled Blue-Green
**Why this strategy:** Inference workloads need continuous serving capacity. Autoscaled blue-green maintains availability while respecting longer graceful termination periods.

**Benefits over surge:**
- No capacity dips during upgrade
- Respects model unloading graceful termination
- Cost-efficient (scales down old pool as new pool scales up)

**Configuration:**
```bash
gcloud container node-pools update l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 50 --total-max-nodes 250 \
  --strategy=BLUE_GREEN \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s \
  --node-pool-soak-duration=1800s
```

### A100 Mixed Pool (100 nodes) - Coordinated Manual Upgrade
**Why this strategy:** 4-8h fine-tuning jobs exceed GKE's 1-hour surge eviction timeout. Needs coordination.

**Approach:**
1. Use maintenance exclusion to block auto-upgrades
2. Wait for running fine-tuning jobs to complete
3. Manual upgrade during low-traffic periods
4. Use drain-first strategy (no surge GPU capacity needed)

## Pre-Upgrade Preparation

### 1. GPU Driver Compatibility Check
```bash
# Current driver version
kubectl get nodes -l cloud.google.com/gke-nodepool=l4-inference-pool -o yaml | grep nvidia.com/gpu
kubectl get nodes -l cloud.google.com/gke-nodepool=a100-mixed-pool -o yaml | grep nvidia.com/gpu

# Test target version compatibility in staging cluster first
# GKE 1.32 typically ships with NVIDIA driver 535.x series
```

### 2. Set Maintenance Exclusion (A100 Pool Protection)
```bash
# Block auto-upgrades during active fine-tuning campaigns
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "ml-training-protection" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time $(date -u -d "+14 days" +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

### 3. Workload Readiness
```bash
# Verify PDBs for inference services
kubectl get pdb -A | grep -E "inference|serving"

# Check fine-tuning job status
kubectl get pods -l workload-type=training --all-namespaces

# Ensure no bare pods
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

## Upgrade Execution Plan

### Phase 1: Control Plane Upgrade (30 minutes)
```bash
# Off-peak hours recommended (2-4 AM local time)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.latest

# Verify control plane
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"

kubectl get pods -n kube-system
```

### Phase 2: L4 Inference Pool - Autoscaled Blue-Green (4-6 hours)
**Best time:** During moderate traffic (avoid peak hours)

```bash
# Trigger upgrade
gcloud container node-pools upgrade l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest

# Monitor progress
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=l4-inference-pool -o wide'

# Check inference service health during upgrade
kubectl get deployments -l workload-type=inference
kubectl top nodes -l cloud.google.com/gke-nodepool=l4-inference-pool
```

**Expected behavior:**
- Green pool scales up with 25% initial capacity (50 nodes)
- Blue pool cordons and drains in batches
- Total upgrade time: 4-6 hours for 200 nodes
- Serving capacity maintained throughout

### Phase 3: A100 Mixed Pool - Coordinated Upgrade (6-8 hours)

**Step 3a: Wait for fine-tuning jobs to complete**
```bash
# Monitor running training jobs
kubectl get pods -l workload-type=training,node-pool=a100-mixed --all-namespaces

# Check job completion status
kubectl get jobs -l workload-type=training --all-namespaces
```

**Step 3b: Manual upgrade with drain-first strategy**
```bash
# Configure for GPU pools (no surge capacity available)
gcloud container node-pools update a100-mixed-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2

# Trigger upgrade during low inference traffic
gcloud container node-pools upgrade a100-mixed-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest

# Monitor
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=a100-mixed-pool -o wide'
```

**Expected behavior:**
- Drains 2 nodes at a time, then creates replacements
- No extra GPU capacity needed
- Temporary capacity reduction during drain
- ~3-5 hours for 100 nodes

## Validation & Monitoring

### Real-time Monitoring During Upgrade
```bash
# Inference service availability
kubectl get deployments -l workload-type=inference -o wide

# GPU utilization tracking
kubectl top nodes -l node.kubernetes.io/instance-type=g2-standard-96  # L4 nodes
kubectl top nodes -l node.kubernetes.io/instance-type=a2-highgpu-1g   # A100 nodes

# Pod disruption tracking
kubectl get events -A --field-selector reason=Evicted

# HPA scaling behavior
kubectl describe hpa -l workload-type=inference
```

### Post-Upgrade Validation
```bash
# All nodes upgraded
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,POOL:.metadata.labels.cloud\.google\.com/gke-nodepool

# GPU driver versions
kubectl describe nodes -l cloud.google.com/gke-accelerator | grep "nvidia.com/gpu"

# Inference latency baseline comparison
# (Use your monitoring stack - Prometheus/Grafana/Cloud Monitoring)

# Fine-tuning job capability test
kubectl run gpu-test --image=nvidia/cuda:11.8-devel-ubuntu20.04 \
  --limits="nvidia.com/gpu=1" --rm -it --restart=Never \
  -- nvidia-smi
```

## Risk Mitigation

### L4 Pool Risks
- **Autoscaler lag:** Monitor HPA/VPA response during blue-green transition
- **Model loading time:** Account for cold start latency on new nodes
- **Network disruption:** Inference pods may see brief connection resets during drain

### A100 Pool Risks  
- **Long job interruption:** 4-8h fine-tuning jobs will be evicted during upgrade
- **Capacity reduction:** maxUnavailable=2 reduces pool by 2% during drain cycles
- **GPU driver changes:** New CUDA version may affect training frameworks

### Rollback Strategy
```bash
# If issues arise during node pool upgrade
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE

# Blue-green rollback (during soak period)
gcloud container node-pools rollback l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE

# Manual rollback (create new pool at old version)
gcloud container node-pools create a100-rollback-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.previous \
  --machine-type a2-highgpu-1g \
  --accelerator type=nvidia-tesla-a100,count=1 \
  --num-nodes 100
```

## Timeline & Communication

### Estimated Duration
- **Phase 1 (Control plane):** 30 minutes
- **Phase 2 (L4 blue-green):** 4-6 hours  
- **Phase 3 (A100 coordinated):** 6-8 hours
- **Total:** 10-14 hours over 2-3 days

### Stakeholder Communication
```
Timeline:
Day 1: Control plane upgrade (2-4 AM) + L4 pool upgrade (6 AM - 12 PM)
Day 2: Monitor fine-tuning job completion
Day 3: A100 pool upgrade during low-traffic window

Impact:
- Inference: <5% latency increase during L4 upgrade
- Training: 6-8h jobs must complete before A100 upgrade
- Platform: Brief API unavailability during CP upgrade
```

## Post-Upgrade Cleanup

```bash
# Remove maintenance exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "ml-training-protection"

# Verify auto-upgrade resumption
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(maintenancePolicy)"

# Performance baseline comparison
# Compare inference p95 latency, throughput, and training job completion times
```

This strategy balances inference availability (blue-green for L4) with training job protection (coordinated upgrade for A100), minimizing business impact while ensuring both workload types are properly handled.
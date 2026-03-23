# GKE ML Platform Upgrade Plan: 1.31 → 1.32

## Cluster Overview
- **Mode**: Standard  
- **Current**: 1.31 → **Target**: 1.32  
- **Workloads**: GPU inference (L4) + fine-tuning (A100)  
- **Node pools**: 200x L4 (inference), 100x A100 (inference + fine-tuning)  
- **Requirements**: Minimal latency impact, high availability  

## Upgrade Strategy

### GPU Pool Strategy Selection
Given your inference availability requirements and mixed workloads, I recommend **different strategies per pool**:

**L4 Pool (inference-only)**: **Surge upgrade with conservative settings**
- `maxSurge=5, maxUnavailable=0` (5 nodes at a time, ~40 batches)
- Maintains serving capacity throughout
- GPU driver restart is unavoidable but minimizes concurrent disruptions

**A100 Pool (inference + fine-tuning)**: **Cordon-and-wait approach**
- Cordon nodes during fine-tuning job gaps
- Allow natural job completion, then upgrade empty nodes
- Protects 4-8 hour fine-tuning jobs from mid-job eviction

### GPU-Specific Considerations
- **No live migration**: Every GPU node upgrade requires pod restart
- **Driver coupling**: GKE 1.32 may install different CUDA drivers than 1.31
- **Surge capacity**: Assume no extra GPU quota available for blue-green
- **Fine-tuning protection**: 4-8 hour jobs cannot tolerate GKE's 1-hour eviction timeout

## Pre-Upgrade Preparation

### 1. Test GPU Driver Compatibility
```bash
# Create test cluster with target version
gcloud container clusters create gpu-test-132 \
  --zone us-central1-a \
  --cluster-version 1.32 \
  --machine-type n1-standard-4 \
  --num-nodes 1

gcloud container node-pools create l4-test \
  --cluster gpu-test-132 \
  --zone us-central1-a \
  --accelerator type=nvidia-l4,count=1 \
  --machine-type g2-standard-4 \
  --num-nodes 1

gcloud container node-pools create a100-test \
  --cluster gpu-test-132 \
  --zone us-central1-a \
  --accelerator type=nvidia-tesla-a100,count=1 \
  --machine-type a2-highgpu-1g \
  --num-nodes 1
```

Deploy test inference and fine-tuning workloads to verify CUDA/driver compatibility.

### 2. Configure Maintenance Protection for A100 Fine-Tuning
```bash
# Add maintenance exclusion to block upgrades during active training
gcloud container clusters update ML_CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "fine-tuning-protection" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time $(date -u -d "+7 days" +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

### 3. Set Up Monitoring
```bash
# Monitor GPU utilization and inference latency
kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: gpu-metrics-config
data:
  config.yaml: |
    global:
      scrape_interval: 15s
    scrape_configs:
    - job_name: 'dcgm-exporter'
      kubernetes_sd_configs:
      - role: endpoints
      relabel_configs:
      - source_labels: [__meta_kubernetes_service_name]
        action: keep
        regex: dcgm-exporter
EOF
```

## Upgrade Execution

### Phase 1: Control Plane Upgrade (15 minutes)
```bash
# Remove maintenance exclusion temporarily
gcloud container clusters update ML_CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "fine-tuning-protection"

# Upgrade control plane
gcloud container clusters upgrade ML_CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.0-gke.latest

# Verify control plane
gcloud container clusters describe ML_CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"

kubectl get pods -n kube-system | grep -v Running
```

### Phase 2: L4 Inference Pool (Conservative Surge)
```bash
# Configure surge for L4 pool - 5 nodes at a time (2.5% of 200 nodes)
gcloud container node-pools update l4-inference-pool \
  --cluster ML_CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5 \
  --max-unavailable-upgrade 0

# Start L4 upgrade
gcloud container node-pools upgrade l4-inference-pool \
  --cluster ML_CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.0-gke.latest

# Monitor progress (expect ~2-3 hours for 200 nodes in batches of 5)
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=l4-inference-pool -o wide'
```

**Expected timeline**: ~3 hours (40 batches × 4 minutes per batch)

### Phase 3: A100 Pool (Cordon-and-Wait)
```bash
# Wait for fine-tuning jobs to complete naturally
kubectl get pods -n ml-training -o wide | grep a100

# Cordon A100 nodes during job gaps
kubectl cordon -l cloud.google.com/gke-nodepool=a100-mixed-pool

# Monitor until A100 nodes are empty of fine-tuning jobs
kubectl get pods -A --field-selector spec.nodeName=NODE_NAME

# Configure conservative upgrade for A100
gcloud container node-pools update a100-mixed-pool \
  --cluster ML_CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2

# Start A100 upgrade
gcloud container node-pools upgrade a100-mixed-pool \
  --cluster ML_CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.0-gke.latest
```

**Expected timeline**: ~2 hours (50 batches × 2.5 minutes per batch)

## Validation & Monitoring

### Inference Latency Monitoring
```bash
# Check inference pod distribution across upgraded nodes
kubectl get pods -n inference -o wide | grep -E "l4|a100"

# Verify GPU driver version on upgraded nodes
kubectl get nodes -o json | \
  jq -r '.items[] | select(.status.nodeInfo.kubeletVersion | contains("1.32")) | 
         {name:.metadata.name, driver:.status.nodeInfo.kernelVersion}'

# Test inference endpoints
curl -X POST https://your-inference-endpoint/predict \
  -H "Content-Type: application/json" \
  -d '{"test": "payload"}'
```

### Performance Validation Checklist
```markdown
L4 Inference Pool Validation:
- [ ] All 200 L4 nodes at version 1.32
- [ ] Inference pods distributed across upgraded nodes
- [ ] P95 latency within 10% of baseline
- [ ] No increase in inference error rate
- [ ] GPU utilization metrics flowing
- [ ] Cluster autoscaler scaling normally

A100 Mixed Pool Validation:
- [ ] All 100 A100 nodes at version 1.32
- [ ] No active fine-tuning jobs disrupted mid-run
- [ ] New fine-tuning jobs starting successfully
- [ ] Inference workloads on A100s responding normally
- [ ] CUDA driver compatibility confirmed
```

## Rollback Plan

If inference latency degrades significantly:

```bash
# Create new L4 pool at 1.31 for emergency rollback
gcloud container node-pools create l4-rollback-pool \
  --cluster ML_CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.latest \
  --accelerator type=nvidia-l4,count=1 \
  --machine-type g2-standard-4 \
  --enable-autoscaling \
  --min-nodes 50 \
  --max-nodes 250

# Cordon upgraded nodes and let autoscaler migrate workloads
kubectl cordon -l cloud.google.com/gke-nodepool=l4-inference-pool
```

## Timeline Summary

| Phase | Duration | Impact |
|-------|----------|--------|
| Control plane | 15 minutes | None (invisible to workloads) |
| L4 inference pool | 3 hours | 2.5% capacity reduction rolling |
| A100 mixed pool | 2 hours | Fine-tuning protected, minimal inference impact |
| **Total** | **~5.5 hours** | High availability maintained |

## Key Success Factors

1. **Driver testing**: Verify CUDA compatibility in test cluster first
2. **Fine-tuning protection**: Never upgrade A100 nodes with active 4-8h jobs
3. **Conservative surge**: Small batches preserve inference capacity
4. **Monitoring**: Track latency and error rates throughout
5. **Rollback ready**: Keep 1.31 pool config handy for emergency rollback

This approach prioritizes your inference SLA while protecting long-running fine-tuning jobs from mid-job disruption.
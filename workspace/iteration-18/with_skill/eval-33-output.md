# GKE GPU Inference Cluster Upgrade Plan
## Cluster: ML Platform | Standard | 1.31 → 1.32

### Executive Summary
For GPU inference workloads, **autoscaled blue-green** is the optimal upgrade strategy. Unlike surge upgrades that force-restart all GPU pods (causing inference latency spikes), autoscaled blue-green maintains serving capacity by keeping the old pool active while the new pool warms up. This is critical for inference SLAs.

### Environment Analysis
- **L4 inference pool (200 nodes):** Latency-sensitive serving workloads
- **A100 mixed pool (100 nodes):** Inference + 4-8 hour fine-tuning jobs
- **Auto-scaling:** Both pools scale based on demand
- **Key constraint:** GPU VMs don't support live migration — every upgrade requires pod restart

### Upgrade Strategy by Pool

#### L4 Inference Pool: Autoscaled Blue-Green
**Why this strategy:** Maintains inference availability throughout upgrade. Old nodes keep serving while new nodes warm up.

```bash
# Configure autoscaled blue-green for L4 pool
gcloud container node-pools update l4-inference-pool \
  --cluster ML_CLUSTER_NAME \
  --region REGION \
  --enable-autoscaling \
  --total-min-nodes 50 --total-max-nodes 250 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

**Process:** Creates 25% initial green capacity → Autoscales green pool as traffic shifts → Scales down blue pool as pods drain → Zero serving interruption

#### A100 Mixed Pool: Coordinated Approach
**Challenge:** Fine-tuning jobs (4-8 hours) exceed GKE's 1-hour surge timeout.

**Solution:** Time upgrade during fine-tuning gaps OR use job checkpointing.

```bash
# Option 1: Maintenance exclusion during active fine-tuning
gcloud container clusters update ML_CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "fine-tuning-campaign" \
  --add-maintenance-exclusion-start-time "2024-01-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-01-20T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Option 2: Autoscaled blue-green with extended grace period (if jobs have checkpointing)
gcloud container node-pools update a100-mixed-pool \
  --cluster ML_CLUSTER_NAME \
  --region REGION \
  --enable-autoscaling \
  --total-min-nodes 25 --total-max-nodes 125 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.30,blue-green-full-batch-timeout=7200s
```

### GPU-Specific Considerations

#### Driver Compatibility Validation
**Critical:** GKE 1.32 may change CUDA driver versions. Test in staging first.

```bash
# Create staging node pool with target version
gcloud container node-pools create staging-l4-test \
  --cluster ML_CLUSTER_NAME \
  --region REGION \
  --node-version 1.32.x-gke.xxxx \
  --machine-type g2-standard-24 \
  --accelerator type=nvidia-l4,count=2 \
  --num-nodes 2

# Deploy representative inference workload and validate
kubectl apply -f inference-test-deployment.yaml
# Check CUDA version, model loading, throughput
```

#### Reservation Capacity Check
**Before upgrade:** Verify GPU reservation has headroom for blue-green (requires ~25-30% extra capacity during transition).

```bash
gcloud compute reservations describe YOUR_GPU_RESERVATION --zone ZONE
# Check: in_use_count vs count — ensure capacity for blue-green overlap
```

### Pre-Upgrade Checklist

**GPU Workload Readiness:**
- [ ] Inference models tested on GKE 1.32 + new CUDA drivers in staging
- [ ] Fine-tuning jobs have checkpointing enabled OR upgrade scheduled during job gaps
- [ ] GPU reservation has 25-30% headroom for blue-green overlap
- [ ] Autoscaler min/max nodes configured for blue-green pools
- [ ] PDBs configured: `minAvailable: 1` per inference deployment

**Infrastructure:**
- [ ] Maintenance window: Schedule during lowest inference traffic (typically 2-6 AM)
- [ ] Monitoring: Baseline inference latency (p95/p99), GPU utilization, job completion rates
- [ ] Rollback plan: Keep blue pools cordoned (not deleted) for 24h post-upgrade

### Execution Runbook

#### Phase 1: Control Plane (10-15 minutes)
```bash
# Upgrade control plane first
gcloud container clusters upgrade ML_CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version 1.32.x-gke.xxxx

# Verify
gcloud container clusters describe ML_CLUSTER_NAME \
  --region REGION \
  --format="value(currentMasterVersion)"
```

#### Phase 2: L4 Inference Pool (45-60 minutes)
```bash
# Start autoscaled blue-green upgrade
gcloud container node-pools upgrade l4-inference-pool \
  --cluster ML_CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.32.x-gke.xxxx

# Monitor: Old pool scales down as new pool scales up
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=l4-inference-pool -o wide'

# Validate inference latency during transition
kubectl logs -f inference-monitoring-pod
```

#### Phase 3: A100 Mixed Pool (timing-dependent)
```bash
# If during fine-tuning gap: proceed with upgrade
gcloud container node-pools upgrade a100-mixed-pool \
  --cluster ML_CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.32.x-gke.xxxx

# If jobs running: wait OR apply exclusion to defer
```

### Post-Upgrade Validation

**GPU Health:**
```bash
# All nodes at target version
gcloud container node-pools list --cluster ML_CLUSTER_NAME --region REGION

# GPU driver version
kubectl describe nodes -l cloud.google.com/gke-accelerator=nvidia-l4 | grep "nvidia.com/gpu"

# No pods in error state
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded
```

**Inference Performance:**
- [ ] Inference latency p95/p99 within 5% of pre-upgrade baseline
- [ ] Model loading time unchanged
- [ ] GPU utilization patterns normal
- [ ] Auto-scaling behavior correct (scaling up/down based on traffic)

### Troubleshooting

**Issue: Blue-green timeout during transition**
```bash
# Check if green nodes are ready
kubectl get nodes -l cloud.google.com/gke-nodepool=NEW_POOL_NAME

# Check pod scheduling on green nodes
kubectl get pods -A -o wide | grep NEW_NODE_NAME
```

**Issue: Inference latency spike during transition**
```bash
# Verify pods distributed across both blue and green pools
kubectl get pods -n inference -o wide

# Check GPU utilization
kubectl top nodes --sort-by=memory
```

**Issue: Fine-tuning job interrupted**
```bash
# If job has checkpointing: resume from last checkpoint
# If no checkpointing: restart job on upgraded nodes
kubectl get jobs -n training --show-labels
```

### Timeline Estimate
- **Control plane:** 15 minutes
- **L4 pool (autoscaled blue-green):** 45-60 minutes
- **A100 pool:** 60-90 minutes (or deferred based on fine-tuning schedule)
- **Total window:** 2-3 hours

### Rollback Plan
If critical issues arise:
1. **Blue pools remain cordoned** (not deleted) for 24 hours
2. **Uncordon blue pool:** `kubectl uncordon NODE_NAME` 
3. **Scale down green pool:** Adjust autoscaling min/max
4. **Route traffic back to blue pool:** Update service selectors if needed

This approach minimizes inference disruption while handling the unique constraints of GPU workloads and mixed inference/training usage patterns.
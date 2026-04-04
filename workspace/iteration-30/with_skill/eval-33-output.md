# GKE Upgrade Plan: ML Inference Platform (1.31 → 1.32)

## Executive Summary
**Cluster:** ML Platform | **Mode:** Standard | **Channel:** (needs confirmation)
**Current:** 1.31 | **Target:** 1.32 | **Node Pools:** L4 inference (200 nodes) + A100 hybrid (100 nodes)

**Key Strategy:** Autoscaled blue-green for inference pools to minimize latency spikes, with fine-tuning job protection during A100 upgrade.

## Pre-Upgrade Assessment

### Version Compatibility
- [ ] Confirm 1.32 available in your release channel: `gcloud container get-server-config --zone ZONE --format="yaml(channels)"`
- [ ] **Critical:** Test GPU driver compatibility - GKE 1.32 may change CUDA versions
  ```bash
  # Create staging node pool with 1.32 to validate
  gcloud container node-pools create staging-test \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version 1.32.x-gke.xxx \
    --machine-type g2-standard-4 \
    --accelerator type=nvidia-l4,count=1 \
    --num-nodes 1
  ```
- [ ] Verify inference model loading and throughput on 1.32 staging nodes before production upgrade
- [ ] Check for deprecated APIs: `kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated`

### GPU-Specific Constraints
**L4 Pool (Inference):**
- GPU VMs don't support live migration - every upgrade causes pod restarts
- Inference latency spikes are inevitable with surge upgrades
- **Recommendation:** Autoscaled blue-green to keep old nodes serving while new nodes warm up

**A100 Pool (Inference + Fine-tuning):**
- 4-8 hour fine-tuning jobs exceed GKE's 1-hour eviction timeout
- Surge upgrades will force-kill running fine-tuning jobs
- **Recommendation:** Coordinate upgrade timing with job scheduling

## Upgrade Strategy

### 1. Control Plane Upgrade
```bash
# Schedule during low-traffic period
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.xxx
```
**Impact:** ~10-15 minutes of reduced API availability. Inference workloads continue running.

### 2. L4 Inference Pool - Autoscaled Blue-Green
**Why this strategy:** Minimizes inference latency by avoiding drain-and-restart. Old pool serves traffic while new pool warms up.

```bash
# Configure autoscaled blue-green
gcloud container node-pools update l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 50 \
  --total-max-nodes 250 \
  --strategy BLUE_GREEN \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

# Trigger upgrade
gcloud container node-pools upgrade l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxx
```

**Process:**
1. Green pool scales up with 25% initial capacity (50 nodes)
2. As traffic shifts, green scales up while blue scales down
3. Cost-efficient - avoids 2x resource spike of standard blue-green
4. **Duration:** ~2-3 hours for 200 nodes

### 3. A100 Hybrid Pool - Fine-tuning Job Protection
**Challenge:** Running fine-tuning jobs (4-8 hours) will be force-evicted after 1 hour with surge.

**Option A - Job-Aware Timing (Recommended):**
```bash
# Check for running fine-tuning jobs
kubectl get pods -n FINETUNING_NAMESPACE -l job-type=finetuning --field-selector=status.phase=Running

# If jobs running: Apply maintenance exclusion, wait for completion
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "await-finetuning-completion" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+12 hours' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades

# When jobs complete, remove exclusion and upgrade with autoscaled blue-green
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "await-finetuning-completion"

gcloud container node-pools update a100-hybrid-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --strategy BLUE_GREEN \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.20

gcloud container node-pools upgrade a100-hybrid-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxx
```

**Option B - Surge with Job Checkpointing:**
```bash
# Only if fine-tuning jobs support checkpointing
gcloud container node-pools update a100-hybrid-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2  # Drains 2 nodes at a time, no extra A100s needed

# Set longer grace period on fine-tuning pods (up to 1 hour respected)
# In pod spec: terminationGracePeriodSeconds: 3600
```

## Workload Preparation

### Inference Workload Readiness
```bash
# Configure PDBs for inference services (protect during blue-green transition)
kubectl apply -f - <<EOF
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: inference-pdb
spec:
  minAvailable: 80%  # Ensure 80% inference capacity during transition
  selector:
    matchLabels:
      workload-type: inference
EOF
```

### Fine-tuning Job Protection
```bash
# Add safe-to-evict annotation to long-running jobs
kubectl annotate pods -l job-type=finetuning \
  cluster-autoscaler.kubernetes.io/safe-to-evict=false
```

### Autoscaler Configuration
```bash
# Prevent autoscaler from creating new nodes at old version during upgrade
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --min-nodes 0 \
  --max-nodes 0  # Temporarily disable autoscaling during upgrade window
```

## Monitoring and Validation

### Pre-Upgrade Baseline
```bash
# Capture inference latency baseline
kubectl top nodes -l accelerator=nvidia-l4
kubectl get pods -l workload-type=inference -o wide | wc -l  # Pod count
# Monitor your inference latency metrics (p95, p99)
```

### During Upgrade Monitoring
```bash
# Watch node upgrade progress
watch 'kubectl get nodes -l accelerator=nvidia-l4 -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,STATUS:.status.conditions[-1].type'

# Monitor inference pod distribution
watch 'kubectl get pods -l workload-type=inference -o wide | grep -E "l4-inference-pool|Running" | wc -l'

# Check for GPU allocation issues
kubectl get events -A --field-selector reason=FailedScheduling | grep -i gpu
```

### Post-Upgrade Validation
```bash
# Verify all nodes at target version
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE

# Test inference endpoint health
# Your inference health check commands here

# Validate GPU allocation
kubectl run gpu-test --image=tensorflow/tensorflow:latest-gpu --limits=nvidia.com/gpu=1 --rm -it --restart=Never -- nvidia-smi

# Check autoscaler resumed
gcloud container clusters describe CLUSTER_NAME --zone ZONE --format="value(nodePools[0].autoscaling)"
```

## Timeline and Impact

| Phase | Duration | Impact |
|-------|----------|--------|
| Control Plane | 15 minutes | Minimal - inference continues |
| L4 Pool (Blue-Green) | 2-3 hours | Low - gradual traffic shift |
| A100 Pool (Blue-Green) | 1.5-2 hours | Low - inference preserved, fine-tuning paused |
| **Total** | **4-5 hours** | **Minimal inference disruption** |

## Risk Mitigation

### GPU Driver Issues
- **Risk:** CUDA version change breaks inference models
- **Mitigation:** Mandatory staging validation before production
- **Rollback:** Create new pool at 1.31, migrate workloads

### Autoscaler During Upgrade
- **Risk:** New nodes provisioned at old version during upgrade
- **Mitigation:** Temporarily constrain autoscaling during upgrade window
- **Recovery:** Re-enable autoscaling post-upgrade

### Fine-tuning Job Loss
- **Risk:** 4-8 hour jobs force-evicted during surge
- **Mitigation:** Use job-aware timing or autoscaled blue-green with extended termination periods

## Rollback Plan

If critical issues arise:

```bash
# Option 1: Complete current phase, create rollback pool
gcloud container node-pools create POOL_NAME-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.xxx \
  --machine-type MACHINE_TYPE \
  --accelerator type=ACCELERATOR_TYPE,count=COUNT

# Option 2: Blue-green rollback (if still in soak period)
gcloud container node-pools rollback POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE
```

**Critical:** Control plane cannot be downgraded from 1.32→1.31 without GKE support involvement.

## Recommended Execution Window

**Optimal timing:** Weekend or low-traffic period when:
- Fewer inference requests (reduced impact of latency spikes)
- No scheduled fine-tuning jobs
- ML engineering team available for validation

**Pre-execution:** Complete staging validation 1 week prior to confirm GPU driver compatibility with your inference models.

This plan prioritizes inference availability through autoscaled blue-green while protecting long-running fine-tuning jobs. The total upgrade takes 4-5 hours but with minimal inference disruption compared to standard surge upgrades that would cause repeated latency spikes.
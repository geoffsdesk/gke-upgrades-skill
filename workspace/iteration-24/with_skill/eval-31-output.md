# LLM Training Cluster Upgrade Plan: GKE 1.31 → 1.32

**Cluster Profile:**
- **Scale:** 512 H100 nodes (A3 Mega), 4,096 GPUs total
- **Workload:** 2-3 week LLM training runs
- **Network:** GPUDirect-TCPXO interconnect
- **Current:** GKE 1.31 → **Target:** GKE 1.32

## Critical Constraints for LLM Training

### 1. **Training Job Protection (Primary Concern)**

Your 2-3 week training runs cannot tolerate mid-job eviction. GKE's default surge upgrade evicts pods after 1 hour — far shorter than your training duration.

**Immediate Action Required:**
```bash
# Block ALL node upgrades during active training runs
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "training-campaign-q1" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time "2025-04-01T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

This allows control plane security patches but blocks disruptive node upgrades until your training completes.

### 2. **GPUDirect-TCPXO Compatibility**

**✅ Good News:** GKE 1.32 maintains GPUDirect-TCPXO support for A3 Mega machines. Your interconnect will survive the upgrade.

**Validation Required:**
```bash
# Verify current TCPXO configuration
kubectl get nodes -o jsonpath='{.items[*].metadata.labels}' | grep tcpx
kubectl describe nodes | grep -i "gpu\|tcpx\|rdma"
```

### 3. **Upgrade Strategy for 512-Node Scale**

With 512 GPU nodes, standard upgrade approaches face severe constraints:

**❌ Surge Upgrade Issues:**
- **No surge capacity:** H100 reservations are typically fixed with zero headroom
- **Force-eviction at 1 hour:** Will terminate active training
- **GPU "musical chairs":** High maxSurge drains many nodes before replacements exist

**✅ Recommended: Custom Parallel Host Maintenance Strategy**

Since you can tolerate full restart between training runs, use GKE's AI Host Maintenance with parallel strategy:

## Recommended Upgrade Plan

### Phase 1: Control Plane Upgrade (Safe During Training)

```bash
# Control plane upgrade — no impact on running training
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version 1.32.x-gke.latest

# Monitor (takes ~10-15 minutes)
watch 'gcloud container clusters describe CLUSTER_NAME --region REGION --format="value(currentMasterVersion)"'
```

**Impact:** Zero disruption to training jobs. Control plane upgrades don't affect running workloads.

### Phase 2: Wait for Training Completion

**Timeline Strategy:**
- Keep the "no minor or node upgrades" exclusion active
- Monitor training job completion
- Plan node upgrade for the gap between training runs

```bash
# Monitor training job status
kubectl get pods -n training --field-selector=status.phase=Running
kubectl logs -n training TRAINING_POD_NAME --tail=100
```

### Phase 3: Node Pool Upgrade (Between Training Runs Only)

**Option A: Parallel Host Maintenance (Fastest - 4-6 hours total)**

When training completes and before the next run starts:

```bash
# Scale training workloads to zero
kubectl scale deployment training-workload --replicas=0 -n training

# Apply parallel host maintenance to ALL nodes
kubectl label nodes -l cloud.google.com/gke-nodepool=gpu-pool \
  cloud.google.com/perform-maintenance=true

# Monitor maintenance progress (~4 hours per update)
kubectl get nodes -o wide --watch
```

**Option B: Autoscaled Blue-Green (Safer but requires 2x capacity)**

Only if you have surge capacity for 512 additional H100 nodes:

```bash
# Configure autoscaled blue-green
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --strategy=AUTOSCALED_BLUE_GREEN \
  --enable-autoscaling \
  --total-min-nodes 0 --total-max-nodes 1024 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.1

# Trigger upgrade
gcloud container node-pools upgrade gpu-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.32.x-gke.latest
```

**Option C: Create New Pool + Migrate (Most Control)**

```bash
# Create new pool at target version
gcloud container node-pools create gpu-pool-132 \
  --cluster CLUSTER_NAME \
  --region REGION \
  --machine-type a3-megagpu-8g \
  --num-nodes 512 \
  --cluster-version 1.32.x-gke.latest \
  --accelerator type=nvidia-h100-mega-80gb,count=8 \
  --enable-gvnic \
  --placement-policy-type COMPACT

# Verify GPUDirect-TCPXO on new nodes
kubectl get nodes -l cloud.google.com/gke-nodepool=gpu-pool-132
kubectl describe nodes -l cloud.google.com/gke-nodepool=gpu-pool-132 | grep -i tcpx

# Schedule next training run on new pool
# Delete old pool after validation
```

## Critical Pre-Upgrade Validation

### 1. **Staging Cluster Test (Mandatory)**

**Never upgrade production GPU training clusters without staging validation.**

```bash
# Create staging cluster with target version
gcloud container clusters create staging-training \
  --region REGION \
  --cluster-version 1.32.x-gke.latest \
  --machine-type a3-megagpu-8g \
  --num-nodes 8 \
  --accelerator type=nvidia-h100-mega-80gb,count=8

# Test GPUDirect-TCPXO functionality
kubectl apply -f gpu-interconnect-test.yaml
# Run multi-node NCCL benchmarks to verify topology
```

### 2. **Driver Compatibility Check**

```bash
# Check current driver version
kubectl get nodes -o jsonpath='{.items[0].status.nodeInfo.kernelVersion}'
nvidia-smi --query-gpu=driver_version --format=csv,noheader,nounits

# Verify target GKE 1.32 driver supports your CUDA workloads
# Test model loading and training initialization on staging
```

### 3. **Backup/Checkpoint Strategy**

```bash
# Ensure training checkpointing is active
kubectl exec -it training-pod -n training -- ls -la /checkpoint/
# Verify checkpoint frequency (every 1-2 hours recommended)
# Test checkpoint restore on staging cluster
```

## Upgrade Timing Strategy

### Optimal Timing Windows:

1. **Between training campaigns:** 2-3 day gaps between major training runs
2. **Planned maintenance windows:** Weekend or holiday periods
3. **After checkpoint completion:** Ensure latest checkpoint is saved before starting

### Communication Plan:

```bash
# Remove maintenance exclusion 24h before planned upgrade
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --remove-maintenance-exclusion "training-campaign-q1"

# Apply new exclusion for upgrade window
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "upgrade-window" \
  --add-maintenance-exclusion-start-time "2025-02-15T18:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-02-16T06:00:00Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## Rollback Plan

If the upgrade breaks interconnect or training performance:

**Immediate Rollback (if using new pool approach):**
```bash
# Cordon new pool
kubectl cordon -l cloud.google.com/gke-nodepool=gpu-pool-132

# Restart training on old pool
kubectl scale deployment training-workload --replicas=1 -n training
kubectl get pods -n training -o wide  # Verify scheduling to old pool
```

**Extended Rollback (if parallel maintenance used):**
- Contact GKE Support immediately with cluster details
- Parallel maintenance cannot be easily reversed
- May require cluster recreation from backup

## Post-Upgrade Validation

```bash
# Verify all nodes upgraded
kubectl get nodes -o wide

# Test GPU interconnect
kubectl apply -f nccl-test-job.yaml
kubectl logs job/nccl-test

# Verify TCPXO topology
kubectl describe nodes | grep -A5 -B5 "tcpx\|rdma"

# Start small training test (1-2 hours) before full campaign
kubectl apply -f training-test-job.yaml
```

## Key Recommendations

1. **Use maintenance exclusions religiously** — never attempt node upgrades during active training
2. **Stage everything** — GPUDirect-TCPXO is complex; validate thoroughly before production
3. **Parallel host maintenance is your best option** given the 2-3 week training constraint
4. **Plan for 4-6 hour upgrade windows** with parallel maintenance across 512 nodes
5. **Checkpoint frequently** and verify restore works on the target GKE version

This approach protects your current training run while providing a safe path to GKE 1.32 during your next training gap.
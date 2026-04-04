# Large-Scale GKE Upgrade Plan: 3,000-Node Multi-Pool Cluster

Your upgrade timeout issue is common at this scale. With GKE's ~20-node concurrent upgrade limit, your 3,000-node cluster requires ~150 batches minimum, which can take days to weeks. An 8-hour weekend window is insufficient.

## Root Cause Analysis

**Why upgrades timeout:**
- GKE upgrades ~20 nodes simultaneously regardless of `maxSurge` setting
- 3,000 nodes ÷ 20 concurrent = ~150 batches minimum
- GPU nodes take longer (driver installs, resource constraints)
- Mixed node pools compound the duration

## Recommended Strategy: Phased Multi-Weekend Approach

### Phase 1: CPU Pools First (Weekend 1)
CPU pools upgrade faster and carry lower risk. Target your 4 CPU pools first:

```bash
# Weekend 1: CPU pools only (assume ~1,500 nodes)
# Configure conservative surge for large pools
gcloud container node-pools update CPU-POOL-1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 50 \
  --max-unavailable-upgrade 0

# Repeat for all CPU pools, then upgrade
gcloud container node-pools upgrade CPU-POOL-1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

**Extend your maintenance window for Weekend 1:**
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-duration 20h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### Phase 2: GPU Pools (Weekend 2)
GPU pools require special handling due to driver coupling and capacity constraints:

```bash
# GPU pools: maxUnavailable is the primary lever (assume fixed reservations)
gcloud container node-pools update A100-POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4

# Stagger GPU pool upgrades (don't run all 4 simultaneously)
# A100 + H100 first (highest value/risk), then L4 + T4
```

## Critical Optimizations for Your Scale

### 1. **Increase maxSurge/maxUnavailable strategically:**
- **CPU pools:** 5% of pool size (e.g., 500-node pool → maxSurge=25)
- **GPU pools with fixed reservations:** `maxSurge=0, maxUnavailable=2-4` (increase maxUnavailable for faster GPU upgrades)
- **Calculate percentage-based:** For a 400-node CPU pool, 5% = 20 nodes concurrent

### 2. **Sequence node pools carefully:**
```bash
# Weekend 1: Low-risk CPU pools
CPU-POOL-1 → CPU-POOL-2 → CPU-POOL-3 → CPU-POOL-4

# Weekend 2: High-value GPU pools  
A100-POOL → H100-POOL → L4-POOL → T4-POOL
```

### 3. **Pre-upgrade capacity management:**
Scale down non-critical workloads before upgrades to free quota for surge nodes:
```bash
# Friday evening: scale down dev/staging workloads
kubectl scale deployment non-critical-app --replicas=0 -n dev
kubectl scale deployment batch-jobs --replicas=0 -n staging
```

### 4. **Configure disruption intervals to prevent back-to-back upgrades:**
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-minor-version-disruption-interval=604800s \
  --maintenance-patch-version-disruption-interval=86400s
```

## Long-term Architecture Recommendations

### **Split into multiple clusters** (recommended for 1,000+ nodes):
- **GPU training cluster:** A100/H100 pools only
- **GPU inference cluster:** L4/T4 pools only  
- **CPU workload clusters:** Split by environment or team

Benefits:
- Independent upgrade schedules
- Smaller blast radius
- Specialized configurations per workload type
- Better resource isolation

### **Enable rollout sequencing** for your fleet:
```bash
gcloud container fleet clusterupgrade update \
  --project=PROJECT_ID \
  --default-upgrade-soaking=7d
```

## GPU-Specific Considerations

### **Driver version coupling warning:**
Each GKE version installs specific GPU drivers. **Test target version in staging first:**

```bash
# Create staging GPU node pool with target version
gcloud container node-pools create staging-gpu-test \
  --cluster STAGING_CLUSTER \
  --zone ZONE \
  --cluster-version TARGET_VERSION \
  --accelerator type=nvidia-tesla-a100,count=1 \
  --num-nodes 1
```

Deploy representative inference/training workloads and validate:
- CUDA compatibility
- Model loading
- Throughput benchmarks

### **GPU reservation constraints:**
If you have fixed GPU reservations, assume **no surge capacity available**:
```bash
# GPU pools: Use maxUnavailable as primary lever
gcloud container node-pools update GPU-POOL-NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2
```

## Maintenance Window Strategy

### **Option A: Extended single weekend (20+ hours)**
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-duration 24h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### **Option B: Split across 2-3 weekends with maintenance exclusions**
```bash
# Block auto-upgrades, manually control timing
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "manual-upgrade-control" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## Monitoring and Validation

### **Track upgrade progress:**
```bash
# Monitor node versions across pools
watch 'gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE --format="table(name,version,status)"'

# Check upgrade operations
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --limit=5
```

### **GPU workload validation post-upgrade:**
```bash
# Verify GPU nodes are schedulable
kubectl get nodes -l cloud.google.com/gke-accelerator -o wide

# Test GPU workload deployment
kubectl run gpu-test --image=nvidia/cuda:11.0-runtime-ubuntu18.04 \
  --limits="nvidia.com/gpu=1" \
  --rm -it --restart=Never -- nvidia-smi
```

## Emergency Procedures

### **If upgrade stalls mid-weekend:**
1. **Identify blocking issue:** `kubectl get pods -A | grep -E "Terminating|Pending"`
2. **Address PDBs:** `kubectl get pdb -A -o wide | grep "0    "`  
3. **Scale down non-critical workloads** to free capacity
4. **Contact GKE support** with cluster name, zone, operation ID

### **Rollback plan:**
For GPU pools, rollback requires creating new pools at previous version:
```bash
gcloud container node-pools create GPU-POOL-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version PREVIOUS_VERSION \
  --accelerator type=nvidia-tesla-a100,count=8 \
  --num-nodes ORIGINAL_COUNT
```

## Next Steps

1. **This weekend:** Implement Phase 1 (CPU pools) with extended 20-hour window
2. **Following weekend:** Phase 2 (GPU pools) with staging validation first  
3. **Long-term:** Evaluate cluster splitting for better operational control

**Key insight:** At 3,000+ nodes, upgrades are multi-day operations. Plan accordingly and consider architectural changes to reduce blast radius.

Would you like me to detail the specific commands for your GPU reservation setup or help plan the cluster splitting strategy?
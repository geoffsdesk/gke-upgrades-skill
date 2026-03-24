# Large-Scale GKE Cluster Upgrade Plan

## The Challenge: Upgrade Duration at 3,000-Node Scale

Your upgrade timeout issue is caused by **GKE's maximum upgrade parallelism** (~20 nodes simultaneously, increasing to 100 in upcoming releases). For a 3,000-node cluster:

- **Current parallelism (20 nodes):** ~150 batches minimum = 12+ hours just for node processing
- **Sequential node pool processing:** GKE upgrades one pool at a time by default, multiplying duration
- **GPU pool constraints:** Fixed reservations likely have zero surge capacity, forcing drain-first upgrades

**Your 8-hour Saturday window is insufficient for a full cluster upgrade with current approach.**

## Recommended Strategy: Phased Multi-Weekend Approach

### Phase 1: Control Plane + CPU Pools (Weekend 1)
**Maintenance window:** Saturday 2am-10am

```bash
# Step 1: Control plane upgrade (15-20 minutes)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION

# Step 2: CPU pools only (configure for 8-hour window)
# Prioritize CPU pools - they typically have surge capacity
for POOL in cpu-pool-1 cpu-pool-2 cpu-pool-3 cpu-pool-4; do
  gcloud container node-pools update $POOL \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --max-surge-upgrade 5% \
    --max-unavailable-upgrade 0
  
  gcloud container node-pools upgrade $POOL \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version TARGET_VERSION &
done

# Monitor all CPU pool upgrades in parallel
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep -E "cpu-pool"'
```

### Phase 2: GPU Pools (Weekend 2)
**Maintenance window:** Saturday 2am-10am

```bash
# GPU pools - assume fixed reservations with zero surge capacity
# Use drain-first strategy with increased maxUnavailable for faster completion

for POOL in a100-pool h100-pool l4-pool t4-pool; do
  gcloud container node-pools update $POOL \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --max-surge-upgrade 0 \
    --max-unavailable-upgrade 2
  
  gcloud container node-pools upgrade $POOL \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version TARGET_VERSION &
done
```

**Key GPU considerations:**
- **maxUnavailable=2** creates temporary capacity loss but speeds completion
- **A100/H100 pools:** Consider maxUnavailable=1 if workloads are disruption-sensitive
- **L4/T4 pools:** Can tolerate maxUnavailable=3-4 for faster completion
- **Training workloads:** Ensure jobs are checkpointed before upgrade window

## Alternative Strategy: Extended Maintenance Windows

If phased upgrades aren't acceptable, extend your maintenance window:

### Option A: 24-Hour Weekend Window
**Schedule:** Saturday 12am - Sunday 12am
- Allows full cluster upgrade in one weekend
- Requires stakeholder buy-in for extended disruption window

### Option B: Consecutive Weekend Maintenance
```bash
# Configure maintenance window for consecutive Saturdays
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-duration 8h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## Upgrade Acceleration Techniques

### 1. Parallel Node Pool Upgrades (Preview - April 2026)
```bash
# Enable concurrent nodepool upgrades for auto-upgrades
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --enable-parallel-nodepool-upgrade
```

### 2. Skip-Level Node Pool Upgrades
After control plane reaches target version, skip intermediate versions for node pools:

```bash
# Example: If CP goes 1.29→1.30→1.31, upgrade nodes directly 1.29→1.31
# Reduces total upgrade cycles by ~33%

gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.latest  # Skip 1.30
```

### 3. Optimize maxSurge per Pool Type

**CPU pools (surge capacity available):**
```bash
# Percentage-based surge for scaling
POOL_SIZE=$(gcloud container node-pools describe $POOL --cluster CLUSTER_NAME --zone ZONE --format="value(initialNodeCount)")
MAX_SURGE=$((POOL_SIZE * 5 / 100))  # 5% of pool size, minimum 1
MAX_SURGE=$(( MAX_SURGE > 20 ? 20 : MAX_SURGE ))  # Cap at current parallelism limit

gcloud container node-pools update $POOL \
  --max-surge-upgrade $MAX_SURGE \
  --max-unavailable-upgrade 0
```

**GPU pools (fixed reservations):**
```bash
# Check reservation headroom first
gcloud compute reservations describe GPU_RESERVATION_NAME --zone ZONE

# If no surge capacity:
gcloud container node-pools update $POOL \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2  # Adjust based on workload tolerance
```

## Long-Running Training Job Protection

For your GPU clusters running multi-day training:

### Pre-Upgrade Training Coordination
```bash
# Apply maintenance exclusion during active training campaigns
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-campaign-jan-2024" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

### Dedicated Training Pool Strategy
```bash
# Separate pools for training vs inference
# Training pools: maintenance exclusions + manual upgrades during job gaps
# Inference pools: auto-upgrades with careful scheduling

gcloud container node-pools update training-a100-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --add-nodepool-maintenance-exclusion-name "block-training-disruption" \
  --add-nodepool-maintenance-exclusion-scope no_upgrades \
  --add-nodepool-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-nodepool-maintenance-exclusion-end-time "2024-01-31T23:59:59Z"
```

## Monitoring and Validation

### Track Progress Across All Pools
```bash
# Real-time upgrade monitoring
watch '
echo "Control Plane Version:"
gcloud container clusters describe CLUSTER_NAME --zone ZONE --format="value(currentMasterVersion)"
echo -e "\nNode Pool Status:"
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE --format="table(name,version,status)"
echo -e "\nNodes by Version:"
kubectl get nodes -o custom-columns="POOL:.metadata.labels[cloud\.google\.com/gke-nodepool],VERSION:.status.nodeInfo.kubeletVersion" --sort-by=.metadata.labels
'
```

### Post-Upgrade Validation
```bash
# GPU-specific health checks
kubectl get nodes -l accelerator -o wide
kubectl describe nodes -l accelerator | grep -A 5 "Allocated resources"

# Verify GPU driver versions
kubectl get nodes -o json | jq -r '.items[] | select(.metadata.labels["accelerator"] != null) | {name: .metadata.name, driver: .status.nodeInfo.kernelVersion}'

# Test GPU workload scheduling
kubectl run gpu-test --image=nvidia/cuda:11.0-runtime-ubuntu20.04 \
  --limits="nvidia.com/gpu=1" --rm -it --restart=Never -- nvidia-smi
```

## Recommended Timeline

**8 weeks before upgrade:**
- [ ] Control plane upgrade (weekend 1)
- [ ] CPU pools upgrade (weekend 1 continuation)

**4 weeks before upgrade:**
- [ ] GPU pools upgrade (weekend 2)
- [ ] End-to-end validation

**Week before:**
- [ ] Staging cluster validation
- [ ] Training job coordination
- [ ] Stakeholder communication

## Key Warnings

⚠️ **Never attempt all 8 node pools in one 8-hour window** - mathematically impossible with current GKE parallelism limits

⚠️ **GPU reservations:** Verify surge capacity exists before using maxSurge > 0 on GPU pools

⚠️ **Mixed-version state is normal and functional** during multi-phase upgrades - no need to rush completion

⚠️ **Training jobs:** Coordinate upgrade timing with ML teams to avoid interrupting multi-day training runs

This phased approach ensures successful upgrades within your operational constraints while minimizing risk to your large-scale AI/ML workloads.
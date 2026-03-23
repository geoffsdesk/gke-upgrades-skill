Your proposed approach will work, but there are potentially better alternatives depending on your specific needs and constraints. Let me break down the options:

## Your Proposed Approach (Manual Migration)
**Process:**
1. Create new 1.32 node pool
2. Cordon old nodes (`kubectl cordon`)
3. Drain nodes manually (`kubectl drain`)
4. Delete old pool

**Pros:**
- Maximum control over timing
- Can handle workloads that don't support disruption gracefully
- Good for stateful workloads or those with complex scheduling requirements

**Cons:**
- Manual overhead for 128 nodes
- Requires double capacity during migration (256 A100s temporarily)
- More prone to human error

## Better Alternatives

### 1. **In-Place Node Pool Upgrade** (Recommended for most cases)
```bash
gcloud container node-pools upgrade POOL_NAME \
    --cluster=CLUSTER_NAME \
    --zone=ZONE \
    --node-version=1.32.x
```

**Pros:**
- No double capacity needed
- Automated surge upgrade process
- Maintains reservations on same nodes
- Built-in rollback capabilities

**Cons:**
- Less control over individual node timing
- Default surge settings might not be optimal for your workload

### 2. **Blue-Green Node Pool Strategy** (Your approach, optimized)
```bash
# 1. Create new pool
gcloud container node-pools create gpu-pool-132 \
    --cluster=CLUSTER_NAME \
    --machine-type=a2-highgpu-8g \
    --accelerator=type=nvidia-tesla-a100,count=8 \
    --node-version=1.32.x \
    --reservation-affinity=specific \
    --reservation=YOUR_RESERVATION_NAME

# 2. Automated draining script instead of manual
for node in $(kubectl get nodes -l cloud.google.com/gke-nodepool=OLD_POOL_NAME -o name); do
    kubectl drain $node --ignore-daemonsets --delete-emptydir-data --force
    sleep 30  # Adjust based on your workload startup time
done
```

## Key Considerations for A100 Workloads

1. **Reservation Compatibility**: Ensure your new node pool can use the same reservations
2. **GPU Driver Compatibility**: Verify NVIDIA driver versions between k8s versions
3. **Workload Startup Time**: A100 workloads often have long initialization times
4. **Storage**: Consider persistent volumes and local SSD migration

## Recommended Approach

Given your constraints (128 A100 nodes, fixed reservations), I'd recommend:

**Option A: In-place upgrade with custom surge settings**
```bash
# Configure surge for gradual rollout
gcloud container node-pools update gpu-pool \
    --max-surge-upgrade=4 \
    --max-unavailable-upgrade=2

# Then upgrade
gcloud container node-pools upgrade gpu-pool \
    --cluster=CLUSTER_NAME \
    --node-version=1.32.x
```

**Option B: If you must use blue-green approach**
- Verify reservation can accommodate 256 nodes temporarily
- Use automated draining scripts
- Consider doing it in batches (e.g., 32 nodes at a time) to reduce capacity requirements

## Questions to Consider
1. Can your reservations handle double capacity temporarily?
2. How long do your GPU workloads take to restart?
3. Do you have stateful workloads that require special handling?
4. What's your tolerance for brief disruptions vs. extended migration windows?

The in-place upgrade is usually the most efficient approach for large GPU clusters, but your manual approach gives you maximum control if you have complex scheduling requirements.
Your proposed approach is actually quite conservative and safe, but there are better options for GPU workloads on GKE, especially with fixed reservations. Let me break down your options:

## Your Current Approach (Safe but Disruptive)
```bash
# 1. Create new node pool
gcloud container node-pools create gpu-pool-v132 \
  --cluster=your-cluster \
  --machine-type=a2-highgpu-1g \
  --accelerator type=nvidia-tesla-a100,count=1 \
  --num-nodes=128 \
  --node-version=1.32

# 2. Cordon old nodes
kubectl cordon -l cloud.google.com/gke-nodepool=old-gpu-pool

# 3. Drain manually (you control the pace)
kubectl drain node-name --ignore-daemonsets --delete-emptydir-data
```

**Pros:** Full control, zero version mixing
**Cons:** Requires manual orchestration, temporary double capacity costs

## Better Approaches

### 1. **Blue-Green with Surge Upgrade (Recommended for GPU)**
```bash
gcloud container node-pools update gpu-pool \
  --cluster=your-cluster \
  --max-surge=32 \
  --max-unavailable=0 \
  --node-version=1.32
```

This creates new nodes before draining old ones, better for GPU workloads.

### 2. **Rolling Update with Custom Surge**
For your 128 A100 setup, consider:
```bash
# Configure surge settings first
gcloud container node-pools update gpu-pool \
  --max-surge=16 \
  --max-unavailable=8

# Then upgrade
gcloud container node-pools upgrade gpu-pool \
  --cluster=your-cluster \
  --node-version=1.32
```

### 3. **Batch Manual Upgrade** (Best for ML workloads)
```bash
# Upgrade in batches of 8-16 nodes
for batch in $(kubectl get nodes -l nodepool=gpu-pool -o name | split -l 16); do
  kubectl drain $batch --ignore-daemonsets --grace-period=300
  # Wait for workloads to reschedule
  sleep 60
done
```

## Key Considerations for GPU Workloads

1. **Reservation Impact**: Check if your fixed reservations work with the new node pool
2. **GPU Driver Compatibility**: Ensure NVIDIA drivers are compatible between versions
3. **Workload Tolerance**: ML training jobs may prefer controlled interruption vs. automatic drainage

## Recommended Approach for Your Setup

Given 128 A100s with fixed reservations, I'd suggest:

```bash
# 1. Test with a small subset first
gcloud container node-pools create gpu-test-v132 \
  --num-nodes=4 \
  --node-version=1.32 \
  # ... other GPU configs

# 2. Validate workloads run correctly

# 3. Use surge upgrade in batches
gcloud container node-pools update gpu-pool \
  --max-surge=16 \
  --max-unavailable=0 \
  --node-version=1.32
```

This gives you the control of manual approach but with GKE handling the orchestration. The key is setting `max-unavailable=0` to ensure new nodes are ready before old ones drain.

Would you like me to help you plan the specific batch sizing based on your workload characteristics?
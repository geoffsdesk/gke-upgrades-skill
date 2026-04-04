Your approach will work, but there are several better alternatives depending on your specific needs. Let me break down the options:

## Better Approaches

### 1. **Blue-Green Node Pool Strategy** (Recommended for GPU workloads)
```bash
# Create new 1.32 node pool
gcloud container node-pools create gpu-pool-v132 \
  --cluster=your-cluster \
  --machine-type=a2-highgpu-1g \
  --accelerator=type=nvidia-tesla-a100,count=1 \
  --num-nodes=128 \
  --node-version=1.32 \
  --reservation-affinity=specific \
  --reservation=your-reservation-name

# Gradually migrate workloads using node selectors/affinity
# Then delete old pool
```

### 2. **In-Place Node Pool Upgrade** (Simplest)
```bash
gcloud container node-pools upgrade gpu-pool \
  --cluster=your-cluster \
  --node-version=1.32
```

### 3. **Surge Upgrade Configuration**
```bash
# Configure surge settings first
gcloud container node-pools update gpu-pool \
  --cluster=your-cluster \
  --max-surge=10 \
  --max-unavailable=5

# Then upgrade
gcloud container node-pools upgrade gpu-pool \
  --cluster=your-cluster \
  --node-version=1.32
```

## Recommended Approach for Your Scenario

Given you have **128 A100 nodes with reservations**, I'd recommend:

### Option A: In-Place Upgrade with Controlled Surge
```bash
# 1. Set conservative surge limits
gcloud container node-pools update your-gpu-pool \
  --cluster=your-cluster \
  --max-surge=5 \
  --max-unavailable=2

# 2. Upgrade the pool
gcloud container node-pools upgrade your-gpu-pool \
  --cluster=your-cluster \
  --node-version=1.32
```

**Pros:**
- Simpler process
- No reservation complications
- Automatic rollout with surge control
- Built-in safety mechanisms

**Cons:**
- Less control over timing
- Potential brief service disruption

### Option B: Blue-Green with Reservation Considerations
If you need maximum control:

```bash
# 1. Check if you can temporarily expand reservation or create new one
# 2. Create new pool
gcloud container node-pools create gpu-pool-v132 \
  --cluster=your-cluster \
  --machine-type=a2-highgpu-1g \
  --accelerator=type=nvidia-tesla-a100,count=1 \
  --num-nodes=128 \
  --node-version=1.32 \
  --reservation-affinity=specific \
  --reservation=your-reservation-name

# 3. Use node affinity to control workload placement
kubectl patch deployment your-gpu-workload -p '
{
  "spec": {
    "template": {
      "spec": {
        "nodeSelector": {
          "cloud.google.com/gke-nodepool": "gpu-pool-v132"
        }
      }
    }
  }
}'

# 4. Delete old pool after migration
gcloud container node-pools delete gpu-pool-v131 --cluster=your-cluster
```

## Key Considerations for GPU Workloads

1. **Reservation Constraints**: Check if your reservation allows temporary expansion
2. **Long-running Jobs**: GPU workloads often run for hours/days
3. **Checkpoint/Resume**: Ensure your workloads can handle restarts gracefully
4. **NVIDIA Driver Compatibility**: Verify driver compatibility between versions

## Pre-upgrade Checklist

```bash
# 1. Check current workload state
kubectl get pods -o wide --field-selector spec.nodeName=<gpu-node-name>

# 2. Verify reservation details
gcloud compute reservations describe your-reservation-name

# 3. Test upgrade on a small subset first (if possible)
gcloud container node-pools create gpu-test-pool \
  --num-nodes=2 \
  --node-version=1.32
```

## My Recommendation

For your scenario, I'd recommend **Option A (in-place upgrade)** because:
- Reservations make blue-green complex and potentially costly
- GKE's surge upgrade is well-tested for GPU nodes
- Less operational overhead
- Built-in rollback capabilities

Start with a small `max-surge` value (5-10 nodes) to test the process, then adjust based on your workload tolerance.

Would you like me to elaborate on any of these approaches or help you plan the specific upgrade steps?
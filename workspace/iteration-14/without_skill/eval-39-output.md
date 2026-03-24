Your proposed approach will work, but there are several better alternatives depending on your specific needs and constraints. Let me break down the options:

## Better Approaches

### 1. **Blue-Green Node Pool Migration** (Recommended for your case)
Given your fixed reservations and critical GPU workloads, this is likely your best option:

```bash
# 1. Create new node pool with 1.32
gcloud container node-pools create gpu-pool-v132 \
  --cluster=your-cluster \
  --machine-type=a2-highgpu-8g \
  --num-nodes=128 \
  --node-version=1.32.x \
  --reservation-affinity=specific \
  --reservation=your-gpu-reservation-new

# 2. Gradually migrate workloads using node selectors/affinity
kubectl patch deployment your-gpu-app -p '{"spec":{"template":{"spec":{"nodeSelector":{"cloud.google.com/gke-nodepool":"gpu-pool-v132"}}}}}'

# 3. Once all workloads moved, delete old pool
gcloud container node-pools delete gpu-pool-v131
```

### 2. **In-Place Node Pool Upgrade** (Simplest if supported)
Check if your node pool supports auto-upgrade:

```bash
# Check current upgrade settings
gcloud container node-pools describe gpu-pool --cluster=your-cluster

# Enable auto-upgrade if not already enabled
gcloud container node-pools update gpu-pool \
  --cluster=your-cluster \
  --enable-autoupgrade

# Or manually trigger upgrade
gcloud container node-pools upgrade gpu-pool \
  --cluster=your-cluster \
  --node-version=1.32.x
```

### 3. **Surge Upgrade Configuration**
If you have spare capacity or can temporarily expand:

```bash
gcloud container node-pools update gpu-pool \
  --cluster=your-cluster \
  --max-surge=10 \
  --max-unavailable=0
```

## Key Considerations for Your Setup

### **Reservation Management**
- **Critical**: Ensure your new reservation covers 1.32-compatible machine types
- You may need to modify or create new reservations
- Coordinate with your GCP account team for reservation changes

### **Workload Disruption**
For GPU workloads (ML training, etc.):
```yaml
# Use PodDisruptionBudgets
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: gpu-workload-pdb
spec:
  maxUnavailable: 10%  # Adjust based on your tolerance
  selector:
    matchLabels:
      workload-type: gpu-training
```

### **Pre-Migration Validation**
```bash
# Test compatibility first with a small subset
gcloud container node-pools create gpu-test-pool \
  --cluster=your-cluster \
  --num-nodes=2 \
  --node-version=1.32.x \
  # ... other configs

# Deploy test workloads to validate GPU drivers, CUDA compatibility, etc.
```

## Recommended Strategy for Your Case

Given 128 A100 nodes with fixed reservations:

1. **Coordinate with GCP** - Ensure reservation compatibility with 1.32
2. **Phased Blue-Green Migration**:
   - Create new pool with 25% capacity (32 nodes)
   - Migrate non-critical workloads first
   - Gradually expand new pool, contract old pool
   - Use node affinity rules to control placement

3. **Monitoring Strategy**:
```bash
# Monitor node readiness during migration
kubectl get nodes -l cloud.google.com/gke-nodepool=gpu-pool-v132 \
  -o custom-columns=NAME:.metadata.name,STATUS:.status.conditions[-1].type,GPU:.status.allocatable.nvidia\.com/gpu
```

## Why Your Original Approach Isn't Optimal

- **Manual drain** of 128 GPU nodes will be time-consuming and error-prone
- **No rollback path** once you start draining
- **Potential for extended downtime** if issues arise
- **Doesn't leverage GKE's built-in upgrade mechanisms**

The blue-green approach gives you better control, easier rollback, and minimizes risk for your high-value GPU infrastructure.
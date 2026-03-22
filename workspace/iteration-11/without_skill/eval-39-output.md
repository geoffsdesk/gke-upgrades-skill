Your approach will work, but there are better alternatives for your specific situation with GPU nodes and fixed reservations. Let me break down the options:

## Your Current Approach (Manual)
**Pros:**
- Full control over timing
- Can handle workloads that don't respond well to automatic eviction

**Cons:**
- Manual and time-consuming for 128 nodes
- Risk of human error
- No automatic workload migration
- Complex coordination with reservations

## Better Approaches

### 1. **Blue/Green Node Pool Strategy** (Recommended for your case)
```bash
# Create new node pool with 1.32
gcloud container node-pools create gpu-pool-v132 \
  --cluster=your-cluster \
  --machine-type=a2-highgpu-1g \
  --num-nodes=128 \
  --node-version=1.32.x \
  --reservation-affinity=specific \
  --reservation=your-reservation-name

# Gradually migrate workloads (use taints/tolerations or node selectors)
# Then delete old pool
gcloud container node-pools delete gpu-pool-v131
```

### 2. **Surge Upgrade** (If you have quota)
```bash
gcloud container node-pools update gpu-pool \
  --max-surge-upgrade=10 \
  --max-unavailable-upgrade=0
```

### 3. **Rolling Update with Node Auto-Provisioning**
If your workloads support it, enable NAP temporarily to handle overflow during the upgrade.

## Specific Considerations for Your Setup

### **GPU Workloads**
- GPU workloads often have long startup times
- Consider checkpoint/restart capabilities
- Plan for model loading time

### **Fixed Reservations**
- Coordinate with your reservation schedule
- You might need temporary additional quota
- Consider reservation splitting if possible

### **Recommended Approach for You**

Given your constraints, I'd suggest a **hybrid approach**:

```bash
# 1. Create new node pool targeting same reservation
gcloud container node-pools create gpu-pool-v132 \
  --cluster=your-cluster \
  --node-version=1.32.x \
  --num-nodes=0 \
  --enable-autoscaling \
  --min-nodes=0 \
  --max-nodes=128 \
  --reservation-affinity=specific \
  --reservation=your-reservation-name

# 2. Add node selector to new workloads
kubectl patch deployment my-gpu-app -p '{"spec":{"template":{"spec":{"nodeSelector":{"cloud.google.com/gke-nodepool":"gpu-pool-v132"}}}}}'

# 3. Scale up new pool gradually
gcloud container node-pools resize gpu-pool-v132 --num-nodes=64

# 4. Use controlled eviction for old nodes
kubectl drain node-name --ignore-daemonsets --delete-emptydir-data --grace-period=300

# 5. Scale down old pool gradually
gcloud container node-pools resize gpu-pool-v131 --num-nodes=64
```

## Additional Recommendations

1. **Test in staging first** with a smaller GPU node pool
2. **Plan maintenance windows** - GPU workload migrations take time
3. **Monitor reservation utilization** during the transition
4. **Use PodDisruptionBudgets** to control eviction rate
5. **Consider workload-specific strategies** (checkpointing, etc.)

The blue/green approach with gradual migration is likely your best bet given the GPU workloads and reservation constraints. Would you like me to elaborate on any of these strategies?
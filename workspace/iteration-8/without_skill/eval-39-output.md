Your proposed approach will work, but there are several better alternatives depending on your specific needs. Let me break down the options:

## Better Approaches

### 1. **Blue-Green Node Pool Upgrade** (Recommended for your case)
Since you have fixed reservations, this is likely your best option:

```bash
# 1. Create new node pool with 1.32
gcloud container node-pools create gpu-pool-v132 \
  --cluster=your-cluster \
  --zone=your-zone \
  --machine-type=a2-highgpu-8g \
  --accelerator=type=nvidia-tesla-a100,count=8 \
  --num-nodes=128 \
  --node-version=1.32.x \
  --reservation-affinity=specific \
  --reservation=your-reservation-name

# 2. Gradually migrate workloads using node selectors/affinity
# 3. Once migration complete, delete old pool
gcloud container node-pools delete gpu-pool-old --cluster=your-cluster
```

**Pros:** Zero downtime, controlled migration, can validate new nodes before switching
**Cons:** Temporarily doubles your node count (cost consideration)

### 2. **Surge Upgrade** (If supported)
Check if your node pool supports surge upgrades:

```bash
# Enable surge upgrade
gcloud container node-pools update gpu-pool \
  --cluster=your-cluster \
  --max-surge=10 \
  --max-unavailable=0

# Then perform rolling upgrade
gcloud container node-pools upgrade gpu-pool \
  --cluster=your-cluster \
  --node-version=1.32.x
```

**Pros:** Automated process, maintains capacity during upgrade
**Cons:** May not work with fixed reservations, requires additional temporary capacity

### 3. **Rolling Update with Custom Strategy**
```bash
# Update node pool in batches
for i in {1..4}; do
  # Cordon subset of nodes
  kubectl get nodes -l your-node-selector | head -32 | \
    xargs kubectl cordon
  
  # Drain them
  kubectl get nodes -l your-node-selector -o name | head -32 | \
    xargs -I {} kubectl drain {} --ignore-daemonsets --delete-emptydir-data
  
  # Upgrade this batch
  gcloud container node-pools upgrade gpu-pool \
    --cluster=your-cluster \
    --node-version=1.32.x
done
```

## Why Your Approach Has Drawbacks

1. **Capacity Loss**: Cordoning all nodes at once means 100% capacity loss
2. **Manual Process**: More error-prone than automated alternatives
3. **Downtime**: Significant service interruption for GPU workloads
4. **Reservation Issues**: May lose your fixed reservation during the transition

## Recommendations for Your Scenario

Given your 128 A100 nodes with fixed reservations:

### Option A: Blue-Green (If budget allows)
- Create new pool with 1.32
- Migrate workloads gradually
- Most controlled approach

### Option B: Batched Rolling Update
- Upgrade in smaller batches (e.g., 25-30 nodes at a time)
- Maintains 75%+ capacity throughout
- Less risky than all-at-once approach

### Option C: Maintenance Window Approach
If you must do it all at once:
```bash
# 1. Schedule maintenance window
# 2. Scale down non-critical workloads
# 3. Cordon all nodes in old pool
kubectl get nodes -l cloud.google.com/gke-nodepool=old-gpu-pool \
  -o name | xargs kubectl cordon

# 4. Drain nodes (use --force if needed for stuck pods)
kubectl get nodes -l cloud.google.com/gke-nodepool=old-gpu-pool \
  -o name | xargs -I {} kubectl drain {} \
  --ignore-daemonsets --delete-emptydir-data --force --grace-period=300

# 5. Delete old pool and create new one
```

## Additional Considerations

1. **GPU Driver Compatibility**: Ensure 1.32 supports your required GPU drivers
2. **Workload Disruption**: Consider which workloads can tolerate restarts
3. **Persistent Storage**: Ensure PVs can reattach to new nodes
4. **Network Policies**: Verify they'll work with new node pool
5. **Monitoring**: Have monitoring in place during the upgrade

The blue-green approach is generally the safest for production GPU workloads, even with the temporary cost increase.
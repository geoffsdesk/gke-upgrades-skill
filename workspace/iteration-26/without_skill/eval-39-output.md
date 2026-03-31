Your proposed approach will work, but there are better options for a cluster with fixed GPU reservations. Here's what I'd recommend:

## Better Approach: In-Place Node Pool Upgrade

For GPU nodes with fixed reservations, **in-place upgrade** is usually preferable:

```bash
# Upgrade the node pool in-place
gcloud container node-pools upgrade NODE_POOL_NAME \
    --cluster=CLUSTER_NAME \
    --zone=ZONE_OR_REGION \
    --max-surge-upgrade=1 \
    --max-unavailable-upgrade=0
```

**Why this is better for your use case:**
- Preserves your GPU reservations (they stay attached to the same zone/project)
- No risk of failing to acquire 128 A100s for the new pool
- Simpler process with built-in safety mechanisms
- Automatic rollback capabilities if issues arise

## If You Must Use Node Pool Replacement

If you have reasons to replace the pool entirely:

### 1. **Create new pool WITHOUT deleting old one first**
```bash
gcloud container node-pools create new-gpu-pool-v132 \
    --cluster=CLUSTER_NAME \
    --machine-type=a2-highgpu-1g \  # or your A100 machine type
    --accelerator=type=nvidia-tesla-a100,count=1 \
    --num-nodes=128 \
    --node-version=1.32.x \
    --reservation-affinity=specific \
    --reservation=YOUR_RESERVATION_NAME
```

### 2. **Gradual migration approach**
```bash
# Cordon old nodes gradually (not all at once)
kubectl cordon NODE_NAME

# Drain with proper GPU considerations
kubectl drain NODE_NAME \
    --ignore-daemonsets \
    --delete-emptydir-data \
    --force \
    --grace-period=300
```

## Key Considerations for A100 Nodes

1. **Reservation Management**: Ensure your reservations cover both pools during transition, or modify reservation to cover new pool

2. **GPU Driver Compatibility**: Verify NVIDIA drivers are compatible with 1.32

3. **Workload-Specific Draining**:
   ```bash
   # For ML workloads, use longer grace periods
   kubectl drain NODE_NAME --grace-period=600 --timeout=900s
   ```

4. **Monitor Resource Availability**:
   ```bash
   # Check A100 availability in your region first
   gcloud compute accelerator-types list --filter="zone:YOUR_ZONE"
   ```

## Recommendation

**Use in-place upgrade** unless you have specific reasons like:
- Changing machine types
- Modifying disk configurations  
- Changing reservation assignments
- Known issues with your current node pool configuration

The gradual in-place upgrade with `max-surge-upgrade=1` will minimize disruption while maintaining your valuable GPU reservations.
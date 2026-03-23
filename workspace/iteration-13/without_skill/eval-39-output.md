For a cluster of this size and importance (128 A100 nodes with fixed reservations), your proposed approach is actually quite sound, but there are some optimizations and alternatives to consider:

## Your Proposed Approach (Recommended with modifications)

**Pros:**
- Maximum control over the process
- No risk of automatic disruption
- Can validate new nodes before migration
- Works well with fixed reservations

**Optimized steps:**
1. Create new 1.32 node pool with same reservations
2. **Gradually** cordon/drain in batches (not all at once)
3. Use `kubectl drain` with appropriate flags:
   ```bash
   kubectl drain <node> --ignore-daemonsets --delete-emptydir-data --grace-period=300
   ```
4. Monitor workload migration between batches
5. Delete old pool only after full validation

## Alternative: Surge Upgrade (if feasible)

If your reservation quota allows temporary doubling:
```bash
gcloud container node-pools update gpu-pool \
  --cluster=your-cluster \
  --zone=your-zone \
  --max-surge=10 \
  --max-unavailable=5
```

Then use standard rolling upgrade, but this requires 2x reservation capacity temporarily.

## Blue/Green at Node Pool Level

Create the new pool, migrate workloads with selectors/taints:
```yaml
nodeSelector:
  cloud.google.com/gke-nodepool: gpu-pool-v132
```

## Key Considerations for A100 Clusters

1. **Batch size**: Drain 5-10 nodes at a time, not all 128
2. **Workload awareness**: Coordinate with ML teams on training job schedules
3. **GPU driver compatibility**: Ensure NVIDIA drivers work with 1.32
4. **Monitoring**: Watch for CUDA/GPU workload issues post-upgrade
5. **Reservation management**: Coordinate with Google Cloud support for reservation transfers

## Recommended Approach

Stick with your manual approach but do it in phases:
- **Week 1**: Create new pool, migrate 20-30 nodes worth of workloads
- **Week 2**: Migrate another batch after validation
- **Continue** until complete

This gives you maximum safety for such a valuable cluster while allowing rollback at any stage.

Would you like me to elaborate on any of these approaches or discuss specific challenges with A100 workload migration?
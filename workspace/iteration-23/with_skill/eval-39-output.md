**No, that's not the optimal approach.** Creating a new node pool manually (custom blue-green) should be a last resort. GKE has native upgrade strategies that are simpler and fully supported.

For your GPU pool with fixed reservations, I recommend **GKE's native surge upgrade with drain-first configuration**:

```bash
# Configure for GPU pools with fixed reservations
gcloud container node-pools update GPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4

# Then upgrade
gcloud container node-pools upgrade GPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

**Why this works better for your scenario:**

1. **No surge capacity needed:** `maxSurge=0` means GKE drains nodes first, then creates replacements using your existing reservation slots. No extra GPUs required.

2. **Controlled parallelism:** `maxUnavailable=4` drains 4 nodes at a time (adjust based on your tolerance for temporary capacity loss). This speeds up the process compared to the default `maxUnavailable=1`.

3. **Automatic management:** GKE handles cordon/drain/delete automatically with proper PDB respect and eviction timeouts.

4. **Built-in safeguards:** Native upgrades respect PDBs, handle admission webhooks properly, and integrate with GKE's retry logic if issues occur.

**For your 128-node pool:** With `maxUnavailable=4` and GKE's ~20-node batch concurrency limit, expect the upgrade to take several hours. You can increase `maxUnavailable` to 8 or higher if your workloads can tolerate more temporary capacity loss.

**Alternative - Autoscaled Blue-Green (if you have headroom in your reservation):**
If your GPU reservation has any unused capacity, consider GKE's autoscaled blue-green upgrade strategy:

```bash
gcloud container node-pools update GPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 128 \
  --total-max-nodes 150 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25
```

This keeps inference workloads serving while new nodes warm up, avoiding the capacity dip of drain-first.

**Before you upgrade:**
1. **Test GPU driver compatibility:** The 1.32 upgrade will change your CUDA driver version. Create a small staging pool at 1.32 first and validate your workloads.
2. **Check reservation headroom:** `gcloud compute reservations describe RESERVATION_NAME --zone ZONE` to confirm available capacity.

Would you like me to create a complete runbook with pre-flight checks and validation steps for your specific environment?
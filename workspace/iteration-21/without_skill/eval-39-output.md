Your proposed approach is **overly conservative** for this situation. Here are better alternatives:

## Recommended Approach: In-Place Node Pool Upgrade

For a Standard GKE cluster, you can upgrade the node pool in-place:

```bash
gcloud container node-pools upgrade NODE_POOL_NAME \
    --cluster=CLUSTER_NAME \
    --zone=ZONE \
    --node-version=1.32.x-gke.xxxx
```

**Why this is better:**
- Preserves your **fixed reservations** (crucial for A100 nodes)
- Automatic rolling upgrade with configurable surge settings
- Built-in safety mechanisms and rollback capabilities
- Less manual intervention required

## Configure Surge Settings for GPU Workloads

Given you have 128 A100 nodes, configure appropriate surge settings:

```bash
gcloud container node-pools update NODE_POOL_NAME \
    --cluster=CLUSTER_NAME \
    --zone=ZONE \
    --max-surge=10 \
    --max-unavailable=5
```

**For GPU workloads, consider:**
- Lower surge/unavailability numbers to manage resource constraints
- GPU workloads often have longer startup times
- A100 reservations are precious - avoid releasing them unnecessarily

## When Your Approach Makes Sense

Your manual approach is warranted if:
- You need **zero disruption** during upgrade
- You have **additional reservations** available for the new pool
- Your workloads cannot tolerate any interruption
- You want maximum control over the migration timing

## Hybrid Approach

If you must use the new pool method:

1. **Verify reservation availability** first
2. Create new pool with `--reservation-affinity`
3. Use `kubectl drain` with appropriate flags:
   ```bash
   kubectl drain NODE_NAME \
     --ignore-daemonsets \
     --delete-emptydir-data \
     --force \
     --grace-period=300
   ```
4. Monitor workload migration carefully

## Key Considerations

- **A100 availability**: These are constrained resources
- **Workload restart time**: ML/AI workloads may take significant time to restart
- **Data locality**: Consider any local storage implications
- **Cost**: Running double capacity temporarily

**Recommendation**: Start with the in-place upgrade approach unless you have specific requirements that necessitate the manual method.
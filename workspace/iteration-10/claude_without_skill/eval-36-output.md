Here are your options to upgrade without additional GPU quota:

## Immediate Solutions

### 1. **Disable Surge Upgrades**
```bash
gcloud container node-pools update [POOL_NAME] \
  --cluster=[CLUSTER_NAME] \
  --zone=[ZONE] \
  --max-surge=0 \
  --max-unavailable=1
```
This forces a rolling upgrade that replaces nodes one-by-one without requiring extra capacity.

### 2. **Manual Node Cordoning/Draining**
- Manually cordon and drain nodes in small batches
- Delete old nodes after workloads migrate
- Let GKE create replacements with new node version

## Alternative Approaches

### 3. **Multi-Zone Strategy** (if applicable)
```bash
# Check available zones for H100s
gcloud compute accelerator-types list --filter="name:nvidia-h100"

# If other zones have capacity, temporarily add them:
gcloud container node-pools update [POOL_NAME] \
  --additional-zones=[ZONE_WITH_CAPACITY]
```

### 4. **Blue/Green Node Pool Migration**
```bash
# Create new pool in different zone with capacity
gcloud container node-pools create [NEW_POOL] \
  --cluster=[CLUSTER_NAME] \
  --zone=[DIFFERENT_ZONE] \
  --accelerator=type=nvidia-h100-80gb,count=8
  
# Migrate workloads, then delete old pool
```

### 5. **Scheduled Maintenance Window**
- Use `--max-unavailable=25%` during low-traffic periods
- Coordinate with Google Cloud support for capacity planning

**Recommended**: Start with option #1 (disable surge) as it requires no additional resources and maintains your current zone placement.
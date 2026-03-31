For GKE Standard clusters on the Regular channel, **GKE handles upgrades automatically**, but you should implement a structured approach to manage them properly for production. Here's what I recommend:

## How GKE Auto-Upgrades Work

**Control Plane:**
- Automatically upgrades during maintenance windows
- You can configure maintenance windows and exclusions
- Updates happen within ~2-3 weeks of version availability on Regular channel

**Node Pools:**
- Auto-upgrade is enabled by default
- Upgrades after control plane is updated
- Respects node pool maintenance windows

## Recommended Production Approach

### 1. **Configure Maintenance Windows**
```bash
# Set maintenance window
gcloud container clusters update CLUSTER_NAME \
    --maintenance-window-start "2023-01-01T09:00:00Z" \
    --maintenance-window-end "2023-01-01T17:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### 2. **Set Up Maintenance Exclusions**
```bash
# Exclude critical business periods
gcloud container clusters update CLUSTER_NAME \
    --add-maintenance-exclusion-name "black-friday" \
    --add-maintenance-exclusion-start "2023-11-20T00:00:00Z" \
    --add-maintenance-exclusion-end "2023-11-27T23:59:59Z"
```

### 3. **Implement a Staged Approach**
- **Dev cluster**: Keep auto-upgrades enabled, no restrictions
- **Staging cluster**: Auto-upgrades with 1-week delay after dev
- **Production clusters**: Auto-upgrades with maintenance windows + exclusions

### 4. **Monitor and Prepare**
```bash
# Check available upgrades
gcloud container clusters describe CLUSTER_NAME \
    --format="value(currentMasterVersion,currentNodeVersion)"

# View upgrade notifications
gcloud container operations list --filter="operationType=upgrade"
```

## Key Benefits of Auto-Upgrades
- **Security**: Automatic security patches
- **Support**: Keeps you within supported versions
- **Features**: Access to latest GKE improvements
- **Reduced overhead**: Less manual management

## When to Consider Manual Control
- **Rapid Release channel**: May want more control due to faster pace
- **Highly regulated environments**: May need extensive testing
- **Complex applications**: Need longer validation periods

## Best Practices
1. **Test in lower environments first**
2. **Use surge upgrades** for faster node updates with minimal disruption
3. **Enable cluster autoscaling** to handle node replacements smoothly
4. **Monitor application health** during upgrade windows
5. **Have rollback procedures** documented

For your production setup, I'd recommend keeping auto-upgrades enabled but with properly configured maintenance windows and exclusions for critical business periods. This gives you the security and support benefits while maintaining control over timing.
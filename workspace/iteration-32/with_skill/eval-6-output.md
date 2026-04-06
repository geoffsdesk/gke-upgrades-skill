# Rapid → Stable Channel Migration Plan

## Critical Implications

### Version Availability Warning ⚠️
**Before migrating, verify that your current version (1.32) is available in Stable channel.** If 1.32 is not yet available in Stable, your cluster will be "ahead of channel" and will NOT receive auto-upgrades until Stable's version catches up to 1.32.

Check current version availability:
```bash
gcloud container get-server-config --zone YOUR_ZONE \
  --format="yaml(channels)" | grep -A 20 "stable"
```

### Key Changes When Moving to Stable

| Aspect | Rapid (current) | Stable (target) | Impact |
|--------|-----------------|-----------------|---------|
| **Upgrade cadence** | Fastest (~2 weeks ahead) | Slowest (2+ weeks behind Regular) | 4-6 week slower security patch delivery |
| **Version validation** | Minimal (early testing) | Extensive (proven in Rapid + Regular) | Higher stability, longer patch lag |
| **SLA coverage** | **No SLA for upgrade stability** | **Full SLA** | Production workload protection |
| **Security patches** | Immediate | Delayed 4-6 weeks | Longer exposure window |

**Key benefit:** The PRIMARY reason to move production from Rapid → Stable is **SLA coverage**. Rapid channel does NOT carry an SLA for upgrade stability — versions may have issues caught before reaching Stable. This is the main production risk, beyond timing alone.

**Key risk:** Slower security patch delivery. Your cluster will receive patches 4-6 weeks later than it does today.

## Migration Steps

### 1. Pre-migration checks
```bash
# Check current channel and version
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name,currentMasterVersion,releaseChannel.channel)"

# Verify 1.32 availability in Stable
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels.stable.validVersions)"

# Check for any active maintenance exclusions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="yaml(maintenancePolicy)"
```

### 2. Apply temporary freeze (recommended)
Add a "no upgrades" exclusion before switching channels to avoid unexpected auto-upgrades immediately after the change:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "channel-migration-freeze" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time $(date -u -d "+7 days" +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-scope no_upgrades
```

### 3. Switch to Stable channel
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel stable
```

### 4. Verify the migration
```bash
# Confirm channel change
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(releaseChannel.channel)"

# Check auto-upgrade target
gcloud container clusters get-upgrade-info CLUSTER_NAME \
  --region REGION
```

### 5. Remove temporary freeze
After verifying the channel change and understanding the new auto-upgrade behavior:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "channel-migration-freeze"
```

## Post-Migration Considerations

### Auto-upgrade Behavior
- If 1.32 is available in Stable: Normal auto-upgrades resume at Stable's cadence
- If 1.32 is NOT available in Stable: No auto-upgrades until Stable reaches 1.32, then normal progression resumes

### Version Drift Risk
Your cluster may fall behind other environments if they remain on faster channels. Consider:
- Keep dev/staging on Regular channel for faster feature access
- Use rollout sequencing to ensure dev upgrades before production (requires same channel)
- OR accept version drift between environments

### Security Patch Timeline
Monitor the [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) to understand when patches arrive in Stable vs your previous Rapid timeline.

## Alternative: Extended Channel for Maximum Control

For production workloads requiring ultimate upgrade control, consider Extended channel instead:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

**Extended channel benefits:**
- Same patch timing as Regular (no 4-6 week delay)
- Up to 24 months support per version
- Manual control over minor version upgrades (no auto-upgrade of minors except at EoS)
- Additional cost only during extended support period (24+ months)

This might better match your production control requirements while maintaining faster security patch delivery.

## Recommendation

Given this is production, I recommend:
1. **Verify 1.32 availability in Stable first** — if not available, wait or consider Extended channel
2. **Use the temporary freeze approach** to control the migration timing
3. **Consider Extended channel** as an alternative that provides maximum control without the 4-6 week security patch delay
4. **Update your maintenance windows** to align with Stable's slower, more predictable upgrade cadence

The key decision is whether the SLA coverage benefit outweighs the 4-6 week security patch delay for your production environment.
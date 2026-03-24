# GKE Release Channel Migration: Rapid → Stable

## Critical Implications

### 1. Version Availability Warning ⚠️
**Your cluster at 1.32 may be "ahead of channel" after switching to Stable.**

- Rapid gets new versions ~4-6 weeks before Stable
- If 1.32 isn't available in Stable yet, your cluster will be frozen at 1.32
- **No auto-upgrades to newer versions** until Stable catches up to 1.32
- You'll still receive patches, but no minor version upgrades

**Check before migrating:**
```bash
# Verify 1.32 availability in Stable channel
gcloud container get-server-config --zone YOUR_ZONE \
  --format="yaml(channels.STABLE.validVersions)"
```

### 2. SLA and Support Changes
- **Rapid channel has NO SLA for upgrade stability** — versions may have issues
- **Stable channel has FULL SLA** — much more reliable for production
- This is the PRIMARY reason to migrate production workloads away from Rapid

### 3. Future Upgrade Cadence
- **Current (Rapid):** New versions within ~2 weeks of upstream Kubernetes
- **Future (Stable):** New versions 4-6 weeks after Rapid validation
- Significantly slower upgrade pace — better for production stability

## Migration Steps

### Step 1: Apply temporary upgrade freeze
```bash
# Prevent auto-upgrades during channel transition
gcloud container clusters update YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --add-maintenance-exclusion-name "channel-migration" \
  --add-maintenance-exclusion-start-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-end-time "$(date -u -d '+7 days' +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-scope no_upgrades
```

### Step 2: Check version compatibility
```bash
# Current cluster version
gcloud container clusters describe YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --format="value(currentMasterVersion)"

# Available versions in Stable
gcloud container get-server-config --zone YOUR_ZONE \
  --format="table(channels.STABLE.validVersions[].version)"
```

### Step 3: Migrate to Stable channel
```bash
gcloud container clusters update YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --release-channel stable
```

### Step 4: Configure production-appropriate maintenance controls
```bash
# Set maintenance window for weekends
gcloud container clusters update YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --maintenance-window-start "2024-12-21T02:00:00Z" \
  --maintenance-window-end "2024-12-21T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Add "no minor or node upgrades" exclusion for maximum production control
# (allows CP security patches, blocks disruptive upgrades)
gcloud container clusters update YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

### Step 5: Remove temporary freeze
```bash
# Remove the migration exclusion
gcloud container clusters update YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --remove-maintenance-exclusion "channel-migration"
```

## Alternative: Extended Channel for Maximum Control

For production workloads requiring the slowest possible upgrade cadence:

```bash
# Extended channel: 24-month support, NO auto-minor upgrades
gcloud container clusters update YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --release-channel extended
```

**Extended channel benefits:**
- Up to 24 months of support per version (extra cost only during extended period)
- Minor upgrades are NOT automated (except at end of extended support)
- Only patches are auto-applied
- Maximum control over when minor upgrades happen

## Post-Migration Validation

```bash
# Confirm channel change
gcloud container clusters describe YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --format="value(releaseChannel.channel)"

# Check auto-upgrade target
gcloud container clusters get-upgrade-info YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE
```

## Recommendations

1. **Use Stable for production** — the SLA difference alone justifies this migration
2. **Keep dev/staging on Regular** — one channel apart maintains version sync
3. **Consider Extended channel** if your team prefers manual minor upgrades
4. **Plan minor upgrades manually** using the "no minor" exclusion + user-triggered upgrades

The migration is safe and reversible, but the version availability check is critical to avoid getting stuck.
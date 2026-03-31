# Channel Migration Plan: Rapid → Stable

## Key Implications

**⚠️ Critical Warning**: Your cluster at 1.32 may be **ahead of the Stable channel**. If 1.32 isn't available in Stable yet, your cluster will be "ahead of channel" and **stop receiving auto-upgrades** until Stable catches up to 1.32.

**Version availability check required**: Before migrating, verify 1.32 is available in Stable:
```bash
gcloud container get-server-config --zone YOUR_ZONE \
  --format="yaml(channels.stable.validVersions)"
```

If 1.32 is NOT in the output, your migration will freeze auto-upgrades until it becomes available.

## Migration Strategy Options

### Option 1: Wait-then-migrate (Recommended)
1. **Wait** for 1.32 to reach Stable channel (~4-6 weeks from Rapid)
2. Check the [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) for 1.32's progression timeline
3. Migrate once 1.32 is available in Stable
4. Resume normal auto-upgrades immediately

### Option 2: Downgrade-then-migrate
1. **Downgrade** to the latest version available in Stable (likely 1.31.x)
2. **Immediately migrate** to Stable channel
3. Resume auto-upgrades from that version

**Downgrade risks**: Control plane minor downgrades require GKE support involvement and may cause API compatibility issues. Node pools can be downgraded more easily.

## Migration Commands

### Step 1: Apply temporary upgrade freeze
```bash
# Prevent unexpected auto-upgrades during transition
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "channel-migration" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+7 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades
```

### Step 2: Migrate to Stable channel
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel stable
```

### Step 3: Remove temporary exclusion
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion "channel-migration"
```

## What Changes After Migration

| Aspect | Rapid (Current) | Stable (Target) |
|--------|----------------|-----------------|
| **Upgrade cadence** | Fastest (new versions ~2 weeks) | Slowest (versions arrive after Regular validation) |
| **Version stability** | No SLA for upgrade stability | Full SLA for upgrade stability |
| **Security patches** | Same timing as Regular/Stable | Same timing as Regular/Stable |
| **Auto-upgrade predictability** | High churn, frequent minor versions | Lower churn, proven versions only |

**Key insight**: The PRIMARY difference is upgrade stability SLA, not just timing. Rapid channel versions may have issues caught before reaching Regular/Stable.

## Recommended Approach for Production

Given you're on **production** infrastructure, I recommend **Option 1 (wait-then-migrate)**:

1. **Check version availability now**: Confirm if 1.32 is in Stable yet
2. **If not available**: Wait 2-4 weeks and check weekly using the release schedule
3. **Configure maintenance controls** while waiting:
   ```bash
   # Set maintenance window to control WHEN upgrades happen
   gcloud container clusters update CLUSTER_NAME \
     --zone ZONE \
     --maintenance-window-start "2025-01-01T02:00:00Z" \
     --maintenance-window-duration 4h \
     --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
   
   # Optional: Add "no minor" exclusion to control WHAT upgrades happen
   gcloud container clusters update CLUSTER_NAME \
     --zone ZONE \
     --add-maintenance-exclusion-scope no_minor_upgrades \
     --add-maintenance-exclusion-until-end-of-support
   ```
4. **Migrate once 1.32 reaches Stable**
5. **Remove any temporary exclusions** to resume auto-upgrades

## Alternative: Extended Channel Consideration

For maximum production control, consider **Extended channel** instead of Stable:
- Up to **24 months** of support (vs 14 months)
- **Manual control** over minor version upgrades
- **Automatic patches** still applied
- Additional cost only during the extended support period (months 15-24)

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

## Validation Commands

```bash
# Confirm channel migration
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(releaseChannel.channel)"

# Check auto-upgrade status
gcloud container clusters get-upgrade-info CLUSTER_NAME \
  --zone ZONE

# Monitor for auto-upgrades resuming
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --limit=5
```

**Next steps**: Check 1.32 availability in Stable, choose your migration timing, and let me know if you need the commands adapted for your specific cluster details.
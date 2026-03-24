# Channel Migration: Rapid → Stable for Production Cluster

## Key Implications

**Version availability warning:** If your current 1.32 version is not yet available in Stable channel, your cluster will be "ahead of channel" after migration. This means:
- You'll receive security patches for 1.32
- You will NOT receive auto-upgrades to newer minor versions (1.33+) until Stable's version catches up to 1.32
- Once Stable reaches 1.32, you'll resume normal auto-upgrades from that point

**Check current version availability:**
```bash
# Verify if 1.32 is available in Stable
gcloud container get-server-config --zone YOUR_ZONE \
  --format="yaml(channels.STABLE.validVersions)" | grep "1.32"
```

## Migration Benefits (Production-Appropriate)

| Aspect | Rapid Channel | Stable Channel |
|--------|---------------|----------------|
| **SLA for upgrade stability** | ❌ **No SLA** - versions may have issues | ✅ **Full SLA** - thoroughly validated |
| **Version arrival timing** | First (~2 weeks after K8s release) | After Regular validation (~6-8 weeks) |
| **Upgrade cadence** | Aggressive - latest features fast | Conservative - stability-first |
| **Production suitability** | Dev/test environments | ✅ **Mission-critical production** |

**Critical insight:** Rapid channel carries NO SLA for upgrade stability. Versions may have issues caught before reaching Stable. This is the primary reason your CTO wants to move production workloads off Rapid.

## Migration Process

### Step 1: Pre-migration checks
```bash
# Current cluster status
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, releaseChannel.channel, nodePools[].version)"

# Check if 1.32 is in Stable yet
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels.STABLE)"
```

### Step 2: Apply maintenance exclusion (recommended)
Before migrating, add a "no minor or node upgrades" exclusion to prevent unexpected auto-upgrades while you validate the new channel behavior:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "channel-migration-hold" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

### Step 3: Migrate to Stable channel
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel stable
```

### Step 4: Verify migration
```bash
# Confirm new channel
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(releaseChannel.channel)"

# Check auto-upgrade target
gcloud container clusters get-upgrade-info CLUSTER_NAME \
  --region REGION
```

## Expected Behavior Post-Migration

**If 1.32 is already in Stable:**
- ✅ Normal auto-upgrade behavior resumes immediately
- You'll get 1.32 patches and eventual 1.33+ upgrades on Stable's timeline

**If 1.32 is NOT yet in Stable:**
- ⏸️ Cluster is "ahead of channel" - frozen at 1.32 for minor upgrades
- ✅ You'll still receive 1.32.x patches
- ⏸️ No minor upgrades (1.33+) until Stable reaches 1.32
- ✅ Once Stable catches up to 1.32, normal auto-upgrades resume

## Timeline Expectations

Based on typical progression:
- **Rapid** (where you are) → **Regular** (~1 month) → **Stable** (~2 months total)
- If you're currently on a recent 1.32 patch in Rapid, expect 4-8 weeks before that version reaches Stable

## Production Recommendations

1. **Keep the maintenance exclusion** until you've validated the new channel behavior and confirmed your target upgrade timing
2. **Monitor the [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule)** to track when your version becomes available in Stable
3. **Plan your next minor upgrade (1.32→1.33) manually** once Stable reaches 1.32, rather than waiting for auto-upgrade
4. **Configure appropriate maintenance windows** for Stable's more predictable but less frequent upgrade cadence

## Maintenance Exclusion Management

Once you're comfortable with Stable channel behavior:
```bash
# Remove the temporary exclusion to resume auto-upgrades
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "channel-migration-hold"
```

Or keep a permanent "no minor upgrades" exclusion if you want to manually control minor version upgrades while allowing patches:
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "channel-migration-hold" \
  --add-maintenance-exclusion-name "manual-minor-upgrades" \
  --add-maintenance-exclusion-scope no_minor_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

This migration aligns your production cluster with industry best practices - Stable channel with controlled upgrade timing is the recommended approach for mission-critical workloads.
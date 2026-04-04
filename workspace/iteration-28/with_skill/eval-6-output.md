# GKE Channel Migration: Rapid → Stable

## ⚠️ Critical Warning: Version Availability Check Required

**Before migrating channels, you must verify that your current version (1.32) is available in the Stable channel.** If 1.32 is not yet available in Stable, your cluster will be "ahead of channel" and will NOT receive auto-upgrades to newer versions until Stable's version reaches 1.32.

Check version availability first:
```bash
gcloud container get-server-config --zone ZONE --format="yaml(channels)"
```

If 1.32 is not available in Stable yet, you have two options:
1. **Wait** until 1.32 reaches Stable (typically 4-6 weeks after Rapid)
2. **Downgrade first** to a version available in both channels, then migrate

## Migration Implications

### Upgrade Cadence Changes
- **Current (Rapid):** New versions within ~2 weeks of upstream K8s release
- **Future (Stable):** New versions after full validation in Regular channel (~6-8 weeks behind Rapid)
- **No SLA impact:** Both channels carry full SLA for upgrade stability

### Security Patch Timing
- Patches will arrive ~2-4 weeks later than on Rapid
- Critical security fixes may have delayed availability
- Consider if this aligns with your security compliance requirements

### Version Progression Timeline
Typical patch progression: Rapid (+0 weeks) → Regular (+2 weeks) → Stable (+4 weeks)

### Frozen State Risk
If you migrate while "ahead of channel," your cluster will be frozen at 1.32 until Stable catches up. During this period:
- ✅ Security patches will still arrive
- ❌ Minor version upgrades will be blocked
- ❌ You'll accumulate version debt vs. the ecosystem

## Safe Migration Plan

### Step 1: Pre-Migration Check
```bash
# Verify current cluster version
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion,releaseChannel.channel)"

# Check Stable channel version availability
gcloud container get-server-config --zone ZONE \
  --format="table(channels.STABLE.validVersions)"
```

### Step 2: Apply Temporary Protection
```bash
# Add "no upgrades" exclusion to prevent auto-upgrades during transition
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "channel-migration" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+7 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades
```

### Step 3: Migrate Channel
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel stable
```

### Step 4: Verify Migration
```bash
# Confirm channel change
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(releaseChannel.channel)"

# Check auto-upgrade target
gcloud container clusters get-upgrade-info CLUSTER_NAME \
  --zone ZONE
```

### Step 5: Remove Temporary Exclusion
```bash
# Remove the exclusion once you've verified stable behavior
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "channel-migration"
```

## Alternative Recommendation: Consider Regular Channel

For most production workloads, **Regular channel** provides the optimal balance:
- ✅ Faster security patches than Stable (~2 weeks vs ~4 weeks behind Rapid)
- ✅ Still has full validation and SLA coverage
- ✅ Balances stability with security posture
- ✅ Most common choice for production environments

## Post-Migration Monitoring

Monitor these for the first 2-4 weeks:
```bash
# Check cluster notifications for upgrade events
gcloud logging read 'resource.type="gke_cluster" AND protoPayload.resourceName:"clusters/CLUSTER_NAME"' --limit=10

# Monitor auto-upgrade status weekly
gcloud container clusters get-upgrade-info CLUSTER_NAME --zone ZONE
```

## Timeline Expectations

If 1.32 is available in Stable now, expect:
- **Immediate:** Channel migration completes
- **2-4 weeks:** First auto-upgrade on Stable cadence
- **Ongoing:** ~4-6 week delay vs. Rapid for new features

The CTO's request makes sense for maximum stability, but ensure your security team accepts the patch delay trade-off. Regular channel might better balance both concerns.
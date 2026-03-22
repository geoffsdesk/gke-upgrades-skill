# Channel Migration Plan: Rapid → Stable

## Migration Impact Analysis

### Immediate Effects
- **Version availability changes**: Stable channel typically lags Rapid by 4-6 weeks. Your cluster will only receive versions that have been validated through Rapid → Regular → Stable promotion.
- **Auto-upgrade timing shifts**: Future upgrades will arrive later but with higher stability confidence and full SLA coverage.
- **Current version (1.32) status**: Need to verify if 1.32 is available in Stable channel yet.

### Key Implications

**Positive:**
- ✅ Full SLA coverage for upgrade stability (Rapid channel has no SLA for upgrade stability)
- ✅ Versions are more battle-tested before reaching your cluster
- ✅ Reduced risk of encountering issues caught during Rapid/Regular validation
- ✅ Better alignment with production stability requirements

**Considerations:**
- ⚠️ Slower access to new Kubernetes features and security patches
- ⚠️ If 1.32 isn't in Stable yet, you may need to downgrade or wait
- ⚠️ Future upgrades will be less frequent but in larger version jumps

## Pre-Migration Checklist

```markdown
## Channel Migration Readiness
- [ ] Verify 1.32 availability in Stable channel
- [ ] Check if any critical security patches are Rapid-only
- [ ] Confirm team accepts slower patch/feature delivery
- [ ] Review maintenance windows (may need adjustment for different cadence)
- [ ] Document current auto-upgrade exclusions (they'll carry forward)
- [ ] Backup cluster configuration
```

## Migration Runbook

### Step 1: Check Version Compatibility

```bash
# Check current cluster state
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="table(name, currentMasterVersion, releaseChannel.channel)"

# Check what's available in Stable channel
gcloud container get-server-config --region REGION \
  --format="yaml(channels.STABLE)"

# Check your cluster's current auto-upgrade target
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION
```

### Step 2: Migration Command

```bash
# Migrate to Stable channel
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --release-channel stable
```

### Step 3: Post-Migration Validation

```bash
# Verify channel change
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="value(releaseChannel.channel)"

# Check new auto-upgrade target
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Verify maintenance settings carried forward
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="yaml(maintenancePolicy)"
```

## Potential Scenarios & Handling

### Scenario A: 1.32 Available in Stable
- ✅ **Outcome**: Clean migration, no version change
- **Action**: Execute migration command, validate settings

### Scenario B: 1.32 Not Yet in Stable
- ⚠️ **Outcome**: Cluster may be auto-downgraded to latest Stable version (e.g., 1.31.x)
- **Action**: 
  1. Apply temporary "no upgrades" maintenance exclusion before migration
  2. Execute channel change
  3. Monitor for forced downgrade notifications
  4. Plan controlled downgrade during maintenance window if needed

### Scenario C: Critical Security Gap
- ⚠️ **Outcome**: Moving to Stable may delay critical patches
- **Action**: Consider Regular channel as middle ground, or time migration after critical patches reach Stable

## Recommended Approach

```bash
# 1. Add temporary protection (optional, if 1.32 not in Stable)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "channel-migration" \
  --add-maintenance-exclusion-start-time "$(date -Iseconds)" \
  --add-maintenance-exclusion-end-time "$(date -d '+7 days' -Iseconds)" \
  --add-maintenance-exclusion-scope no_upgrades

# 2. Execute migration
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --release-channel stable

# 3. Remove temporary exclusion after validation
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --remove-maintenance-exclusion "channel-migration"
```

## Alternative: Consider Regular Channel

Given you're coming from Rapid, **Regular channel** might be a better intermediate step:
- Still provides full SLA (unlike Rapid)
- Faster patch delivery than Stable
- Good balance of stability and timeliness for production workloads

```bash
# Alternative: Migrate to Regular instead
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --release-channel regular
```

## Post-Migration Monitoring

- Monitor Cloud Logging for any forced upgrade notifications
- Review the [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) to understand your new upgrade timeline
- Consider enabling scheduled upgrade notifications (72h advance notice) for better planning

**Timeline**: Channel migration is immediate (~1-2 minutes). The behavioral changes (different upgrade cadence) take effect for future upgrades.

Would you like me to help you check the current version availability in Stable channel, or do you want to explore the Regular channel option first?
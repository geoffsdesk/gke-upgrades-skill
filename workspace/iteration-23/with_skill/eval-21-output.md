# Extended Release Channel Migration Plan

## Extended Channel Overview & Tradeoffs

### Benefits of Extended Channel
- **24-month support period** (vs 14 months on Regular/Stable) - provides additional time for upgrades
- **Manual control over minor version upgrades** - Extended does NOT auto-upgrade minor versions (except at end of extended support)
- **Automatic patch upgrades only** - you get security patches but control when minor version changes happen
- **Full SLA coverage** during both standard (14mo) and extended support periods
- **Ideal for compliance environments** requiring predictable change control

### Key Tradeoffs & Considerations

**Cost:**
- **Additional cost applies ONLY during the extended support period (months 15-24)**
- **No extra cost during standard support** (first 14 months) - same pricing as Regular/Stable
- Extended support pricing varies by region - check current GKE pricing page

**Operational Changes:**
- **Manual minor upgrades required** - you must plan and execute minor version upgrades proactively
- **Risk of falling behind** - without proactive planning, clusters accumulate version debt
- **Internal processes needed** - teams need upgrade planning, testing, and execution processes

**Technical Constraints:**
- Still subject to **End of Extended Support enforcement** - clusters are force-upgraded when extended support expires
- **Node pools follow cluster minor version** - maintain version alignment
- **Same 2-minor-version skew limits** apply between control plane and nodes

## Migration Assessment

Your current state:
- Regular channel at 1.31
- Version 1.31 is available in Extended channel ✅
- Migration is safe - no version compatibility issues

## Migration Steps

### 1. Pre-Migration Preparation

```bash
# Verify current cluster state
gcloud container clusters describe CLUSTER_NAME --region REGION \
  --format="table(name, currentMasterVersion, releaseChannel.channel, nodePools[].name, nodePools[].version)"

# Check Extended channel availability for 1.31
gcloud container get-server-config --region REGION \
  --format="yaml(channels)" | grep -A 10 "EXTENDED"

# Apply temporary "no upgrades" exclusion before channel switch
gcloud container clusters update CLUSTER_NAME --region REGION \
  --add-maintenance-exclusion-name "channel-migration" \
  --add-maintenance-exclusion-start-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-end-time "$(date -u -d '+7 days' +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-scope no_upgrades
```

### 2. Channel Migration

```bash
# Migrate to Extended channel
gcloud container clusters update CLUSTER_NAME --region REGION \
  --release-channel extended

# Verify migration
gcloud container clusters describe CLUSTER_NAME --region REGION \
  --format="value(releaseChannel.channel)"
```

### 3. Configure Extended Channel Controls

```bash
# Remove temporary exclusion and add persistent "no minor upgrades" control
gcloud container clusters update CLUSTER_NAME --region REGION \
  --remove-maintenance-exclusion-name "channel-migration"

# Optional: Add persistent exclusion for maximum control
gcloud container clusters update CLUSTER_NAME --region REGION \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Configure maintenance window for patches
gcloud container clusters update CLUSTER_NAME --region REGION \
  --maintenance-window-start "2024-12-01T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### 4. Verification

```bash
# Confirm Extended channel and auto-upgrade behavior
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Check maintenance exclusions
gcloud container clusters describe CLUSTER_NAME --region REGION \
  --format="yaml(maintenancePolicy)"
```

## Recommended Extended Channel Configuration

For maximum control while maintaining security posture:

```bash
gcloud container clusters update CLUSTER_NAME --region REGION \
  --release-channel extended \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support \
  --maintenance-window-start "2024-12-01T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA" \
  --maintenance-patch-version-disruption-interval 2592000s
```

This provides:
- **Automatic security patches** within Saturday 2-6 AM maintenance windows
- **No automatic minor or node upgrades** - you control when these happen
- **30-day minimum gap** between patch upgrades
- **24-month support** with manual minor upgrade control

## Post-Migration Operations

### Planning Minor Upgrades
Since Extended channel doesn't auto-upgrade minor versions, establish a process:

```bash
# Check when new minor versions become available
gcloud container get-server-config --region REGION \
  --format="yaml(channels.EXTENDED)"

# Plan manual minor upgrade (example: 1.31 → 1.32)
# 1. Test in staging/dev cluster first
# 2. Schedule maintenance window
# 3. Execute upgrade manually:
gcloud container clusters upgrade CLUSTER_NAME --region REGION \
  --cluster-version 1.32.X-gke.Y
```

### Monitoring Extended Support Timeline

```bash
# Check End of Extended Support date
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION \
  --format="value(endOfExtendedSupportTimestamp)"

# Set up alerting 3-6 months before extended support expires
```

## Migration Timeline & Rollback

**Migration duration:** Immediate - channel change takes effect within minutes
**Rollback window:** Can migrate back to Regular/Stable channel anytime, but:
- If you're ahead of the target channel's available versions, you'll be "ahead of channel" until versions catch up
- Auto-upgrade behavior resumes immediately upon switching back

## Recommended Process

1. **Week 1:** Migrate one non-critical production cluster to Extended, validate behavior
2. **Week 2-3:** Develop internal minor upgrade processes and test in staging
3. **Week 4+:** Migrate remaining production clusters
4. **Ongoing:** Execute manual minor upgrades quarterly or as needed

This migration gives you the control you're looking for while maintaining security through automatic patches. The key is establishing proactive minor upgrade planning to avoid accumulating version debt.
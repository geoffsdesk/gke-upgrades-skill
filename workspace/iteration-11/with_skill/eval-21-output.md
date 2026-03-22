# Extended Channel Migration Plan

## Extended Channel Tradeoffs

### Benefits
- **Extended support period**: Up to 24 months vs 14 months standard support
- **Maximum control over EoS enforcement**: Extended delays EoS enforcement until end of extended support (vs immediate at 14 months)
- **Same SLA as Regular/Stable**: Full production SLA unlike Rapid channel
- **Ideal migration path from "No channel"**: Preserves manual upgrade workflows while adding modern features

### Key Tradeoffs & Considerations

**1. Additional cost during extended period**
- Extended channel is **free during the standard 14-month support period**
- Extra charges apply **only during months 15-24** (the extended period)
- Cost is per-node, calculated during extended support usage

**2. Manual minor version upgrades required**
- **Critical difference**: Minor version upgrades on Extended are NOT automated (except at end of extended support)
- Only patches are auto-applied during standard + extended periods  
- Your team must plan and initiate minor upgrades proactively using maintenance windows
- This requires internal processes to schedule minor upgrades before Extended support expires

**3. Version availability timing**
- Extended gets the same versions as Regular channel, same timing
- Not slower to receive new versions (unlike Stable which waits for additional validation)
- The "Extended" aspect refers to support duration, not version arrival

**4. Operational complexity**
- Need processes to track when versions approach end-of-extended-support
- Must plan minor upgrades manually vs relying on auto-upgrade
- Teams comfortable with manual upgrade workflows will adapt easily

## Migration Steps

### Pre-Migration Assessment
```bash
# Check current cluster state
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="table(name, currentMasterVersion, releaseChannel.channel, nodePools[].name, nodePools[].version)"

# Verify 1.31 is available on Extended (it is - Extended supports 1.27+)
gcloud container get-server-config --region REGION \
  --format="yaml(channels.EXTENDED)"
```

### Migration Process

**Step 1: Add temporary "no upgrades" exclusion (safety)**
```bash
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "channel-migration-safety" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time $(date -u -d "+7 days" +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-scope no_upgrades
```

**Step 2: Migrate to Extended channel**
```bash
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --release-channel extended
```

**Step 3: Configure ongoing maintenance policy**
```bash
# Add "no minor or node upgrades" exclusion for maximum control
# This allows control plane patches but blocks minor + node upgrades
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "extended-channel-control" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Set maintenance windows for when you DO want upgrades
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-window-start "2024-12-15T02:00:00Z" \
  --maintenance-window-end "2024-12-15T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"
```

**Step 4: Remove temporary safety exclusion**
```bash
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --remove-maintenance-exclusion-name "channel-migration-safety"
```

## Operational Process for Extended Channel

Since Extended channel requires manual minor version planning:

### 1. Version Monitoring
```bash
# Check auto-upgrade status and EoS timeline
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Monitor Extended channel version availability  
gcloud container get-server-config --region REGION --format="yaml(channels.EXTENDED)"
```

### 2. Minor Upgrade Planning Workflow
- **Quarterly review**: Check version EoS timeline vs current version
- **Staging first**: Test new minor versions in dev/staging Extended clusters  
- **Manual initiation**: Remove exclusions temporarily during planned maintenance windows
- **Re-enable exclusions**: After upgrade, re-apply "no minor or node upgrades" exclusion

### 3. Example Minor Upgrade Process
```bash
# When ready to upgrade from 1.31 → 1.32
# 1. Remove exclusion temporarily
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --remove-maintenance-exclusion-name "extended-channel-control"

# 2. The cluster will auto-upgrade during next maintenance window
# OR initiate manually for immediate control:
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version "1.32.x-gke.xxx"

# 3. After upgrade, re-enable control
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "extended-channel-control" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## Validation

**Post-migration verification:**
```bash
# Confirm channel migration
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="value(releaseChannel.channel)"
# Should show: EXTENDED

# Verify exclusions are active
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="yaml(maintenancePolicy)"

# Check auto-upgrade target (should respect your exclusions)
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION
```

## Recommendation

Extended channel is an excellent fit for your production clusters given:
- You're already manually managing upgrades (moving from Regular)
- 24-month support aligns with enterprise planning cycles  
- You get the same versions as Regular but with extended lifecycle flexibility
- Manual minor upgrade requirement matches production change control processes

The operational overhead (manual minor upgrades) is manageable and gives you maximum control over when disruptive changes occur. Extended channel is particularly well-suited for teams that prefer deliberate, scheduled maintenance over automated upgrades.
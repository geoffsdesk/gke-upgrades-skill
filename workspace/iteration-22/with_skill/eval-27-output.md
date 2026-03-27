# GKE Upgrade Configuration for Financial Services - Maximum Control with Security

For financial services requiring maximum upgrade control while maintaining security posture, here's the recommended configuration:

## Recommended Configuration: Extended Channel + Persistent Exclusions

```bash
gcloud container clusters update CLUSTER_NAME \
    --release-channel extended \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support \
    --maintenance-patch-version-disruption-interval=7776000s \
    --maintenance-window-start "2026-01-01T02:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## Why This Configuration for Financial Services

**Extended Release Channel Benefits:**
- **24-month support** instead of standard 14 months (extra cost only during extended period)
- **No automatic minor version upgrades** (except at end of extended support)
- **Patches still auto-apply** for security compliance
- **Full SLA coverage** unlike Rapid channel
- **Maximum flexibility** around End of Support enforcement

**"No minor or node upgrades" Exclusion:**
- **Allows control plane security patches** to flow automatically
- **Blocks disruptive minor version and node upgrades**
- **Persistent tracking** - automatically renews when new minor versions are adopted
- **No 30-day limit** like "no upgrades" exclusions
- **Prevents version skew** between control plane and nodes

**90-Day Patch Disruption Interval:**
- **Limits control plane patches** to once every 90 days maximum
- **Ideal for quarterly change windows** common in financial services
- **Still maintains security posture** with automatic patches
- **Configurable down to your specific requirements** (30d, 45d, 60d, etc.)

**Saturday 2-6 AM Maintenance Window:**
- **Predictable timing** during off-peak hours
- **4-hour window** adequate for control plane patches
- **Weekend scheduling** minimizes business impact

## How This Works in Practice

### Automatic (No Action Required)
- **Security patches** applied to control plane during Saturday windows (max once per 90 days)
- **Extended support** keeps versions supported up to 24 months
- **Compliance maintained** through automatic security updates

### Manual (Your Control)
- **Minor version upgrades** - you trigger when ready during change windows
- **Node pool upgrades** - you control timing and strategy
- **Emergency patches** - bypass all controls if needed

### Manual Upgrade Commands (When Ready)

```bash
# Minor version upgrade (control plane first)
gcloud container clusters upgrade CLUSTER_NAME \
    --zone ZONE \
    --master \
    --cluster-version TARGET_MINOR_VERSION

# Node pool upgrade (after CP upgrade)
gcloud container node-pools upgrade NODE_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version TARGET_MINOR_VERSION
```

## Alternative Configurations by Risk Tolerance

### Ultra-Conservative (FedRAMP/High Security)
```bash
# Even slower patches - quarterly only
--maintenance-patch-version-disruption-interval=7776000s  # 90 days
--add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

### Moderate Control (Most Financial Services)
```bash
# Monthly patches, quarterly minor upgrades
--maintenance-patch-version-disruption-interval=2592000s  # 30 days
--add-maintenance-exclusion-scope no_minor_upgrades  # Allows node upgrades
```

### Faster Security Response
```bash
# Weekly patches, controlled minor upgrades
--maintenance-patch-version-disruption-interval=604800s  # 7 days
--add-maintenance-exclusion-scope no_minor_upgrades
```

## Multi-Environment Strategy

```bash
# Development: Regular channel, faster patches
gcloud container clusters update DEV_CLUSTER \
    --release-channel regular \
    --maintenance-patch-version-disruption-interval=604800s

# Staging: Regular channel, same as prod timing
gcloud container clusters update STAGING_CLUSTER \
    --release-channel regular \
    --add-maintenance-exclusion-scope no_minor_upgrades \
    --maintenance-patch-version-disruption-interval=2592000s

# Production: Extended channel, maximum control
gcloud container clusters update PROD_CLUSTER \
    --release-channel extended \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support \
    --maintenance-patch-version-disruption-interval=7776000s
```

## Key Advantages Over Alternatives

**vs. "No Channel" (Legacy):**
- ✅ Extended support available
- ✅ Better exclusion controls
- ✅ Persistent exclusions that track EoS
- ✅ Rollout sequencing support

**vs. Regular/Stable + Manual Freezing:**
- ✅ No 6-month exclusion limits to manage
- ✅ Automatic security patches still flow
- ✅ Extended 24-month support timeline
- ✅ No risk of hitting exclusion quotas (3 max per cluster)

**vs. Complete Manual Control:**
- ✅ Security patches automated
- ✅ No risk of falling behind on CVEs
- ✅ Compliance audit trail maintained
- ✅ Reduced operational overhead

## Monitoring and Notifications

```bash
# Enable 72-hour advance notifications
gcloud container clusters update CLUSTER_NAME \
    --send-scheduled-upgrade-notifications

# Monitor via Cloud Logging
gcloud logging read 'resource.type="gke_cluster" 
    jsonPayload.notification_type="SCHEDULED_UPGRADE"' \
    --project PROJECT_ID
```

## Compliance Benefits

- **Audit trail** - all upgrades logged with timestamps
- **Security compliance** - patches applied within 90 days
- **Change management** - manual control over disruptive changes  
- **Risk mitigation** - predictable weekend windows only
- **Version stability** - up to 24 months on same minor version

This configuration gives you **maximum control** over disruptive upgrades while **maintaining security posture** through automatic patches - the ideal balance for regulated financial services environments.
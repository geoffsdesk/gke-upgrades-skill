I'll help you configure maintenance controls for your regulated financial services environment. For SOX compliance with quarterly freezes and annual audits, you'll want the **Extended release channel** combined with restrictive maintenance exclusions and weekend-only windows.

## Recommended Configuration for Regulated Environment

For maximum upgrade control while maintaining security posture:
- **Extended release channel**: Up to 24 months support, no automatic minor version upgrades
- **"No minor or node upgrades" exclusion**: Allows security patches on control plane but blocks disruptive changes
- **Weekend maintenance windows**: Saturday 2-6 AM for predictability
- **90-day patch interval**: Limits control plane disruption frequency

## Configuration Commands

Run these for each of your 3 clusters:

```bash
# Configure Extended channel + restrictive maintenance controls
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --release-channel extended \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support \
    --maintenance-patch-version-disruption-interval=7776000s \
    --maintenance-window-start "2024-01-06T07:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Key parameters explained:**
- `extended`: 24-month support, you control when minor upgrades happen
- `no_minor_or_node_upgrades`: Only security patches auto-apply to control plane
- `until-end-of-support`: Exclusion automatically renews with version changes
- `7776000s`: 90-day minimum gap between patches (maximum allowed)
- Saturday 7-11 AM UTC: Adjust timezone as needed

## Quarterly Code Freeze Management

For quarterly freezes, layer temporary "no upgrades" exclusions:

```bash
# Q4 freeze example (blocks ALL upgrades including patches)
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "q4-code-freeze" \
    --add-maintenance-exclusion-start "2024-10-01T00:00:00Z" \
    --add-maintenance-exclusion-end "2024-12-31T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades

# November audit freeze (if separate from Q4)
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "annual-audit" \
    --add-maintenance-exclusion-start "2024-11-01T00:00:00Z" \
    --add-maintenance-exclusion-end "2024-11-30T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
```

**Important limits:**
- Each "no upgrades" exclusion: 30 days maximum
- Total exclusions per cluster: 3 maximum
- Must leave 48 hours available per 32-day window for maintenance

For longer freezes, chain multiple exclusions but be aware this accumulates security debt.

## Cluster Notification Setup

Enable advance notifications for upgrade planning:

```bash
# Enable 72-hour scheduled upgrade notifications
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --enable-scheduled-upgrades

# Set up Pub/Sub for cluster notifications
gcloud pubsub topics create gke-cluster-notifications
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --enable-notification-config \
    --notification-config-pubsub-topic projects/PROJECT_ID/topics/gke-cluster-notifications
```

## Manual Minor Version Control Process

With Extended channel + exclusions, minor version upgrades require manual approval:

1. **Monitor for new versions** via GKE release schedule
2. **Test in staging** when new minor becomes available
3. **Plan upgrade window** during scheduled maintenance
4. **Execute manually** when ready:
   ```bash
   gcloud container clusters upgrade CLUSTER_NAME \
       --zone ZONE \
       --master \
       --cluster-version TARGET_VERSION
   ```

## Compliance Benefits of This Setup

✅ **SOX Requirements:**
- Predictable change windows (Saturday mornings only)
- Change control via manual minor upgrades
- Audit trail via Cloud Logging and Pub/Sub notifications
- 90-day patch intervals for stability

✅ **Security Posture:**
- Control plane security patches still auto-apply
- Extended support prevents forced EoS upgrades
- Up to 24 months per version reduces upgrade frequency

✅ **Operational Control:**
- You decide when disruptive changes happen
- Quarterly freezes block all upgrades
- Advance notifications for planning

## Verification Commands

Check your configuration:

```bash
# Verify channel and exclusions
gcloud container clusters describe CLUSTER_NAME \
    --zone ZONE \
    --format="yaml(releaseChannel,maintenancePolicy)"

# Check auto-upgrade status
gcloud container clusters get-upgrade-info CLUSTER_NAME \
    --zone ZONE
```

**Warning about version drift:** Extended exclusion periods can cause clusters to fall behind on patches. Plan catch-up windows between quarterly freezes to maintain security posture.

Would you like me to adjust the maintenance window timing for your specific timezone, or help you set up monitoring for the cluster notifications?
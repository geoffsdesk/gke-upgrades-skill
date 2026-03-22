# GKE Maintenance Configuration for SOX Compliance

I'll help you configure maintenance windows and exclusions for your regulated financial services environment. This setup will ensure auto-upgrades only occur during approved windows while respecting your compliance requirements.

## Configuration Strategy

For SOX compliance, I recommend:
- **Weekend-only maintenance windows** for auto-upgrades
- **"No minor or node upgrades" exclusions** during normal operations (allows security patches on control plane)
- **"No upgrades" exclusions** for code freezes and audit periods
- **Regular release channel** for production predictability

## 1. Weekend Maintenance Windows

Configure recurring weekend maintenance windows for all clusters:

```bash
# Cluster 1
gcloud container clusters update CLUSTER_1_NAME \
  --zone ZONE_1 \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-end "2024-01-06T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Cluster 2  
gcloud container clusters update CLUSTER_2_NAME \
  --zone ZONE_2 \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-end "2024-01-06T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Cluster 3
gcloud container clusters update CLUSTER_3_NAME \
  --zone ZONE_3 \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-end "2024-01-06T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Note:** Adjust the start time (currently 2 AM UTC Saturday) to match your preferred weekend maintenance window.

## 2. Baseline "No Minor or Node Upgrades" Exclusions

For maximum control while maintaining security compliance, apply persistent exclusions that allow control plane security patches but block disruptive changes:

```bash
# Cluster 1 - Persistent exclusion until End of Support
gcloud container clusters update CLUSTER_1_NAME \
  --zone ZONE_1 \
  --add-maintenance-exclusion-name "sox-compliance-baseline" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Cluster 2
gcloud container clusters update CLUSTER_2_NAME \
  --zone ZONE_2 \
  --add-maintenance-exclusion-name "sox-compliance-baseline" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Cluster 3
gcloud container clusters update CLUSTER_3_NAME \
  --zone ZONE_3 \
  --add-maintenance-exclusion-name "sox-compliance-baseline" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## 3. Quarterly Code Freeze Exclusions

For Q1 2024 code freeze (example - adjust dates for your schedule):

```bash
# All clusters - Q1 2024 code freeze (blocks ALL upgrades including patches)
for CLUSTER in CLUSTER_1_NAME CLUSTER_2_NAME CLUSTER_3_NAME; do
  gcloud container clusters update $CLUSTER \
    --zone CORRESPONDING_ZONE \
    --add-maintenance-exclusion-name "q1-2024-code-freeze" \
    --add-maintenance-exclusion-start-time "2024-03-15T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-04-05T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
done
```

Repeat for each quarter, adjusting dates as needed.

## 4. Annual November Audit Exclusion

```bash
# All clusters - November 2024 audit period
for CLUSTER in CLUSTER_1_NAME CLUSTER_2_NAME CLUSTER_3_NAME; do
  gcloud container clusters update $CLUSTER \
    --zone CORRESPONDING_ZONE \
    --add-maintenance-exclusion-name "november-2024-audit" \
    --add-maintenance-exclusion-start-time "2024-11-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-11-30T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
done
```

## 5. Release Channel Configuration

Ensure all production clusters use Regular channel for predictability:

```bash
# Verify current channels
gcloud container clusters describe CLUSTER_1_NAME --zone ZONE_1 --format="value(releaseChannel.channel)"
gcloud container clusters describe CLUSTER_2_NAME --zone ZONE_2 --format="value(releaseChannel.channel)"
gcloud container clusters describe CLUSTER_3_NAME --zone ZONE_3 --format="value(releaseChannel.channel)"

# Migrate to Regular channel if needed
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular
```

## SOX Compliance Benefits

This configuration provides:

✅ **Change Control**: All disruptive upgrades blocked by default, requiring explicit approval
✅ **Security Patching**: Control plane security patches still applied automatically
✅ **Audit Trail**: All maintenance activities logged in Cloud Audit Logs
✅ **Predictable Windows**: Upgrades only during pre-approved weekend maintenance windows
✅ **Code Freeze Respect**: Complete upgrade blocks during sensitive periods
✅ **Documentation**: Clear maintenance exclusion names for audit purposes

## Operational Procedures

### Planned Upgrade Process
1. **Assessment**: Review pending upgrades during monthly change control meetings
2. **Testing**: Validate upgrades in non-production environments first
3. **Approval**: Get change control approval for production upgrades
4. **Remove Exclusion**: Temporarily remove the baseline exclusion for approved maintenance windows
5. **Execute**: Allow auto-upgrade during the next weekend window, or trigger manually
6. **Restore**: Re-apply baseline exclusion after upgrade completes

### Emergency Security Patches
For critical security patches requiring immediate deployment:
```bash
# Temporarily allow patches only (still blocks minor/node upgrades)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "sox-compliance-baseline"

# Trigger immediate control plane patch
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master

# Restore baseline exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "sox-compliance-baseline-restored" \
  --add-maintenance-exclusion-start-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## Monitoring and Alerts

Set up Cloud Monitoring alerts for:
- Maintenance exclusion expiration (30 days before)
- Version approaching End of Support
- Failed upgrade operations
- Cluster version drift between environments

This configuration ensures your GKE clusters remain secure through automated patching while maintaining the strict change control required for SOX compliance.
# GKE Maintenance Configuration for Regulated Environment

Based on your SOX compliance and financial services requirements, I'll configure a comprehensive maintenance strategy that provides maximum control while maintaining security posture.

## Recommended Configuration Strategy

For regulated environments like yours, I recommend:
- **Extended release channel** (24-month support, manual minor upgrade control)
- **"No minor or node upgrades" persistent exclusion** (allows security patches, blocks disruptive changes)
- **Weekend maintenance windows** (Saturday early morning)
- **90-day patch disruption interval** (quarterly patch cadence)
- **Quarterly "no upgrades" exclusions** for code freezes
- **Extended November exclusion** for audit period

## Configuration Commands

### 1. Base Configuration for All 3 Clusters

Run these commands for each cluster, replacing `CLUSTER_NAME` and `ZONE`:

```bash
# Switch to Extended channel and configure comprehensive maintenance controls
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --release-channel extended \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support \
    --maintenance-patch-version-disruption-interval=7776000s \
    --maintenance-window-start "2024-01-06T02:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**What this does:**
- **Extended channel**: Up to 24 months support, no auto minor upgrades (cost only during extended period)
- **"No minor or node upgrades" exclusion**: Allows control plane security patches only, blocks all disruptive upgrades
- **Persistent exclusion**: Auto-renews when new minor versions are adopted, tracks EoS
- **90-day patch interval**: Limits control plane patches to once every 90 days (quarterly)
- **Saturday 2-6 AM UTC window**: Patches only happen during this weekend window

### 2. Quarterly Code Freeze Exclusions

For each quarterly code freeze, add temporary "no upgrades" exclusions (blocks even patches):

```bash
# Q1 Code Freeze (example dates - adjust to your schedule)
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "q1-code-freeze-2024" \
    --add-maintenance-exclusion-start-time "2024-03-15T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-04-01T00:00:00Z" \
    --add-maintenance-exclusion-scope no_upgrades

# Q2 Code Freeze
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "q2-code-freeze-2024" \
    --add-maintenance-exclusion-start-time "2024-06-15T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-07-01T00:00:00Z" \
    --add-maintenance-exclusion-scope no_upgrades

# Q3 Code Freeze
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "q3-code-freeze-2024" \
    --add-maintenance-exclusion-start-time "2024-09-15T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-10-01T00:00:00Z" \
    --add-maintenance-exclusion-scope no_upgrades

# Q4 Code Freeze
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "q4-code-freeze-2024" \
    --add-maintenance-exclusion-start-time "2024-12-15T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2025-01-01T00:00:00Z" \
    --add-maintenance-exclusion-scope no_upgrades
```

### 3. Extended November Audit Exclusion

For your annual audit, create an extended freeze (may need to chain multiple 30-day exclusions):

```bash
# November audit freeze - Part 1
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "november-audit-2024-part1" \
    --add-maintenance-exclusion-start-time "2024-11-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-12-01T00:00:00Z" \
    --add-maintenance-exclusion-scope no_upgrades

# If audit extends longer, add Part 2 (ensure 48h gap in any 32-day window)
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "november-audit-2024-part2" \
    --add-maintenance-exclusion-start-time "2024-12-03T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-12-15T00:00:00Z" \
    --add-maintenance-exclusion-scope no_upgrades
```

### 4. Enable Scheduled Upgrade Notifications

Get 72-hour advance notice of any control plane patches:

```bash
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --send-scheduled-upgrade-notifications
```

## Configuration Summary

| Control | Setting | Purpose |
|---------|---------|---------|
| **Release Channel** | Extended | 24-month support, manual minor upgrades only |
| **Base Exclusion** | No minor or node upgrades (persistent) | Allows CP security patches, blocks disruptive changes |
| **Patch Interval** | 90 days | Quarterly patch cadence aligned with your processes |
| **Maintenance Window** | Saturday 2-6 AM UTC | Weekend-only patches during low-traffic hours |
| **Code Freeze Exclusions** | No upgrades (30 days each) | Blocks ALL changes during quarterly freezes |
| **Audit Exclusion** | No upgrades (extended November) | Complete freeze during annual audit |
| **Notifications** | 72-hour advance warning | Proactive alerts via Cloud Logging |

## Manual Minor Upgrade Process

When you're ready to upgrade minor versions (typically annually or as needed):

1. **Remove temporary exclusions** if any are active
2. **Test in dev/staging first**
3. **Trigger manual upgrade** during maintenance window:
   ```bash
   gcloud container clusters upgrade CLUSTER_NAME \
       --zone ZONE \
       --cluster-version TARGET_VERSION
   
   # For node pools after control plane completes
   gcloud container node-pools upgrade NODE_POOL_NAME \
       --cluster CLUSTER_NAME \
       --zone ZONE \
       --cluster-version TARGET_VERSION
   ```

## Monitoring and Compliance

Set up alerts for:
- **Deprecation insights**: `gcloud recommender insights list --insight-type=google.container.DiagnosisInsight`
- **Upgrade events**: Monitor Cloud Logging for `resource.type="gke_cluster"` upgrade events
- **Version drift**: Track when clusters fall behind current Extended channel versions

## Key Benefits for SOX Compliance

✅ **Change Control**: All disruptive upgrades require manual approval and execution  
✅ **Audit Trail**: Cloud Logging captures all upgrade events and exclusion changes  
✅ **Security Posture**: Critical patches still auto-apply during maintenance windows  
✅ **Predictability**: Upgrades only during defined Saturday windows  
✅ **Freeze Periods**: Complete lockdown during code freezes and audit  
✅ **Extended Support**: 24-month version lifecycle reduces upgrade frequency  

This configuration gives you maximum control while maintaining Google's security SLAs. The persistent exclusion automatically tracks version EoS dates, so you won't be surprised by forced upgrades.
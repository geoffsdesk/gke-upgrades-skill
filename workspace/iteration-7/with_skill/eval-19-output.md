# GKE Upgrade Notification Triage System

## Notification types and action levels

GKE sends several types of upgrade-related notifications. Here's how to triage them by urgency:

| Notification Type | Urgency | Action Required | Timeline |
|------------------|---------|-----------------|----------|
| **End-of-Life (EoS) warnings** | 🔴 **HIGH** | Plan upgrade or enable Extended channel | 30-90 days |
| **Security patch available** | 🟡 **MEDIUM** | Review and schedule if not auto-upgrading | 7-30 days |
| **Auto-upgrade scheduled (72h notice)** | 🟢 **LOW** | Verify timing, add exclusion if needed | 72 hours |
| **New version available** | 🔵 **INFO** | No action (unless accelerating manually) | None |
| **Upgrade completed** | 🔵 **INFO** | Validate cluster health | Post-upgrade |

## Triage decision tree

```
📧 New GKE notification received
├── Contains "End of Life" or "End of Support"?
│   ├── YES → 🔴 HIGH: Plan upgrade within 30 days
│   └── NO → Continue...
├── Contains "security" or "CVE"?
│   ├── YES → 🟡 MEDIUM: Review patch, schedule if not auto-applied
│   └── NO → Continue...
├── Contains "scheduled for auto-upgrade"?
│   ├── YES → 🔵 LOW: Check timing, add exclusion if conflicts
│   └── NO → Continue...
└── Contains "version available" or "upgrade completed"?
    └── YES → 🔵 INFO: File for reference, validate if completed
```

## Action playbooks by notification type

### 🔴 HIGH: End-of-Life (EoS) warnings

**Sample notification text:** *"Kubernetes version 1.28 will reach End of Life on..."*

**Immediate actions:**
1. **Inventory affected clusters:**
   ```bash
   # Find all clusters on the EoS version
   gcloud container clusters list --format="table(name,zone,currentMasterVersion,releaseChannel.channel)" | grep "1.28"
   ```

2. **Choose your path:**
   - **Option A (recommended):** Enroll in Extended channel for 24-month support (versions 1.27+)
   - **Option B:** Plan manual upgrade to next supported minor version
   - **Option C:** Apply 30-day "no upgrades" exclusion as temporary measure

3. **For Extended channel enrollment:**
   ```bash
   gcloud container clusters update CLUSTER_NAME \
     --zone ZONE \
     --release-channel extended
   ```

4. **Timeline:** Complete within 30 days of EoS warning

### 🟡 MEDIUM: Security patches

**Sample notification text:** *"Security update available for GKE version..."* or mentions CVE numbers

**Actions depend on your upgrade model:**

**If using auto-upgrades (recommended):**
- Verify patch will be auto-applied within your maintenance windows
- Check if maintenance exclusions might block the security patch
- Review CVE details to assess criticality

**If using manual upgrades:**
- Review the security bulletin details
- Schedule patch upgrade within 7-30 days based on severity
- Test in staging environment first

**Commands to check current security posture:**
```bash
# Check if cluster will auto-upgrade to the patched version
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(releaseChannel,maintenancePolicy)"

# Review maintenance exclusions that might block patches
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="yaml(maintenancePolicy.window.maintenanceExclusions)"
```

### 🔵 LOW: Auto-upgrade scheduled (72-hour notice)

**Sample notification text:** *"Your cluster is scheduled for automatic upgrade on..."*

**Standard response:**
1. **Verify timing is acceptable** - check if it conflicts with:
   - Code freezes or critical releases
   - High-traffic periods (Black Friday, end-of-quarter)
   - Planned maintenance or deployments

2. **If timing is problematic, add temporary exclusion:**
   ```bash
   # Block upgrade for up to 30 days
   gcloud container clusters update CLUSTER_NAME \
     --zone ZONE \
     --add-maintenance-exclusion-name "emergency-freeze" \
     --add-maintenance-exclusion-start-time "2024-01-15T00:00:00Z" \
     --add-maintenance-exclusion-end-time "2024-02-14T23:59:59Z" \
     --add-maintenance-exclusion-scope no_upgrades
   ```

3. **If timing is acceptable** - no action required, let auto-upgrade proceed

### 🔵 INFO: New version available / Upgrade completed

**No immediate action required** - these are informational. File for reference or use for validation.

**For "upgrade completed" notifications:**
- Run post-upgrade health checks if this was unexpected
- Update your cluster inventory spreadsheet

## Notification filtering and routing

Set up email rules or Cloud Monitoring alerting policies to automatically route notifications:

### High-priority routing (immediate Slack/PagerDuty)
- Subject contains: "End of Life", "End of Support", "EoS"
- Body contains: "will be force-upgraded"

### Medium-priority routing (team channel)
- Subject contains: "security", "CVE", "patch"
- Subject contains: "scheduled for auto-upgrade" (if you want advance notice)

### Low-priority routing (email folder)
- Subject contains: "version available", "upgrade completed"

## Team responsibilities matrix

| Role | EoS warnings | Security patches | Scheduled upgrades | Version announcements |
|------|-------------|------------------|-------------------|---------------------|
| **Platform Team** | Plan upgrade path | Assess & schedule | Verify timing | Monitor & file |
| **App Teams** | Test app compatibility | Review impact | Prepare for downtime | Update compatibility matrix |
| **SRE/Ops** | Execute upgrades | Apply patches | Monitor during window | Validate post-upgrade |

## Recommended notification settings

**Enable these notification types:**
- Upgrade operations (to get the 72-hour notice)
- End-of-life warnings
- Security bulletins
- Maintenance window notifications

**Consider disabling:**
- "Version available" notifications if you're using auto-upgrades (reduces noise)
- Upgrade completion notifications for dev/staging clusters

**Configure via Cloud Console → GKE → Notifications or:**
```bash
# Enable scheduled upgrade notifications (72h advance notice)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --enable-network-policy \
  --notification-config-enabled
```

## Sample triage checklist

Copy this checklist for your team's runbook:

```
GKE Notification Triage Checklist
- [ ] Notification type identified: EoS / Security / Scheduled / Info
- [ ] Urgency level assigned: High / Medium / Low / Info
- [ ] Affected clusters inventoried
- [ ] Conflicts with maintenance windows/freezes checked
- [ ] Action plan selected and timeline set
- [ ] Relevant teams notified (app owners, SRE, etc.)
- [ ] Follow-up scheduled if temporary measure applied
```

This triage system will help your team respond appropriately to each type of GKE notification without over-reacting to informational messages or under-reacting to critical EoS warnings.
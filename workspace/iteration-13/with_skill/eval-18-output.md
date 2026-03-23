# GKE Maintenance Configuration for Financial Services

I'll configure maintenance windows and exclusions for your regulated environment. This setup provides predictable weekend-only upgrades while respecting your quarterly freezes and annual audit period.

## Configuration Strategy

**Auto-upgrade approach:** Use release channels with maintenance windows + exclusions rather than disabling auto-upgrades. This maintains security patch compliance while giving you control over timing.

**Recommended setup:**
- **Weekend maintenance windows** for predictable timing
- **"No minor or node upgrades" exclusions** for maximum control during normal operations
- **"No upgrades" exclusions** for code freezes and audit periods
- **Regular or Stable release channel** for production stability

## 1. Maintenance Windows (Weekend Only)

Configure recurring weekend windows for all clusters:

```bash
# Cluster 1 - Saturday maintenance window (4-hour window)
gcloud container clusters update CLUSTER_1_NAME \
    --zone ZONE \
    --maintenance-window-start "2024-12-21T02:00:00Z" \
    --maintenance-window-end "2024-12-21T06:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Cluster 2 - Saturday maintenance window (staggered 2 hours later)
gcloud container clusters update CLUSTER_2_NAME \
    --zone ZONE \
    --maintenance-window-start "2024-12-21T04:00:00Z" \
    --maintenance-window-end "2024-12-21T08:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Cluster 3 - Sunday maintenance window
gcloud container clusters update CLUSTER_3_NAME \
    --zone ZONE \
    --maintenance-window-start "2024-12-22T02:00:00Z" \
    --maintenance-window-end "2024-12-22T06:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"
```

**Why staggered:** Prevents simultaneous upgrades across all clusters, allowing you to validate one before the next begins.

## 2. Release Channel Selection

Set production-appropriate channels:

```bash
# Option A: Regular channel (recommended for most financial services)
gcloud container clusters update CLUSTER_NAME --zone ZONE --release-channel regular

# Option B: Stable channel (most conservative, later patches)
gcloud container clusters update CLUSTER_NAME --zone ZONE --release-channel stable

# Option C: Extended channel (if you need 24-month support lifecycle)
gcloud container clusters update CLUSTER_NAME --zone ZONE --release-channel extended
```

**Recommendation:** Start with **Regular channel** - it provides the right balance of stability and timely security patches for financial services.

## 3. Persistent Maintenance Exclusions

Set up ongoing exclusions that automatically track version End of Support:

```bash
# "No minor or node upgrades" exclusion (allows security patches, blocks disruptive changes)
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "sox-compliance-control" \
    --add-maintenance-exclusion-scope "no_minor_or_node_upgrades" \
    --add-maintenance-exclusion-until-end-of-support
```

**This exclusion:**
- ✅ **Allows control plane security patches** (critical for compliance)
- ❌ **Blocks minor version upgrades** (prevents K8s API changes)
- ❌ **Blocks node pool upgrades** (prevents node image changes)
- 🔄 **Auto-renews** until version End of Support (no 6-month limit)

## 4. Quarterly Code Freeze Exclusions

Apply these **30 days before each quarterly freeze:**

```bash
# Q4 2024 Code Freeze (example: December 1-31)
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "q4-2024-code-freeze" \
    --add-maintenance-exclusion-start-time "2024-12-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-12-31T23:59:59Z" \
    --add-maintenance-exclusion-scope "no_upgrades"

# Q1 2025 Code Freeze (example: March 1-31)
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "q1-2025-code-freeze" \
    --add-maintenance-exclusion-start-time "2025-03-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2025-03-31T23:59:59Z" \
    --add-maintenance-exclusion-scope "no_upgrades"
```

**Schedule these exclusions in advance** - they can be added months ahead of time.

## 5. Annual Audit Period (November)

```bash
# November audit period - complete upgrade freeze
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "annual-audit-2024" \
    --add-maintenance-exclusion-start-time "2024-11-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-11-30T23:59:59Z" \
    --add-maintenance-exclusion-scope "no_upgrades"
```

## 6. Controlled Upgrade Process

When you need to perform upgrades during exclusion periods:

```bash
# Check current auto-upgrade target
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Manual control plane upgrade (bypasses maintenance windows/exclusions)
gcloud container clusters upgrade CLUSTER_NAME \
    --zone ZONE \
    --master \
    --cluster-version TARGET_VERSION

# Manual node pool upgrade with conservative settings
gcloud container node-pools update NODE_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --max-surge-upgrade 1 \
    --max-unavailable-upgrade 0

gcloud container node-pools upgrade NODE_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version TARGET_VERSION
```

## 7. Monitoring and Compliance

### Upgrade notifications (Preview - March 2026)
```bash
# Enable 72-hour advance notifications via Cloud Logging
# This will be available in March 2026 for control plane upgrades
```

### Current monitoring:
```bash
# Check maintenance exclusions status
gcloud container clusters describe CLUSTER_NAME \
    --zone ZONE \
    --format="yaml(maintenancePolicy)"

# Monitor auto-upgrade status
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Check for deprecation insights
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=LOCATION \
    --project=PROJECT_ID
```

## SOX Compliance Checklist

```markdown
SOX Compliance Verification
- [ ] Maintenance windows configured for weekend-only operations
- [ ] "No minor or node upgrades" exclusions active during normal operations
- [ ] Quarterly code freeze exclusions scheduled in advance
- [ ] Annual audit period exclusion configured for November
- [ ] Release channel set to Regular or Stable (not Rapid)
- [ ] Auto-upgrade controls documented and approved by compliance team
- [ ] Manual upgrade procedures documented for emergency patching
- [ ] Monitoring configured for upgrade events and compliance violations
- [ ] Change management process updated to include GKE upgrade procedures
```

## Key Benefits of This Approach

1. **Predictable timing:** Upgrades only during weekend maintenance windows
2. **Security compliance:** Control plane patches still applied automatically
3. **Change control:** Major changes (minor versions, node images) require manual approval
4. **Audit-friendly:** Complete upgrade freeze during audit periods
5. **Automated management:** Exclusions auto-renew, reducing operational overhead

## Emergency Override

If critical security patches need immediate application:

```bash
# Temporarily remove exclusion
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --remove-maintenance-exclusion-name "sox-compliance-control"

# Apply patch, then restore exclusion
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "sox-compliance-control" \
    --add-maintenance-exclusion-scope "no_minor_or_node_upgrades" \
    --add-maintenance-exclusion-until-end-of-support
```

This configuration gives you the control needed for SOX compliance while maintaining GKE's automated security patching benefits. The persistent exclusions eliminate the need for manual renewal every 6 months.
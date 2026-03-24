# GKE Upgrade Control Strategy for Financial Services

For maximum control while maintaining security compliance, here's the recommended configuration:

## Primary Strategy: Release Channel + "No Minor or Node Upgrades" Exclusion

This gives you the optimal balance of control and security:

### 1. Channel Selection
```bash
# Use Regular or Stable channel (not Extended unless you have compliance requirements for 24-month versions)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular  # or 'stable' for extra stability validation
```

**Why Regular/Stable over Extended:**
- Regular/Stable: Security patches auto-apply, minor upgrades blocked by exclusion
- Extended: Minor upgrades are NOT automated - you must plan and execute them manually before EoS

### 2. Maximum Control Exclusion
```bash
# Apply "no minor or node upgrades" exclusion - this is your primary control mechanism
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "finserv-change-control" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**What this exclusion does:**
- ✅ **Security patches on control plane auto-apply** (maintains security posture)
- 🛑 **Minor version upgrades blocked** (you control timing)
- 🛑 **Node pool upgrades blocked** (you control timing)
- 🔄 **Automatically renews** when you eventually upgrade to a new minor version

### 3. Strict Change Windows
```bash
# Configure narrow maintenance windows aligned with your change freezes
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-end "2024-01-06T04:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## Multi-Environment Strategy

```bash
# Development: Regular channel, no exclusions (early validation)
gcloud container clusters update dev-cluster \
  --zone ZONE \
  --release-channel regular

# Staging: Regular channel with exclusions, manual minor upgrades
gcloud container clusters update staging-cluster \
  --zone ZONE \
  --release-channel regular \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Production: Stable channel with exclusions, manual minor upgrades
gcloud container clusters update prod-cluster \
  --zone ZONE \
  --release-channel stable \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## Change Control Process

### Planned Minor Version Upgrades (Quarterly)

1. **Remove exclusion temporarily:**
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "finserv-change-control"
```

2. **Execute controlled upgrade during change window:**
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION
```

3. **Re-apply exclusion after upgrade:**
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "finserv-change-control" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

### Emergency Security Exclusions (Code Freezes)

For critical periods (earnings, regulatory deadlines):
```bash
# Temporarily block ALL upgrades including patches (max 30 days)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "earnings-freeze" \
  --add-maintenance-exclusion-start-time "2024-01-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-01-22T00:00:00Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## Monitoring & Compliance

### 1. Security Patch Tracking
```bash
# Monitor control plane patch status
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Check for security bulletins
gcloud logging read 'resource.type="gke_cluster" AND jsonPayload.operationType="UPDATE_CLUSTER"' \
  --format="table(timestamp, jsonPayload.targetVersion)"
```

### 2. Version Compliance Dashboard
```bash
# List all clusters and versions for compliance reporting
gcloud container clusters list \
  --format="table(name, location, currentMasterVersion, releaseChannel.channel, status)"
```

### 3. Scheduled Upgrade Notifications (Preview)
```bash
# Enable 72-hour advance notifications for control plane upgrades
# (Available March 2026 - configure via Cloud Logging alerting policies)
```

## Key Benefits of This Approach

| Requirement | How This Strategy Delivers |
|------------|---------------------------|
| **Security compliance** | Control plane security patches auto-apply |
| **Change control** | Minor upgrades only happen when you approve them |
| **No surprise disruptions** | Node pool upgrades blocked until you're ready |
| **Predictable timing** | Maintenance windows + manual triggers = full control |
| **Audit trail** | All upgrade events logged in Cloud Logging |
| **Rollback safety** | Two-step control plane upgrades with soak periods |

## What NOT to Do

❌ **Don't use "No channel"** - Limited exclusion options, no Extended support, harder to control
❌ **Don't use Extended channel as default** - Minor upgrades not automated, requires more manual planning
❌ **Don't chain "no upgrades" exclusions** - Risk falling behind on security patches

This configuration gives you maximum upgrade timing control while maintaining Google's security patch SLA - exactly what financial services needs for regulatory compliance with minimal operational overhead.
# GKE Upgrade Control Configuration for Financial Services

For maximum control over upgrade timing while maintaining security, I recommend **Release Channel + Maintenance Exclusions** as your primary strategy. This gives you the most granular control available in GKE.

## Recommended Configuration

### 1. Release Channel Selection

**Primary recommendation: Regular Channel** for production clusters
- Full SLA coverage (unlike Rapid)
- Security patches arrive within days of release
- Minor versions arrive ~2-4 weeks after upstream Kubernetes
- Balances security responsiveness with stability

**Alternative: Stable Channel** if you need maximum stability
- Same security patch timing as Regular
- Minor versions arrive ~4-6 weeks after upstream
- Additional validation period before promotion

**Avoid Extended Channel** for security-sensitive workloads unless you have dedicated processes for manual minor upgrades (Extended doesn't auto-upgrade minor versions).

### 2. Maintenance Windows + Exclusions Strategy

Configure **recurring maintenance windows** aligned with your change windows:
```bash
# Example: Saturday 2-6 AM maintenance window
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-03-09T02:00:00Z" \
  --maintenance-window-end "2024-03-09T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

Then use **"No minor or node upgrades"** exclusions to block disruptive changes while allowing security patches:
```bash
# Allows control plane security patches, blocks minor + node upgrades
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "financial-controls" \
  --add-maintenance-exclusion-start-time "2024-03-01T00:00:00Z" \
  --add-maintenance-exclusion-until-end-of-support \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

### 3. Why This Configuration Is Optimal

| What you get | How it helps financial services |
|-------------|--------------------------------|
| **Security patches auto-applied** | Control plane gets CVE fixes within days, no manual intervention needed |
| **No surprise minor upgrades** | Disruptive changes only happen when you initiate them |
| **Change window compliance** | All maintenance happens during your defined windows |
| **Persistent control** | Exclusion automatically renews when you do upgrade to the next minor version |
| **Emergency override** | Can still do manual upgrades for critical security issues |

### 4. Operational Workflow

**Steady state:** Clusters receive only control plane security patches during maintenance windows. No node or minor version changes.

**Planned upgrades:** Every 6-12 months (before End of Support):
1. Remove maintenance exclusion temporarily
2. Test upgrade in staging environment first
3. Execute production upgrade during scheduled change window
4. Restore maintenance exclusion for continued control

**Emergency security upgrades:** Manual upgrade capability remains available outside maintenance windows if needed.

## Multi-Environment Strategy

```bash
# Development: Rapid channel (early testing)
gcloud container clusters update dev-cluster \
  --release-channel rapid

# Staging: Regular channel (matches production timing)
gcloud container clusters update staging-cluster \
  --release-channel regular

# Production: Regular channel + exclusions (maximum control)
gcloud container clusters update prod-cluster \
  --release-channel regular
# + maintenance exclusions as shown above
```

## Additional Financial Services Controls

### Disruption Intervals
Slow down the frequency of patches if needed:
```bash
# Only allow patches every 30 days instead of default 7 days
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-patch-version-disruption-interval 30
```

### Scheduled Notifications
Enable 72-hour advance notifications (preview):
```bash
# Opt into scheduled upgrade notifications via Cloud Logging
# (Specific implementation details available March 2026)
```

### Accelerated Patch Mode
For compliance requirements needing faster patches:
```bash
# Opt into accelerated patch rollouts (e.g., FedRAMP)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --patch-update accelerated
```

## What NOT to Do

❌ **Don't use "No channel"** - Lacks the granular exclusion types you need and is a legacy configuration

❌ **Don't disable auto-upgrades entirely** - Loses GKE's security value proposition

❌ **Don't use "No upgrades" exclusions long-term** - 30-day maximum blocks even security patches

## Migration Path (if currently on "No channel")

```bash
# Step 1: Add temporary "no upgrades" exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "migration-freeze" \
  --add-maintenance-exclusion-start-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-end-time "$(date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-scope no_upgrades

# Step 2: Migrate to Regular channel
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular

# Step 3: Replace with persistent "no minor or node" exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion "migration-freeze" \
  --add-maintenance-exclusion-name "financial-controls" \
  --add-maintenance-exclusion-start-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-until-end-of-support \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

This configuration gives you maximum control over disruptive changes while maintaining GKE's automated security patching - exactly what financial services environments need.
# GKE Maintenance Exclusion Configuration

Based on your requirements, here's the exact configuration for your three scenarios:

## 1. Quarterly Code Freeze (June)

Use a **"no upgrades"** exclusion to block ALL upgrades during your code freeze:

```bash
# June code freeze (example: June 15-30, 2024)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "june-code-freeze" \
  --add-maintenance-exclusion-start-time "2024-06-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

**Key points:**
- Blocks patches, minor upgrades, AND node upgrades
- Maximum 30 days per exclusion
- This is honored even after End of Support (emergency protection)

## 2. Black Friday/Cyber Monday (November)

Use **"no upgrades"** exclusion for your peak traffic period:

```bash
# BFCM exclusion (example: November 20 - December 5, 2024)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze" \
  --add-maintenance-exclusion-start-time "2024-11-20T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-05T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## 3. No Minor Version Auto-Upgrades (Year-round Control)

Use **"no minor or node upgrades"** exclusion that tracks End of Support automatically:

```bash
# Persistent exclusion - no minor upgrades without approval
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "no-minor-auto-upgrades" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Why "no minor or node upgrades" instead of just "no minor upgrades"?**
- Prevents control plane and node minor version skew
- Gives you maximum control over both components
- Still allows security patches on the control plane
- The `--add-maintenance-exclusion-until-end-of-support` flag automatically renews when you upgrade to a new minor version

## Complete Setup Script

```bash
#!/bin/bash
# Replace these variables
CLUSTER_NAME="your-cluster-name"
ZONE="us-central1-a"  # or --region for regional clusters

# 1. Year-round: No minor upgrades without approval
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "no-minor-auto-upgrades" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# 2. June code freeze (adjust dates yearly)
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-06-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# 3. BFCM freeze (adjust dates yearly)
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-11-20T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-05T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## Verification Commands

```bash
# Check all exclusions
gcloud container clusters describe $CLUSTER_NAME \
  --zone $ZONE \
  --format="yaml(maintenancePolicy.window.recurringWindow,maintenancePolicy.exclusions)"

# Check auto-upgrade status
gcloud container clusters get-upgrade-info $CLUSTER_NAME --zone $ZONE
```

## When You Want to Upgrade Minor Versions

With the persistent "no minor or node upgrades" exclusion in place, you'll initiate minor upgrades manually:

```bash
# Check available versions
gcloud container get-server-config --zone $ZONE \
  --format="yaml(channels.REGULAR.availableVersions)"

# Upgrade control plane
gcloud container clusters upgrade $CLUSTER_NAME \
  --zone $ZONE \
  --master \
  --cluster-version TARGET_VERSION

# Upgrade node pools
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster $CLUSTER_NAME \
  --zone $ZONE \
  --cluster-version TARGET_VERSION
```

## Important Notes

1. **Exclusion Limits:** Maximum 3 "no upgrades" exclusions per cluster, with at least 48 hours available for maintenance in any 32-day window
2. **Manual Upgrades Bypass Exclusions:** If you run `gcloud container clusters upgrade` manually, it ignores all maintenance exclusions
3. **Security Patches:** The persistent exclusion still allows control plane security patches — you're not creating security debt
4. **Annual Renewal:** Update the June and BFCM exclusion dates each year

This configuration gives you complete control while maintaining security patch compliance.
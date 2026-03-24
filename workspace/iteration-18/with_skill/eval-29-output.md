# GKE Maintenance Exclusion Configuration

Based on your requirements, here's the exact configuration for your three scenarios:

## 1. Quarterly Code Freeze (June) - "No Upgrades" Exclusion

For your June code freeze, use a **"no upgrades"** exclusion that blocks ALL upgrades including patches:

```bash
# June code freeze (example: June 1-30, 2024)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

**Key constraints:**
- Maximum 30 days per exclusion (hard limit)
- For longer freezes, chain multiple exclusions
- You can have up to 3 "no upgrades" exclusions per cluster

## 2. Black Friday/Cyber Monday (November) - "No Upgrades" Exclusion

```bash
# BFCM period (example: November 15 - December 15, 2024)
# Split into two 30-day exclusions due to limit

# First exclusion: Nov 15 - Dec 14
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze-part1-2024" \
  --add-maintenance-exclusion-start-time "2024-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-14T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# Second exclusion: Dec 15 - Dec 31 (if needed)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze-part2-2024" \
  --add-maintenance-exclusion-start-time "2024-12-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## 3. No Automatic Minor Version Upgrades - Persistent Exclusion

For **never allowing minor version auto-upgrades**, use a persistent **"no minor or node upgrades"** exclusion:

```bash
# Permanent exclusion that tracks End of Support automatically
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "no-auto-minor-upgrades" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**What this does:**
- **Allows**: Control plane security patches (automatic)
- **Blocks**: Minor version upgrades AND node pool upgrades (requires your manual trigger)
- **Duration**: Automatically tracks End of Support - no need to renew
- **Rollover**: When you manually upgrade to a new minor version, the exclusion automatically applies to the new version

## Complete Configuration Script

Here's a script to set up all three exclusions for a cluster:

```bash
#!/bin/bash
CLUSTER_NAME="your-cluster-name"
ZONE="your-zone"

# 1. Persistent no-minor-upgrades exclusion
echo "Setting up permanent no-minor-upgrades exclusion..."
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "no-auto-minor-upgrades" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# 2. June code freeze 2024
echo "Setting up June code freeze..."
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# 3. BFCM freeze 2024 (split into two parts due to 30-day limit)
echo "Setting up BFCM freeze part 1..."
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze-part1-2024" \
  --add-maintenance-exclusion-start-time "2024-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-14T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

echo "Setting up BFCM freeze part 2..."
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze-part2-2024" \
  --add-maintenance-exclusion-start-time "2024-12-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

echo "All maintenance exclusions configured!"
```

## Verify Configuration

Check your exclusions are active:

```bash
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="yaml(resourceUsageExportConfig.maintenancePolicy)"

# Or view in a table format
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(resourceUsageExportConfig.maintenancePolicy.maintenanceExclusions[].name,resourceUsageExportConfig.maintenancePolicy.maintenanceExclusions[].startTime,resourceUsageExportConfig.maintenancePolicy.maintenanceExclusions[].endTime,resourceUsageExportConfig.maintenancePolicy.maintenanceExclusions[].exclusionOptions.scope)"
```

## When You Want Minor Upgrades

Since you have the persistent "no minor or node upgrades" exclusion, you'll manually trigger minor upgrades when ready:

```bash
# Control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version NEW_MINOR_VERSION

# Then node pools (after CP upgrade completes)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version NEW_MINOR_VERSION
```

## Important Notes

- **Manual upgrades bypass ALL exclusions** - be careful not to accidentally upgrade during freeze periods
- **Security patches still apply** through the "no minor or node upgrades" exclusion - this keeps you secure while giving you control
- **"No upgrades" exclusions are honored even past End of Support** - useful for critical business periods
- **The persistent exclusion automatically renews** when you upgrade to new minor versions

This configuration gives you maximum control while maintaining security posture through automatic patch updates.
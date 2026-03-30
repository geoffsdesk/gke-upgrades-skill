# GKE Maintenance Exclusion Configuration

Based on your requirements, here's the exact configuration for your three scenarios:

## 1. Quarterly Code Freeze (June) - "No Upgrades" Exclusion

For complete upgrade freeze during code freeze periods:

```bash
# June code freeze (example: June 1-30, 2025)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "Q2-code-freeze-2025" \
  --add-maintenance-exclusion-start-time "2025-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# Repeat for each quarterly freeze
```

**Important:** "No upgrades" exclusions are limited to 30 days maximum. For longer freezes, chain multiple exclusions:

```bash
# Extended freeze - Month 1
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "Q2-code-freeze-2025-part1" \
  --add-maintenance-exclusion-start-time "2025-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# Extended freeze - Month 2 (if needed)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "Q2-code-freeze-2025-part2" \
  --add-maintenance-exclusion-start-time "2025-07-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-07-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## 2. Black Friday/Cyber Monday (November) - "No Upgrades" Exclusion

```bash
# BFCM freeze (example: November 15 - December 5, 2025)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "BFCM-freeze-2025" \
  --add-maintenance-exclusion-start-time "2025-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-12-05T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## 3. Never Auto-Upgrade Minor Versions - Persistent Exclusion

For permanent control over minor version upgrades while allowing security patches:

```bash
# Persistent exclusion - tracks End of Support automatically
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "no-minor-auto-upgrades" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Why "no_minor_or_node_upgrades" instead of just "no_minor_upgrades"?**
- Prevents control plane minor upgrades (requires your approval)
- Prevents node pool minor upgrades (avoids version skew)
- Still allows control plane security patches automatically
- Provides maximum control over disruptive changes

## Complete Setup Script

Here's a complete script to configure all exclusions for a cluster:

```bash
#!/bin/bash

CLUSTER_NAME="your-cluster-name"
ZONE="your-zone"

# 1. Permanent minor version control
echo "Setting up permanent minor version control..."
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "no-minor-auto-upgrades" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# 2. June code freeze (adjust dates as needed)
echo "Setting up June code freeze..."
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "Q2-code-freeze-2025" \
  --add-maintenance-exclusion-start-time "2025-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# 3. BFCM freeze (adjust dates as needed)
echo "Setting up BFCM freeze..."
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "BFCM-freeze-2025" \
  --add-maintenance-exclusion-start-time "2025-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-12-05T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

echo "All maintenance exclusions configured!"
```

## Verification

Check your configured exclusions:

```bash
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="yaml(maintenancePolicy)"
```

## Workflow for Manual Minor Version Upgrades

Since you're blocking minor auto-upgrades, here's how to manually upgrade when ready:

```bash
# 1. Check available versions
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels)"

# 2. Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION

# 3. Upgrade node pools (Standard clusters only)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

**Note:** Manual upgrades bypass ALL maintenance controls (windows and exclusions), so they execute immediately when triggered.

## Important Considerations

1. **Security patches still apply** with the persistent exclusion - only minor versions are blocked
2. **Maximum 3 "no_upgrades" exclusions per cluster** - plan your freeze periods carefully
3. **48-hour maintenance availability** required in any 32-day period - don't overlap exclusions
4. **EoS enforcement** still applies - clusters will be force-upgraded when versions reach End of Support (use Extended channel for longer support)
5. **Release channel required** - these exclusions only work on release channels, not legacy "No channel"

This configuration gives you complete control over minor versions while maintaining security through automatic patches, with the ability to freeze all upgrades during critical business periods.
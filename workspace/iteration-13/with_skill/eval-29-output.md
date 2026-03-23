# GKE Maintenance Exclusion Configuration

Based on your requirements, here's the exact configuration for your maintenance exclusions:

## 1. Quarterly Code Freeze (June) - "No Upgrades" Exclusion

This blocks ALL upgrades (patches, minor versions, and node upgrades) during your June code freeze:

```bash
# June code freeze - blocks everything for 30 days max
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "june-code-freeze" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

⚠️ **Important:** The `no_upgrades` exclusion has a 30-day maximum. If your June freeze is longer than 30 days, you'll need to chain exclusions:

```bash
# First 30 days
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-part1" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# If freeze extends into July (create this exclusion before June 30)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-part2" \
  --add-maintenance-exclusion-start-time "2024-07-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-07-15T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## 2. Black Friday/Cyber Monday (November) - "No Upgrades" Exclusion

```bash
# BFCM - blocks everything during peak traffic
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze" \
  --add-maintenance-exclusion-start-time "2024-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-15T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## 3. Permanent Minor Version Control - "No Minor or Node Upgrades" Exclusion

This gives you maximum control - allows security patches on the control plane but requires your approval for all minor version and node upgrades:

```bash
# Persistent exclusion that tracks End of Support automatically
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "require-manual-minor-upgrades" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

The `--add-maintenance-exclusion-until-end-of-support` flag automatically renews the exclusion whenever your cluster adopts a new minor version, so you only need to set this once.

## Complete Setup Script

Here's a complete script to configure all exclusions for a cluster:

```bash
#!/bin/bash
CLUSTER_NAME="your-cluster-name"
ZONE="us-central1-a"  # or your zone/region

echo "Setting up maintenance exclusions for $CLUSTER_NAME..."

# 1. Persistent minor version control
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "require-manual-minor-upgrades" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# 2. June code freeze
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "june-code-freeze" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# 3. BFCM freeze
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze" \
  --add-maintenance-exclusion-start-time "2024-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-15T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

echo "Exclusions configured. Verifying..."

# Verify configuration
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE \
  --format="yaml(maintenancePolicy.window.maintenanceExclusions)"
```

## Verification Commands

Check your exclusion configuration:

```bash
# List all exclusions
gcloud container clusters describe CLUSTER_NAME --zone ZONE \
  --format="table(maintenancePolicy.window.maintenanceExclusions[].name,maintenancePolicy.window.maintenanceExclusions[].startTime,maintenancePolicy.window.maintenanceExclusions[].endTime,maintenancePolicy.window.maintenanceExclusions[].scope)"

# Check current auto-upgrade status
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION
```

## When You Want to Upgrade

Since you're blocking minor versions permanently, here's how to upgrade when YOU decide:

```bash
# 1. Check available versions
gcloud container get-server-config --zone ZONE --format="yaml(channels)"

# 2. Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION

# 3. Then upgrade node pools
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

## Key Points

- **Control plane patches** will still be applied automatically (important for security)
- **Minor version upgrades** require your explicit action
- **Node pool upgrades** require your explicit action  
- **During June/November freezes** - absolutely nothing gets upgraded
- **End of Support enforcement** - the persistent exclusion automatically tracks EoS, so you won't be force-upgraded until the very end of the version's support lifecycle

This configuration gives you maximum control while still maintaining security through automatic control plane patches.
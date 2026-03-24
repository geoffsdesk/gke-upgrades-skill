# GKE Maintenance Exclusion Configuration

Based on your requirements, here's the exact configuration for your three scenarios:

## 1. Persistent "No Minor Upgrades" Control (Year-round)

This blocks all minor version upgrades while allowing patches and node upgrades. You must manually trigger minor upgrades when ready.

```bash
# Apply to each cluster
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "no-minor-upgrades-persistent" \
  --add-maintenance-exclusion-scope no_minor_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Key benefits:**
- Automatically tracks each version's End of Support date
- No need to update dates when you eventually do minor upgrades
- Still get security patches on control plane
- Still get node pool upgrades (patches)

## 2. Quarterly Code Freeze (June)

30-day "no upgrades" exclusion that blocks ALL upgrades including patches:

```bash
# June code freeze (adjust dates for your specific freeze window)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## 3. Black Friday/Cyber Monday (November)

```bash
# BFCM freeze (extend dates as needed for your peak season)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-05T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## Complete Setup Script

```bash
#!/bin/bash

# Configuration
CLUSTER_NAME="your-cluster-name"
ZONE="us-central1-a"  # or --region for regional clusters

echo "Setting up maintenance exclusions for $CLUSTER_NAME..."

# 1. Persistent minor upgrade control
echo "✓ Adding persistent 'no minor upgrades' exclusion..."
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "no-minor-upgrades-persistent" \
  --add-maintenance-exclusion-scope no_minor_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# 2. June code freeze
echo "✓ Adding June code freeze exclusion..."
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# 3. BFCM freeze
echo "✓ Adding BFCM freeze exclusion..."
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-05T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

echo "✅ All exclusions configured!"

# Verify configuration
echo "Current exclusions:"
gcloud container clusters describe $CLUSTER_NAME \
  --zone $ZONE \
  --format="table(maintenancePolicy.window.maintenanceExclusions[].name,maintenancePolicy.window.maintenanceExclusions[].exclusionOptions.scope)"
```

## Verification Commands

```bash
# Check all active exclusions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="yaml(maintenancePolicy.window.maintenanceExclusions)"

# Check auto-upgrade status
gcloud container clusters get-upgrade-info CLUSTER_NAME \
  --zone ZONE \
  --format="table(autoUpgradeStatus,minorTargetVersion,patchTargetVersion)"
```

## Important Notes

**Exclusion Limits:**
- Maximum 3 "no_upgrades" exclusions per cluster
- Within any 32-day rolling window, at least 48 hours must be available for maintenance
- Plan your June and November freezes carefully to avoid hitting these limits

**Manual Upgrades Still Work:**
- These exclusions only block AUTO-upgrades
- You can still manually trigger upgrades anytime with `gcloud container clusters upgrade`

**When to Manually Upgrade:**
With the persistent "no minor upgrades" exclusion, you'll need to manually upgrade when ready:

```bash
# When you're ready for a minor version bump
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION

# Then upgrade node pools
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

**Updating Future Years:**
For 2025 and beyond, update the June/November exclusion dates:

```bash
# Remove old year's exclusions
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "june-code-freeze-2024"

# Add new year's exclusions
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-2025" \
  --add-maintenance-exclusion-start-time "2025-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

This configuration gives you complete control over minor upgrades while maintaining security through automatic patches, with specific protection during your critical business periods.
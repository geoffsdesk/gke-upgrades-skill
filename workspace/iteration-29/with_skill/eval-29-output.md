Based on your requirements, here's the exact maintenance exclusion configuration for your GKE clusters:

## Configuration Overview

You'll need **two types of exclusions**:
1. **Persistent "no minor or node upgrades" exclusion** - blocks all minor version upgrades year-round
2. **Temporary "no upgrades" exclusions** - blocks everything during your critical periods

## 1. Persistent Minor Version Control

Apply this once per cluster to block all minor version upgrades while still allowing security patches:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "no-minor-upgrades-policy" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**What this does:**
- Blocks minor version upgrades (e.g., 1.29 → 1.30)
- Blocks node pool upgrades
- **Still allows** control plane security patches within your current minor version
- Automatically tracks End of Support dates - no need to renew manually

## 2. Critical Period "No Upgrades" Exclusions

### June Code Freeze (Example: June 1-30, 2024)
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

### Black Friday/Cyber Monday (Example: November 15 - December 5, 2024)
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-05T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## Complete Setup Script

Replace the placeholders and run this for each cluster:

```bash
#!/bin/bash
CLUSTER_NAME="your-cluster-name"
ZONE="us-central1-a"  # or your zone/region

# 1. Set up permanent minor version control
echo "Setting up permanent minor version control..."
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "no-minor-upgrades-policy" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# 2. June 2024 code freeze
echo "Adding June 2024 code freeze exclusion..."
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# 3. BFCM 2024 freeze
echo "Adding BFCM 2024 freeze exclusion..."
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-05T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

echo "Maintenance exclusions configured for $CLUSTER_NAME"
```

## How Your Upgrade Process Will Work

1. **Day-to-day**: Only control plane security patches auto-apply
2. **June & BFCM**: No upgrades at all (including patches)
3. **Minor version upgrades**: Only when you manually trigger them

### When You Want to Upgrade to a New Minor Version

```bash
# Check what versions are available
gcloud container get-server-config --zone ZONE --format="yaml(channels)"

# Upgrade control plane first
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

The persistent exclusion stays in place - you don't need to remove it before manual upgrades.

## Important Notes

- **30-day limit**: "No upgrades" exclusions are limited to 30 days each. For longer freezes, chain multiple exclusions.
- **Maximum 3 exclusions**: You can have up to 3 "no upgrades" exclusions per cluster.
- **Manual upgrades bypass exclusions**: When you manually trigger upgrades, they ignore all exclusion settings.
- **EoS enforcement**: Even with exclusions, GKE will force-upgrade clusters at End of Support (consider Extended channel for maximum flexibility).

## Annual Maintenance

Each year, add new "no upgrades" exclusions for your June and BFCM periods. The persistent minor version exclusion renews automatically.

This configuration gives you maximum control while still maintaining security through automatic patch updates outside your critical periods.
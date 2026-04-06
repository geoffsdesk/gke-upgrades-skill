# GKE Maintenance Exclusion Configuration

Based on your requirements, you need two types of exclusions:

## 1. Permanent Minor Version Control

For **never allowing minor version upgrades without explicit approval**, use a persistent "no minor or node upgrades" exclusion:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "no-minor-upgrades-permanent" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

This exclusion:
- **Blocks minor version upgrades AND node pool upgrades**
- **Allows control plane security patches** (critical for security posture)
- **Automatically renews** when you manually upgrade to a new minor version
- **Tracks End of Support** - no need to manually manage expiration dates

## 2. Quarterly Code Freeze (June)

For your **June code freeze**, add a "no upgrades" exclusion that blocks everything:

```bash
# Example: June 1-30, 2025 freeze
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-2025" \
  --add-maintenance-exclusion-start-time "2025-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## 3. Black Friday/Cyber Monday Freeze (November)

For your **BFCM freeze**, use the same pattern:

```bash
# Example: Nov 15 - Dec 5, 2025 (extended BFCM period)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze-2025" \
  --add-maintenance-exclusion-start-time "2025-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-12-05T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## Complete Configuration Script

Here's a complete script for one cluster:

```bash
#!/bin/bash
CLUSTER_NAME="your-cluster-name"
ZONE="your-zone"

# 1. Permanent minor version control
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "no-minor-upgrades-permanent" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# 2. June 2025 code freeze (adjust dates as needed)
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-2025" \
  --add-maintenance-exclusion-start-time "2025-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# 3. BFCM 2025 freeze (adjust dates as needed)
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze-2025" \
  --add-maintenance-exclusion-start-time "2025-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-12-05T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## Important Notes

### Exclusion Types Explained
- **"no_minor_or_node_upgrades"**: Blocks minor version upgrades AND node pool upgrades, but **allows control plane security patches**. This is your primary control mechanism.
- **"no_upgrades"**: Blocks **everything** including security patches. Use only for critical freeze periods (June, BFCM). Limited to 30 days maximum.

### Annual Planning
You'll need to **recreate the seasonal exclusions each year**:
```bash
# Delete old exclusions
gcloud container clusters update CLUSTER_NAME --zone ZONE \
  --remove-maintenance-exclusion-name "june-code-freeze-2025"

# Add new ones for 2026
gcloud container clusters update CLUSTER_NAME --zone ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-2026" \
  --add-maintenance-exclusion-start-time "2026-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2026-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

### When You Want to Upgrade Minor Versions
With the permanent exclusion in place, minor upgrades happen **only when you trigger them manually**:

```bash
# Manual control plane upgrade
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION

# Manual node pool upgrade  
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

The persistent exclusion automatically renews for the new minor version after your manual upgrade.

### Verification
Check your current exclusions:
```bash
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="yaml(maintenancePolicy)"
```

This configuration gives you:
- ✅ **Security patches applied automatically** (except during freeze periods)
- ✅ **Full control over minor version timing**
- ✅ **Complete freeze during your critical business periods**
- ✅ **No manual exclusion management** for minor versions (auto-renews)
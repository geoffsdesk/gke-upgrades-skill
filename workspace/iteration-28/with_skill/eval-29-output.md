Here's the exact configuration for your three maintenance exclusion requirements:

## 1. Quarterly Code Freeze (June)

```bash
# June code freeze (30-day maximum per exclusion)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "q2-code-freeze" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

**Note:** The "no upgrades" exclusion blocks ALL upgrades (patches, minor, nodes) but is limited to 30 days maximum. For June (30 days), this fits exactly. You'll need to create a new exclusion each year.

## 2. Black Friday/Cyber Monday Period (November)

```bash
# BFCM freeze - Option A: Full month
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze" \
  --add-maintenance-exclusion-start-time "2024-11-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-11-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# BFCM freeze - Option B: Just the critical period (recommended)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze" \
  --add-maintenance-exclusion-start-time "2024-11-20T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-05T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

**Recommendation:** Use Option B (15-day critical period) to minimize security patch delays while protecting your highest-traffic period.

## 3. Block Minor Version Auto-Upgrades (Permanent)

```bash
# Persistent exclusion - blocks minor + node upgrades, allows CP security patches
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "no-auto-minor-upgrades" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Key benefits:**
- **No time limit** - automatically tracks each version's End of Support
- **Security patches still applied** to control plane
- **Manual control** over when minor upgrades happen
- **Prevents version skew** between control plane and nodes

## Complete Setup Script

```bash
#!/bin/bash
CLUSTER_NAME="your-cluster-name"
ZONE="your-zone"

# Permanent minor version control
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "no-auto-minor-upgrades" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# June code freeze (create annually)
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "q2-code-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# BFCM freeze (create annually)
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-11-20T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-05T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

echo "Maintenance exclusions configured successfully"
```

## Verify Configuration

```bash
# Check all exclusions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(maintenancePolicy.window.maintenanceExclusions[].name,
                   maintenancePolicy.window.maintenanceExclusions[].exclusionOptions.scope,
                   maintenancePolicy.window.maintenanceExclusions[].startTime,
                   maintenancePolicy.window.maintenanceExclusions[].endTime)"
```

## Manual Minor Version Upgrade Process

When you're ready to upgrade to a new minor version:

```bash
# 1. Check available versions
gcloud container get-server-config --zone ZONE --format="yaml(channels)"

# 2. Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION

# 3. Upgrade node pools
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

## Important Notes

1. **Security patches continue** - The "no minor or node upgrades" exclusion allows control plane security patches
2. **Manual upgrades bypass exclusions** - When you run upgrade commands manually, they ignore all maintenance controls
3. **EoS enforcement honored** - Even with exclusions, GKE will force-upgrade at End of Support
4. **Annual renewal needed** - Recreate June and BFCM exclusions each year with updated dates
5. **Maximum 3 exclusions** per cluster - you're using all 3 slots with this configuration

This setup gives you maximum control while maintaining security posture through continued patch application.
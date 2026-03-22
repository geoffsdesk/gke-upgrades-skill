I'll provide the exact maintenance exclusion configuration for your three requirements. You'll need different exclusion types for each scenario.

## Configuration Commands

### 1. Quarterly Code Freeze (June) - "No upgrades" exclusion

This blocks ALL upgrades (patches, minor, nodes) for up to 30 days:

```bash
# June code freeze - adjust dates for your specific freeze period
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

### 2. Black Friday/Cyber Monday (November) - "No upgrades" exclusion

Same type as code freeze - blocks everything during your critical period:

```bash
# BFCM freeze - typically mid-November through early December
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-05T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

### 3. Block Minor Version Upgrades Permanently - "No minor or node upgrades" exclusion

This gives you maximum control - allows security patches but blocks disruptive changes:

```bash
# Persistent exclusion that auto-renews with each minor version
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "no-minor-upgrades-permanent" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## Why "No minor or node upgrades" instead of just "No minor upgrades"

I'm recommending `no_minor_or_node_upgrades` for your permanent exclusion because:
- **Prevents control plane/node version skew** - keeps everything aligned
- **Still allows security patches** on the control plane
- **Maximum control** over both minor versions AND node pool upgrades
- **No expiration hassle** - the `--add-maintenance-exclusion-until-end-of-support` flag automatically tracks the version's End of Support date

## Complete Setup Script

Here's a script to apply all three exclusions to a cluster:

```bash
#!/bin/bash
CLUSTER_NAME="your-cluster-name"
ZONE="your-zone"

echo "Setting up maintenance exclusions for ${CLUSTER_NAME}..."

# 1. June code freeze
gcloud container clusters update ${CLUSTER_NAME} \
  --zone ${ZONE} \
  --add-maintenance-exclusion-name "june-code-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# 2. BFCM freeze
gcloud container clusters update ${CLUSTER_NAME} \
  --zone ${ZONE} \
  --add-maintenance-exclusion-name "bfcm-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-05T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# 3. Permanent minor upgrade control
gcloud container clusters update ${CLUSTER_NAME} \
  --zone ${ZONE} \
  --add-maintenance-exclusion-name "no-minor-upgrades-permanent" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

echo "Maintenance exclusions configured successfully!"
```

## Verification

Check your exclusions are active:

```bash
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="yaml(maintenancePolicy.window.maintenanceExclusions)"
```

## Important Notes

- **30-day limit for "no upgrades"**: The June and BFCM exclusions can each be max 30 days. If you need longer periods, create overlapping exclusions.
- **Security patches still apply**: With the permanent `no_minor_or_node_upgrades` exclusion, your control plane will still get security patches - you're not sacrificing security for control.
- **When you want to upgrade**: Remove the permanent exclusion temporarily, perform your controlled upgrade, then re-add it.
- **End of Support enforcement**: Even with exclusions, GKE will eventually force-upgrade versions that reach End of Support. The permanent exclusion delays this until the extended support period ends.

This configuration gives you complete control over upgrade timing while maintaining security through automated patching.
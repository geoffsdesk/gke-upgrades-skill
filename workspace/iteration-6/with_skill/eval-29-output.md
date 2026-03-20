# GKE Maintenance Exclusions Configuration

Based on your requirements, you need two types of exclusions: periodic "no upgrades" exclusions for your critical periods, and a permanent "no minor or node upgrades" exclusion for version control.

## Configuration Commands

Replace `CLUSTER_NAME` and `ZONE` with your actual values for each cluster.

### 1. Quarterly Code Freeze (June) - "No Upgrades"

```bash
# June code freeze - blocks ALL upgrades for 30 days
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

### 2. Black Friday/Cyber Monday (November) - "No Upgrades"

```bash
# BFCM period - blocks ALL upgrades for 30 days  
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "bfcm-2024" \
  --add-maintenance-exclusion-start-time "2024-11-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-11-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

### 3. Permanent Minor Version Control - "No Minor or Node Upgrades"

```bash
# Permanent exclusion - allows control plane patches, blocks minor + node upgrades
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "no-minor-upgrades-permanent" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2029-12-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

## Maintenance Exclusion Types Explained

| Exclusion Type | What it blocks | Duration | Your use case |
|---------------|---------------|----------|---------------|
| **"no_upgrades"** | ALL upgrades (patches, minor, nodes) | 30 days max | June freeze, BFCM |
| **"no_minor_or_node_upgrades"** | Minor + node upgrades, allows CP patches | Up to version EoS | Permanent version control |

## Annual Renewal Process

Each December, you'll need to renew next year's exclusions:

```bash
# Remove expired exclusions
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion "june-code-freeze-2024" \
  --remove-maintenance-exclusion "bfcm-2024"

# Add next year's exclusions
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-2025" \
  --add-maintenance-exclusion-start-time "2025-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "bfcm-2025" \
  --add-maintenance-exclusion-start-time "2025-11-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-11-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## Verification

Check your exclusions are active:

```bash
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(maintenancePolicy.window.maintenanceExclusions[].name, maintenancePolicy.window.maintenanceExclusions[].exclusionOptions.scope)"
```

## How This Setup Works

1. **June & November**: Complete upgrade freeze during critical periods
2. **Rest of year**: Control plane gets security patches automatically, but you control when minor versions and node upgrades happen
3. **Manual upgrades**: You can still upgrade manually anytime with `gcloud container clusters upgrade` - exclusions only affect auto-upgrades

## Important Notes

- **Security patches**: With "no_minor_or_node_upgrades", your control plane still gets critical security patches
- **End of Support**: When your current version reaches EoS, you can either manually upgrade before the deadline or temporarily add a "no_upgrades" exclusion (max 30 days) to defer the forced upgrade
- **Multiple clusters**: Run these commands for each cluster in your fleet
- **Release channels**: This setup works with any release channel (Regular, Stable, Extended recommended for production)

This configuration gives you maximum control - no surprise minor version changes, but security patches still flow automatically during safe periods.
# GKE Maintenance Exclusion Configuration

Based on your requirements, you need two different exclusion types: **event-based exclusions** for your scheduled freezes and a **persistent exclusion** for minor version control.

## 1. Persistent Minor Version Control

For blocking all minor version upgrades while allowing security patches:

```bash
# Apply to each cluster - this exclusion persists and auto-renews at EoS
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "no-minor-upgrades-policy" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Why "no_minor_or_node_upgrades":** This prevents both control plane minor upgrades AND node pool upgrades, ensuring you have complete control over disruptive changes while still receiving control plane security patches.

## 2. Quarterly Code Freeze (June)

```bash
# June code freeze - blocks ALL upgrades for 30 days
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "june-code-freeze" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## 3. Black Friday/Cyber Monday Freeze (November)

```bash
# BFCM freeze - blocks ALL upgrades
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze" \
  --add-maintenance-exclusion-start-time "2024-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-15T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## Complete Setup Script

```bash
#!/bin/bash
# Set your cluster details
CLUSTER_NAME="your-cluster-name"
ZONE="your-zone"

echo "Setting up maintenance exclusions for ${CLUSTER_NAME}..."

# 1. Persistent minor version control
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "no-minor-upgrades-policy" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# 2. June code freeze
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# 3. BFCM freeze
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-15T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

echo "Maintenance exclusions configured successfully!"
```

## What This Configuration Does

| Exclusion | What it blocks | Duration | Renews automatically |
|-----------|----------------|----------|---------------------|
| **no-minor-upgrades-policy** | Minor version upgrades + node upgrades | Until version EoS | ✅ Yes - tracks EoS |
| **june-code-freeze** | ALL upgrades (patches, minor, nodes) | 30 days | ❌ No - manual yearly |
| **bfcm-freeze** | ALL upgrades (patches, minor, nodes) | 30 days | ❌ No - manual yearly |

## Annual Maintenance Required

**For quarterly/BFCM exclusions**, you'll need to update the dates each year:

```bash
# Remove old exclusions
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "june-code-freeze-2024"

# Add new ones with updated dates
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-2025" \
  --add-maintenance-exclusion-start-time "2025-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## How to Manually Upgrade When Ready

Since minor upgrades are blocked, when you want to upgrade:

```bash
# Trigger manual upgrade (bypasses ALL exclusions)
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

## Verification

Check your exclusions are active:
```bash
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(maintenancePolicy.window.maintenanceExclusions)"
```

## Important Notes

- **Security patches flow automatically** - the persistent exclusion only blocks minor/node upgrades, not control plane patches
- **"no_upgrades" exclusions have a 30-day maximum** - this is a hard GKE limit
- **Manual upgrades bypass ALL exclusions** - you maintain full control when ready
- **EoS enforcement is honored** even during "no_upgrades" exclusions (but delayed until the exclusion ends)
- **Maximum 3 "no_upgrades" exclusions per cluster** - plan your freeze periods accordingly

This configuration gives you complete control over disruptive upgrades while maintaining security patch flow during normal operations.
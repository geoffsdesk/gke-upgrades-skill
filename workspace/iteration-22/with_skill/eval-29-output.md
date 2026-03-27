# GKE Maintenance Exclusion Configuration

Based on your requirements, here's the exact configuration for your three scenarios:

## 1. Quarterly Code Freeze (June)

Use a **"no upgrades"** exclusion that blocks ALL upgrades during your code freeze:

```bash
# June code freeze (example: June 1-30, 2025)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-2025" \
  --add-maintenance-exclusion-start-time "2025-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

**Important:** "No upgrades" exclusions are limited to 30 days maximum. For longer freezes, you'll need to chain multiple exclusions (up to 3 per cluster).

## 2. Black Friday/Cyber Monday (November)

Same "no upgrades" configuration for your peak traffic period:

```bash
# BFCM freeze (example: November 20 - December 5, 2025)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze-2025" \
  --add-maintenance-exclusion-start-time "2025-11-20T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-12-05T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## 3. Block Minor Version Auto-Upgrades (Permanent Control)

Use a **"no minor or node upgrades"** exclusion that persists until end of support:

```bash
# Permanent minor version control - allows CP patches, blocks minor + node auto-upgrades
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "no-minor-upgrades-permanent" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## Why This Configuration Works

| Exclusion Type | What It Blocks | What It Allows | Duration | Use Case |
|---------------|---------------|---------------|----------|----------|
| **"no_upgrades"** | Everything (patches, minor, nodes) | Nothing | 30 days max | Code freezes, BFCM |
| **"no_minor_or_node_upgrades"** | Minor versions + node upgrades | Control plane patches | Until EoS | Permanent minor control |

## Key Benefits of This Approach

✅ **Security patches still flow** during normal operations (control plane gets patches)  
✅ **Complete freeze** during critical periods (June, BFCM)  
✅ **Manual control** over minor version timing  
✅ **No version drift** between control plane and nodes (both blocked together)  
✅ **Persistent exclusion** auto-renews when you manually upgrade to new minor versions  

## Operational Workflow

### During Normal Operations
- Control plane gets security patches automatically
- Minor versions blocked - you choose when to upgrade
- When ready for minor upgrade: manually trigger it (exclusion stays in place for future minor versions)

### During Code Freeze Periods  
- Everything blocked (even security patches)
- Resume normal operations after exclusion expires

### Manual Minor Upgrades
When you're ready to upgrade to a new minor version:

```bash
# Manual upgrade bypasses ALL maintenance controls
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION

# The "no minor or node upgrades" exclusion stays active for the next minor version
```

## Verify Your Configuration

```bash
# Check current exclusions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="yaml(maintenancePolicy)"

# Check auto-upgrade target (should be patch-only with minor exclusion)
gcloud container clusters get-upgrade-info CLUSTER_NAME \
  --region REGION
```

## Important Limitations

- **30-day limit** on "no upgrades" - plan June/BFCM exclusions carefully
- **Maximum 3 exclusions** per cluster at any time
- **48 hours minimum** maintenance availability required in any 32-day rolling window
- **Manual upgrades bypass ALL exclusions** - this is how you maintain control

This configuration gives you maximum control while maintaining security posture through control plane patches during normal operations.
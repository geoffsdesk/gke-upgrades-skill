# GKE Maintenance Exclusion Configuration

Based on your requirements, you need two different exclusion strategies: time-based exclusions for your freeze periods and a persistent exclusion for minor version control.

## 1. Persistent Minor Version Control (Recommended)

For **never allowing minor version upgrades without explicit approval**, use a persistent exclusion that automatically tracks End of Support dates:

```bash
# Apply to each cluster - allows CP patches but blocks minor + node upgrades
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "no-minor-upgrades" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**What this does:**
- **Allows:** Control plane security patches (automatic)
- **Blocks:** Minor version upgrades AND node pool upgrades (both require your manual approval)
- **Duration:** Automatically extends until your current version reaches End of Support
- **Benefits:** Prevents control plane/node version skew, maximum upgrade control

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

## 3. Black Friday/Cyber Monday Period (November)

```bash
# BFCM freeze - blocks ALL upgrades for 30 days  
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze" \
  --add-maintenance-exclusion-start-time "2024-11-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-11-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## Complete Configuration Template

Here's the complete setup for each cluster:

```bash
#!/bin/bash
# Set your cluster details
CLUSTER_NAME="your-cluster-name"
ZONE="your-zone"  # or --region for regional clusters

# 1. Persistent minor version control (apply once, auto-renews)
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "no-minor-upgrades" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# 2. June code freeze (renew annually)
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# 3. BFCM freeze (renew annually) 
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-11-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-11-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## Important Notes

### Exclusion Limits
- **Maximum 3 "no upgrades" exclusions per cluster**
- **30-day maximum per "no upgrades" exclusion**
- Within any 32-day window, at least 48 hours must be available for maintenance

### Manual Upgrade Process
With these exclusions in place, when you want to do minor upgrades:

```bash
# Manual control plane upgrade (bypasses ALL exclusions)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION

# Manual node pool upgrade (bypasses ALL exclusions)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

**Key insight:** Manual upgrades bypass ALL maintenance exclusions, so you don't need to remove and re-add exclusions when upgrading.

### Annual Maintenance

Each year, update the time-based exclusions:

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

### Verification

Check your current exclusions:

```bash
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="yaml(resourceLabels,maintenancePolicy)"
```

This configuration gives you:
- ✅ **Security patches applied automatically** (except during freeze periods)
- ✅ **Complete control over minor version timing**
- ✅ **Guaranteed freeze periods for June and November**
- ✅ **No unexpected disruptive upgrades**
# GKE Maintenance Exclusion Configuration

Based on your requirements, you need **two different exclusion types** with different scopes and durations. Here's the exact configuration:

## 1. Persistent "No Minor Version" Control

For **never allowing minor version upgrades without approval**, use a persistent exclusion that tracks End of Support:

```bash
# Apply to each cluster - this exclusion auto-renews as versions change
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "no-minor-upgrades-policy" \
  --add-maintenance-exclusion-scope "no_minor_upgrades" \
  --add-maintenance-exclusion-until-end-of-support
```

**What this does:**
- Blocks minor version upgrades (e.g., 1.29 → 1.30)
- Allows patch upgrades (e.g., 1.29.1 → 1.29.2) for security
- Allows node pool upgrades within the same minor version
- Automatically extends until the current version reaches End of Support
- **No manual renewal needed** - tracks EoS dates automatically

## 2. Temporary "No Upgrades" for Business Critical Periods

For **quarterly code freezes and BFCM**, use time-bound exclusions that block ALL upgrades:

### June Code Freeze (example dates)
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope "no_upgrades"
```

### Black Friday/Cyber Monday (example dates)
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-05T23:59:59Z" \
  --add-maintenance-exclusion-scope "no_upgrades"
```

**What these do:**
- Block ALL upgrades (patches, minor versions, node pools)
- Maximum 30 days per exclusion (chain multiple if needed for longer periods)
- Honored even after End of Support (emergency protection)

## 3. Verification Commands

Check your exclusions are active:
```bash
# List all maintenance exclusions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="yaml(maintenancePolicy.window.maintenanceExclusions)"

# Check auto-upgrade status and targets
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION
```

## 4. Complete Setup Script

Here's a complete script for one cluster (repeat for each):

```bash
#!/bin/bash
CLUSTER_NAME="your-cluster-name"
ZONE="us-central1-a"

echo "Setting up maintenance exclusions for $CLUSTER_NAME..."

# Persistent minor version control
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "no-minor-upgrades-policy" \
  --add-maintenance-exclusion-scope "no_minor_upgrades" \
  --add-maintenance-exclusion-until-end-of-support

# June 2024 code freeze
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope "no_upgrades"

# BFCM 2024 freeze  
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-05T23:59:59Z" \
  --add-maintenance-exclusion-scope "no_upgrades"

echo "Exclusions configured. Verifying..."
gcloud container clusters describe $CLUSTER_NAME \
  --zone $ZONE \
  --format="yaml(maintenancePolicy.window.maintenanceExclusions)"
```

## 5. Ongoing Management

**For next year's exclusions:**
- The "no-minor-upgrades-policy" exclusion continues automatically
- Add new "no_upgrades" exclusions for 2025 dates in advance
- 30-day maximum means BFCM needs chaining if longer than November 15 - December 5

**When you DO want minor upgrades:**
- Remove the persistent exclusion temporarily
- Perform the upgrade manually
- Re-add the exclusion to maintain control

This configuration gives you complete control over minor versions while still receiving critical security patches, plus bulletproof protection during your business-critical periods.
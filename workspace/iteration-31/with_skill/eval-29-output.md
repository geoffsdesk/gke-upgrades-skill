# GKE Maintenance Exclusions Configuration

Based on your requirements, here's the exact configuration for your three scenarios:

## 1. Quarterly Code Freeze (June) - "No upgrades" exclusion

This blocks ALL upgrades (patches, minor versions, and node upgrades) during your code freeze:

```bash
# June code freeze - blocks everything for up to 30 days
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "june-code-freeze" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

**Note:** The "no upgrades" exclusion has a 30-day maximum per exclusion. For a full month, you may need to chain two exclusions if June has 31 days or if you need buffer time.

## 2. Black Friday/Cyber Monday (November) - "No upgrades" exclusion

```bash
# BFCM freeze - blocks everything during peak traffic
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze" \
  --add-maintenance-exclusion-start-time "2024-11-20T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-05T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## 3. Manual Minor Version Control - "No minor or node upgrades" exclusion (Recommended)

This allows control plane security patches but prevents minor version upgrades and node upgrades without your approval:

```bash
# Persistent minor version control - tracks End of Support automatically
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "manual-minor-control" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## Complete Setup Script

Here's a script to configure all three exclusions:

```bash
#!/bin/bash

CLUSTER_NAME="your-cluster-name"
ZONE="us-central1-a"  # Replace with your zone
YEAR="2024"  # Update annually

echo "Configuring maintenance exclusions for cluster: $CLUSTER_NAME"

# 1. Persistent minor version control (no expiration - tracks EoS)
echo "Setting up persistent minor version control..."
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "manual-minor-control" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# 2. June code freeze (30-day max)
echo "Setting up June code freeze..."
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-$YEAR" \
  --add-maintenance-exclusion-start-time "${YEAR}-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "${YEAR}-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# 3. BFCM freeze
echo "Setting up BFCM freeze..."
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze-$YEAR" \
  --add-maintenance-exclusion-start-time "${YEAR}-11-20T00:00:00Z" \
  --add-maintenance-exclusion-end-time "${YEAR}-12-05T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

echo "Exclusions configured successfully!"

# Verify configuration
echo "Current maintenance exclusions:"
gcloud container clusters describe $CLUSTER_NAME \
  --zone $ZONE \
  --format="table(maintenancePolicy.window.maintenanceExclusions[].name,
                   maintenancePolicy.window.maintenanceExclusions[].startTime,
                   maintenancePolicy.window.maintenanceExclusions[].endTime,
                   maintenancePolicy.window.maintenanceExclusions[].exclusionOptions.scope)"
```

## How This Configuration Works

### Persistent Minor Control
- **Allows:** Control plane security patches (essential for security)
- **Blocks:** Minor version upgrades and node pool upgrades
- **Duration:** Automatically tracks the version's End of Support date
- **Result:** You get security patches but control when disruptive changes happen

### Seasonal Freezes (June, BFCM)
- **Blocks:** ALL upgrades including patches
- **Duration:** Fixed date ranges
- **Tradeoff:** Maximum stability during critical periods, but accumulates security debt

### When You Want Minor Upgrades
When ready for a minor version upgrade:
```bash
# The exclusion stays in place - just trigger the upgrade manually
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION

# Then upgrade node pools when ready
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

**Manual upgrades bypass ALL maintenance controls** - the exclusions remain active to continue blocking auto-upgrades.

## Important Constraints

1. **Maximum 3 exclusions per cluster** - you're using all 3 slots
2. **48-hour maintenance window requirement** - within any 32-day period, at least 48 hours must be available for maintenance
3. **Security patch accumulation** - during "no upgrades" periods, you'll miss security patches and need to catch up afterward

## Annual Maintenance

Update the date-based exclusions annually:
```bash
# Remove old exclusions
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion "june-code-freeze-2024"

# Add new ones with updated dates
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-2025" \
  --add-maintenance-exclusion-start-time "2025-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

This configuration gives you maximum control over disruptive changes while maintaining security patches during normal periods.
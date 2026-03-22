# GKE Maintenance Exclusions Configuration

Based on your requirements, here's the exact configuration for your three scenarios:

## 1. Persistent "No Minor or Node Upgrades" Exclusion (Always Active)

This prevents all minor version upgrades and node pool upgrades while still allowing control plane security patches. This is your primary control mechanism.

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "no-minor-upgrades-policy" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Key points:**
- This exclusion automatically tracks your cluster's End of Support date and renews when you adopt a new minor version
- Allows control plane patches for security (recommended)
- Blocks all disruptive changes (minor versions + node upgrades)
- Apply this to ALL your clusters as your baseline policy

## 2. Quarterly Code Freeze (June - 30 days max)

During your June code freeze, block ALL upgrades including patches:

```bash
# June 2024 example - adjust dates for your specific freeze period
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## 3. Black Friday/Cyber Monday (November)

Block all upgrades during your peak traffic period:

```bash
# BFCM 2024 example - adjust dates for your specific period
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "bfcm-2024" \
  --add-maintenance-exclusion-start-time "2024-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-05T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## Maintenance Window Configuration

Set predictable maintenance windows for when upgrades ARE allowed:

```bash
# Example: Saturday 2-6 AM EST maintenance window
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T07:00:00Z" \
  --maintenance-window-end "2024-01-06T11:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## Complete Setup Script

Here's a complete script for one cluster:

```bash
#!/bin/bash
CLUSTER_NAME="your-cluster-name"
ZONE="your-zone"

# 1. Set up persistent "no minor or node upgrades" policy
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "no-minor-upgrades-policy" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# 2. Set up June 2024 code freeze
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# 3. Set up BFCM 2024
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "bfcm-2024" \
  --add-maintenance-exclusion-start-time "2024-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-05T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# 4. Set maintenance window (Saturday 2-6 AM EST)
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --maintenance-window-start "2024-01-06T07:00:00Z" \
  --maintenance-window-end "2024-01-06T11:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

echo "Maintenance exclusions configured for $CLUSTER_NAME"
```

## Verify Configuration

Check your exclusions are active:

```bash
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(maintenancePolicy.window,maintenancePolicy.exclusions)"
```

## Annual Maintenance Tasks

**For June code freeze:** Recreate the "no_upgrades" exclusion each year with updated dates.

**For BFCM:** Recreate the "no_upgrades" exclusion each year with updated dates.

**For persistent policy:** No action needed - the "until end of support" flag automatically renews.

## Important Notes

1. **"No minor or node upgrades" is your primary control** - this gives you full control over disruptive changes while still getting security patches
2. **"No upgrades" is for special periods** - use sparingly as it blocks security patches
3. **30-day maximum** for "no_upgrades" exclusions - plan your freeze periods accordingly
4. **Multiple exclusions can overlap** - the most restrictive one wins
5. **Apply to all clusters** in your fleet for consistent behavior

This configuration ensures you'll never get surprise minor version upgrades while still maintaining security through control plane patches during normal operations.
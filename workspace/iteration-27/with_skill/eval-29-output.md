Based on your requirements, you need a combination of time-based exclusions for specific periods and a persistent exclusion for minor version control. Here's the exact configuration:

## Persistent Minor Version Control

For preventing minor version auto-upgrades while allowing security patches:

```bash
# Apply to each cluster - this stays active until end of support for each version
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "no-minor-upgrades-policy" \
  --add-maintenance-exclusion-scope no_minor_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**What this does:** Blocks minor version auto-upgrades permanently, but still allows:
- Control plane security patches (automatic)
- Node pool security patches (automatic) 
- You can manually trigger minor upgrades when ready

## Quarterly Code Freeze (June)

```bash
# Configure each year - example for June 2024
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "q2-code-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## Black Friday/Cyber Monday Freeze

```bash
# Configure each year - example for November 2024
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-05T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## Recommended Maintenance Window

Set a predictable maintenance window during off-peak hours:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T03:00:00Z" \
  --maintenance-window-end "2024-01-06T07:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**This creates:** Saturday 3-7 AM UTC maintenance windows.

## Complete Configuration Script

Here's a script to apply all settings to your clusters:

```bash
#!/bin/bash

CLUSTERS=("prod-cluster" "staging-cluster")  # Replace with your cluster names
ZONES=("us-central1-a" "us-west1-b")        # Replace with your zones

for i in "${!CLUSTERS[@]}"; do
  CLUSTER="${CLUSTERS[$i]}"
  ZONE="${ZONES[$i]}"
  
  echo "Configuring $CLUSTER in $ZONE..."
  
  # Persistent minor version control
  gcloud container clusters update "$CLUSTER" \
    --zone "$ZONE" \
    --add-maintenance-exclusion-name "no-minor-upgrades-policy" \
    --add-maintenance-exclusion-scope no_minor_upgrades \
    --add-maintenance-exclusion-until-end-of-support
  
  # Maintenance window (Saturday 3-7 AM UTC)
  gcloud container clusters update "$CLUSTER" \
    --zone "$ZONE" \
    --maintenance-window-start "2024-01-06T03:00:00Z" \
    --maintenance-window-end "2024-01-06T07:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
  
  # June code freeze (update year as needed)
  gcloud container clusters update "$CLUSTER" \
    --zone "$ZONE" \
    --add-maintenance-exclusion-name "q2-code-freeze-2024" \
    --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
  
  # BFCM freeze (update year as needed)
  gcloud container clusters update "$CLUSTER" \
    --zone "$ZONE" \
    --add-maintenance-exclusion-name "bfcm-freeze-2024" \
    --add-maintenance-exclusion-start-time "2024-11-15T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-12-05T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
  
  echo "✓ $CLUSTER configured"
done
```

## Operational Workflow

With this setup:

1. **Normal operation:** Only security patches auto-apply during Saturday maintenance windows
2. **When you want a minor upgrade:**
   ```bash
   # Manually trigger when ready
   gcloud container clusters upgrade CLUSTER_NAME \
     --zone ZONE \
     --cluster-version TARGET_VERSION
   ```
3. **Annual maintenance:** Update the June and BFCM exclusion dates each year

## Verification Commands

```bash
# Check current exclusions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="yaml(maintenancePolicy.window,maintenancePolicy.resourceVersion)"

# Check auto-upgrade status
gcloud container clusters get-upgrade-info CLUSTER_NAME --zone ZONE
```

**Important notes:**
- `no_upgrades` exclusions are limited to 30 days max - your BFCM period (20 days) fits within this limit
- The persistent `no_minor_upgrades` exclusion automatically renews when you get new minor versions
- Manual upgrades bypass ALL exclusions - you can still upgrade during freeze periods if needed
- Security patches will continue during freeze periods with the persistent exclusion, but not with `no_upgrades` exclusions

This configuration gives you complete control over minor versions while maintaining security through automatic patching.
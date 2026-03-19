# GKE Maintenance Exclusion Configuration

Based on your requirements, here's the exact configuration for your three scenarios:

## 1. Quarterly Code Freeze (June) - "No upgrades" exclusion

This blocks ALL upgrades including patches - use this for your code freeze:

```bash
# June code freeze (example: June 1-30, 2024)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

**Note:** This exclusion type has a 30-day maximum duration and blocks everything including security patches. For longer freezes, you'll need to chain multiple exclusions.

## 2. Black Friday/Cyber Monday (November) - "No upgrades" exclusion

Similar to code freeze - complete stability during your busiest period:

```bash
# BFCM protection (example: November 15 - December 5, 2024)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-05T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

**Note:** This is 20 days, well within the 30-day limit. Adjust dates based on your specific high-traffic period.

## 3. No Minor Version Auto-Upgrades (Year-round) - "No minor or node upgrades" exclusion

This gives you maximum control - allows security patches on control plane but blocks disruptive changes:

```bash
# Block minor version auto-upgrades (can run until version EoS)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "no-minor-upgrades-permanent" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-12-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

**This is the recommended approach** because:
- Control plane still gets security patches
- Prevents disruptive minor version and node pool upgrades
- Can be extended up to the version's End of Support date
- You manually control when minor upgrades happen

## Applying to Multiple Clusters

Create a script to apply across your fleet:

```bash
#!/bin/bash
CLUSTERS=("cluster-1" "cluster-2" "cluster-3")
ZONES=("us-central1-a" "us-west1-b" "us-east1-c")

for i in "${!CLUSTERS[@]}"; do
  CLUSTER="${CLUSTERS[$i]}"
  ZONE="${ZONES[$i]}"
  
  echo "Configuring maintenance exclusions for $CLUSTER in $ZONE..."
  
  # Year-round minor upgrade protection
  gcloud container clusters update "$CLUSTER" \
    --zone "$ZONE" \
    --add-maintenance-exclusion-name "no-minor-upgrades-2024" \
    --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-12-31T23:59:59Z" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades
  
  # June code freeze
  gcloud container clusters update "$CLUSTER" \
    --zone "$ZONE" \
    --add-maintenance-exclusion-name "june-code-freeze-2024" \
    --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
  
  # BFCM freeze
  gcloud container clusters update "$CLUSTER" \
    --zone "$ZONE" \
    --add-maintenance-exclusion-name "bfcm-freeze-2024" \
    --add-maintenance-exclusion-start-time "2024-11-15T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-12-05T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
done
```

## Verification Commands

Check your exclusions are active:

```bash
# View all maintenance exclusions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(maintenancePolicy.window.maintenanceExclusions[].name,maintenancePolicy.window.maintenanceExclusions[].startTime,maintenancePolicy.window.maintenanceExclusions[].endTime,maintenancePolicy.window.maintenanceExclusions[].scope)"

# Check cluster's current auto-upgrade status
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(autopilot,releaseChannel,currentMasterVersion)"
```

## Managing Exclusions Going Forward

**Removing expired exclusions:**
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "june-code-freeze-2024"
```

**Annual renewal of the year-round exclusion:**
```bash
# Extend for 2025
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "no-minor-upgrades-2025" \
  --add-maintenance-exclusion-start-time "2025-01-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-12-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Remove the old 2024 exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "no-minor-upgrades-2024"
```

## Important Notes

1. **Exclusion hierarchy:** During June and November, the "no_upgrades" exclusions take precedence and block everything, including patches
2. **Manual upgrades:** You can still manually upgrade anytime using `gcloud container clusters upgrade` - exclusions only affect auto-upgrades
3. **End of Support:** The "no_upgrades" exclusion is honored even after a version reaches EoS, giving you 30 days past EoS if needed
4. **Security patches:** Outside of your freeze periods, control plane will still receive security patches thanks to the "no_minor_or_node_upgrades" exclusion

This configuration gives you complete control over when disruptive changes happen while maintaining security during normal operations.
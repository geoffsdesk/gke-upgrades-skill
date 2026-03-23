# GKE Maintenance Exclusion Configuration

Based on your requirements, here's the exact configuration for your three scenarios:

## 1. Persistent "No Minor Upgrades" (Year-round Control)

This prevents ALL minor version upgrades while allowing security patches and node upgrades:

```bash
# Apply to each cluster - this exclusion automatically tracks EoS and renews
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "no-minor-upgrades-policy" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_minor_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Key benefit:** This exclusion automatically renews when you eventually do upgrade to a new minor version - no need to recreate it.

## 2. Quarterly Code Freeze (June - 30 days max)

Complete upgrade freeze during your June code freeze:

```bash
# Apply in early June each year
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## 3. Black Friday/Cyber Monday Protection (November)

Complete upgrade freeze during your busiest period:

```bash
# Apply each year for BFCM period
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-15T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## Configuration Script for Multiple Clusters

```bash
#!/bin/bash

CLUSTERS=(
  "prod-cluster-1:us-central1-a"
  "prod-cluster-2:us-east1-b" 
  "staging-cluster:us-central1-a"
)

echo "Setting up maintenance exclusions for all clusters..."

for cluster_config in "${CLUSTERS[@]}"; do
  IFS=':' read -r cluster zone <<< "$cluster_config"
  
  echo "Configuring cluster: $cluster in zone: $zone"
  
  # 1. Persistent no minor upgrades
  gcloud container clusters update "$cluster" \
    --zone "$zone" \
    --add-maintenance-exclusion-name "no-minor-upgrades-policy" \
    --add-maintenance-exclusion-start-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --add-maintenance-exclusion-scope no_minor_upgrades \
    --add-maintenance-exclusion-until-end-of-support
  
  # 2. June code freeze 2024
  gcloud container clusters update "$cluster" \
    --zone "$zone" \
    --add-maintenance-exclusion-name "june-code-freeze-2024" \
    --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
  
  # 3. BFCM freeze 2024
  gcloud container clusters update "$cluster" \
    --zone "$zone" \
    --add-maintenance-exclusion-name "bfcm-freeze-2024" \
    --add-maintenance-exclusion-start-time "2024-11-15T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-12-15T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades

done

echo "All maintenance exclusions configured!"
```

## Verify Your Configuration

Check that exclusions are active:

```bash
# List all exclusions for a cluster
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="yaml(maintenancePolicy.window.maintenanceExclusions)"

# Check auto-upgrade status
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION
```

## Important Notes

**Exclusion Hierarchy:** When multiple exclusions are active, the most restrictive applies:
- During June & November: `no_upgrades` (blocks everything)  
- Rest of year: `no_minor_upgrades` (allows patches & node upgrades)

**Annual Renewal:** You'll need to recreate the June and BFCM exclusions each year (30-day limit), but the `no_minor_upgrades` exclusion persists automatically.

**Security Patches:** Your configuration allows security patches year-round except during June and November freezes - this is the recommended balance of control and security.

**When You Want Minor Upgrades:** Remove the persistent exclusion temporarily, perform your controlled upgrade, then re-add it:

```bash
# Remove for controlled upgrade
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "no-minor-upgrades-policy"

# After upgrade, re-add
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "no-minor-upgrades-policy" \
  --add-maintenance-exclusion-start-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-scope no_minor_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

This configuration gives you complete control over minor version timing while maintaining security through automated patching outside of critical business periods.
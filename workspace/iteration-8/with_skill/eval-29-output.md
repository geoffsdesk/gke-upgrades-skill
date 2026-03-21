# GKE Maintenance Exclusions Configuration

Based on your requirements, here's the exact configuration for your three scenarios:

## 1. Persistent Control: Block Minor & Node Upgrades (Year-round)

This is your primary control mechanism - blocks disruptive upgrades while allowing security patches on the control plane:

```bash
# Apply to each cluster - this exclusion automatically tracks EoS and renews
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "no-minor-or-node-upgrades-persistent" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**What this does:**
- Blocks ALL minor version upgrades on control plane and nodes
- Blocks ALL node pool upgrades (even same-version node replacements)
- Allows control plane security patches
- Automatically renews when cluster adopts new minor versions
- No 6-month limit - tracks End of Support indefinitely

## 2. Quarterly Code Freeze (June)

30-day complete freeze during your quarterly code freeze:

```bash
# Apply in late May for June code freeze
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "q2-code-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## 3. Black Friday/Cyber Monday (November)

30-day complete freeze during your peak traffic period:

```bash
# Apply in late October
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-11-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-11-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## Configuration Script Template

Here's a complete script to apply all exclusions across your fleet:

```bash
#!/bin/bash

# Configuration
CLUSTERS=(
  "cluster-1:us-central1-a"
  "cluster-2:us-east1-b"
  "cluster-3:europe-west1-c"
  # Add your clusters in format "name:zone"
)

CURRENT_YEAR=$(date +%Y)
NEXT_YEAR=$((CURRENT_YEAR + 1))

for cluster_zone in "${CLUSTERS[@]}"; do
  IFS=':' read -r cluster zone <<< "$cluster_zone"
  
  echo "Configuring exclusions for $cluster in $zone..."
  
  # 1. Persistent minor/node upgrade control
  gcloud container clusters update "$cluster" \
    --zone "$zone" \
    --add-maintenance-exclusion-name "no-minor-or-node-upgrades-persistent" \
    --add-maintenance-exclusion-start-time "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
  
  # 2. Q2 Code Freeze (June)
  gcloud container clusters update "$cluster" \
    --zone "$zone" \
    --add-maintenance-exclusion-name "q2-code-freeze-$CURRENT_YEAR" \
    --add-maintenance-exclusion-start-time "${CURRENT_YEAR}-06-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "${CURRENT_YEAR}-06-30T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
  
  # 3. BFCM Freeze (November)
  gcloud container clusters update "$cluster" \
    --zone "$zone" \
    --add-maintenance-exclusion-name "bfcm-freeze-$CURRENT_YEAR" \
    --add-maintenance-exclusion-start-time "${CURRENT_YEAR}-11-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "${CURRENT_YEAR}-11-30T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
  
  echo "✓ Configured exclusions for $cluster"
  echo
done

echo "All clusters configured with maintenance exclusions"
```

## Verify Configuration

Check your exclusions are properly set:

```bash
# List all maintenance exclusions for a cluster
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(maintenancePolicy.window.maintenanceExclusions[].name,
                   maintenancePolicy.window.maintenanceExclusions[].startTime,
                   maintenancePolicy.window.maintenanceExclusions[].endTime,
                   maintenancePolicy.window.maintenanceExclusions[].exclusionOptions.scope)"
```

## Key Points

**Exclusion Precedence:** The `no_upgrades` exclusions (June/November) override the `no_minor_or_node_upgrades` exclusion during those periods. So you get:
- **January-May, July-October, December:** Only control plane patches allowed
- **June & November:** Complete freeze (no upgrades at all)

**When You Want to Upgrade:** When you're ready for a minor version upgrade:
1. Temporarily remove the persistent exclusion
2. Perform the upgrade manually or wait for auto-upgrade
3. Re-apply the persistent exclusion for the new version

**Annual Renewal:** You'll need to add new June/November exclusions each year. The persistent exclusion automatically renews.

**Emergency Override:** Even with `no_upgrades` exclusions, you can still perform manual upgrades if needed for security patches - the exclusions only block auto-upgrades.

This configuration gives you complete control over when upgrades happen while maintaining security through control plane patches year-round.
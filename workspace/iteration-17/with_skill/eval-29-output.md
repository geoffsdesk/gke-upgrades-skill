# GKE Maintenance Exclusions Configuration

Based on your requirements, here's the exact configuration for your three scenarios:

## 1. Persistent "No Minor or Node Upgrades" Exclusion (Year-round Control)

This blocks all minor version upgrades and node pool upgrades while still allowing critical security patches on the control plane. **This is your primary control mechanism.**

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "no-minor-upgrades-permanent" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Key benefits:**
- Automatically tracks End of Support dates — no manual renewal needed
- Allows security patches on control plane (critical for compliance)
- Prevents disruptive minor version changes and node pool upgrades
- No 6-month limit — persists until you remove it

## 2. Quarterly Code Freeze (June)

For your June code freeze, add a "no upgrades" exclusion that blocks ALL upgrades including patches:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

**Repeat annually:**
```bash
# For 2025
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-2025" \
  --add-maintenance-exclusion-start-time "2025-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## 3. Black Friday/Cyber Monday (November)

Block all upgrades during your peak traffic period:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-11-20T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-05T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

**Repeat annually:**
```bash
# For 2025
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze-2025" \
  --add-maintenance-exclusion-start-time "2025-11-20T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-12-05T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## Complete Multi-Cluster Setup Script

For applying to multiple clusters, use this script:

```bash
#!/bin/bash

CLUSTERS=(
  "prod-cluster-1:us-central1-a"
  "prod-cluster-2:us-east1-b" 
  "staging-cluster:us-central1-a"
)

for cluster_info in "${CLUSTERS[@]}"; do
  IFS=':' read -r cluster zone <<< "$cluster_info"
  
  echo "Configuring exclusions for $cluster in $zone..."
  
  # Permanent no minor upgrades
  gcloud container clusters update $cluster \
    --zone $zone \
    --add-maintenance-exclusion-name "no-minor-upgrades-permanent" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
  
  # June 2024 code freeze
  gcloud container clusters update $cluster \
    --zone $zone \
    --add-maintenance-exclusion-name "june-code-freeze-2024" \
    --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
  
  # BFCM 2024 freeze
  gcloud container clusters update $cluster \
    --zone $zone \
    --add-maintenance-exclusion-name "bfcm-freeze-2024" \
    --add-maintenance-exclusion-start-time "2024-11-20T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-12-05T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
done
```

## Verification Commands

Check your exclusions are active:

```bash
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="yaml(maintenancePolicy.window.maintenanceExclusions)"
```

## Your Upgrade Workflow

With this configuration:

1. **Normal operation:** Only control plane security patches auto-apply (no minor versions, no node upgrades)
2. **Minor version upgrades:** You initiate manually when ready:
   ```bash
   gcloud container clusters upgrade CLUSTER_NAME --zone ZONE --master --cluster-version TARGET_VERSION
   gcloud container node-pools upgrade NODE_POOL --cluster CLUSTER_NAME --zone ZONE --cluster-version TARGET_VERSION
   ```
3. **During freezes:** No upgrades at all (including patches)
4. **After freezes:** Security patches resume automatically

## Important Notes

- **Maximum 3 "no_upgrades" exclusions per cluster** — you're using 2 (June + BFCM), leaving 1 for emergencies
- **Within any 32-day window, at least 48 hours must be available for maintenance** — your exclusions are spaced out enough to meet this requirement
- **Manual upgrades bypass all exclusions** — if you need emergency patching during a freeze, you can still force it
- **Persistent exclusions automatically renew** when you adopt new minor versions — no manual intervention needed

This gives you complete control over when disruptive changes happen while maintaining security patch compliance.
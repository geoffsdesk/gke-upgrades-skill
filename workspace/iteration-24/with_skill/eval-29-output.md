# GKE Maintenance Exclusion Configuration

Based on your requirements, here's the exact configuration for your three scenarios:

## 1. Quarterly Code Freeze (June) - "No Upgrades" Exclusion

For complete upgrade freeze during June code freeze:

```bash
# June code freeze - blocks ALL upgrades (patches + minor + node)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

**Important:** "No upgrades" exclusions are limited to 30 days maximum. For longer freezes, chain multiple exclusions:

```bash
# If June freeze extends beyond 30 days, add a second exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-2024-part2" \
  --add-maintenance-exclusion-start-time "2024-07-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-07-15T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## 2. Black Friday/Cyber Monday - "No Upgrades" Exclusion

For your busiest period with zero tolerance for disruption:

```bash
# BFCM freeze - complete upgrade freeze for peak traffic
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-11-20T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-05T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## 3. Permanent Minor Version Control - "No Minor or Node Upgrades" Exclusion

For ongoing control over minor version upgrades while still receiving security patches:

```bash
# Permanent minor version control - allows CP security patches, blocks minor + node upgrades
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "minor-version-control" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Key advantage:** The `--add-maintenance-exclusion-until-end-of-support` flag creates a persistent exclusion that automatically tracks your current version's End of Support date and renews when you manually upgrade to a new minor version. No need to manually manage dates or chain exclusions.

## Verification Commands

Check your configured exclusions:

```bash
# List all maintenance exclusions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="yaml(maintenancePolicy)"

# Check auto-upgrade status
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION
```

## Complete Workflow for Your Environment

Here's how these exclusions work together:

1. **Steady state:** Clusters have the permanent "no minor or node upgrades" exclusion active
   - ✅ Control plane security patches auto-apply
   - ❌ Minor version upgrades blocked (require your manual trigger)
   - ❌ Node pool upgrades blocked (require your manual trigger)

2. **Code freeze periods:** Add temporary "no upgrades" exclusions on top
   - ❌ ALL upgrades blocked (including security patches)

3. **Manual upgrade process:** When you're ready for minor upgrades:
   ```bash
   # Upgrade control plane (exclusion automatically allows manual upgrades)
   gcloud container clusters upgrade CLUSTER_NAME \
     --zone ZONE \
     --master \
     --cluster-version TARGET_VERSION
   
   # Upgrade node pools
   gcloud container node-pools upgrade NODE_POOL_NAME \
     --cluster CLUSTER_NAME \
     --zone ZONE \
     --cluster-version TARGET_VERSION
   ```

## Important Notes

- **Manual upgrades bypass ALL exclusions** - you can always upgrade manually even with active exclusions
- **Security patches continue** with the "no minor or node" exclusion - you stay current on security without disruptive minor versions
- **Maximum 3 exclusions per cluster** - plan your freeze periods accordingly
- **EoS protection** - even "no upgrades" exclusions are honored past End of Support (gives you the 30-day window to plan)

## Recommended Release Channel

For maximum control with your workflow, use **Regular** or **Stable** channel:

```bash
# Set to Regular channel for balanced upgrade cadence
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular
```

This configuration gives you complete control over when disruptive changes happen while maintaining security patch currency - exactly what you need for regulated release cycles with critical business periods.
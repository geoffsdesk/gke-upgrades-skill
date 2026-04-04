Based on your requirements, here's the exact maintenance exclusion configuration for your three scenarios:

## Quarterly Code Freeze (June)

For your June code freeze, use a **"no upgrades" exclusion** to block all upgrades (patches, minor versions, and node upgrades):

```bash
# June code freeze (adjust dates for your specific freeze period)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "june-code-freeze" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

**Important:** "No upgrades" exclusions are limited to 30 days maximum per exclusion. If your code freeze is longer than 30 days, you'll need to chain multiple exclusions (up to 3 per cluster):

```bash
# First 30 days
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "june-freeze-part1" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# Additional period if needed (starts immediately after first ends)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "june-freeze-part2" \
  --add-maintenance-exclusion-start-time "2024-07-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-07-15T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## Black Friday/Cyber Monday Protection (November)

For BFCM, use the same "no upgrades" exclusion pattern:

```bash
# BFCM protection (typically mid-November through early December)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze" \
  --add-maintenance-exclusion-start-time "2024-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-15T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

Again, this is longer than 30 days, so you'll need multiple exclusions:

```bash
# BFCM Part 1 (30 days)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze-part1" \
  --add-maintenance-exclusion-start-time "2024-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-14T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# BFCM Part 2 (remaining days)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze-part2" \
  --add-maintenance-exclusion-start-time "2024-12-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## Permanent Minor Version Control

For permanent control over minor version upgrades (while still allowing security patches), use **"no minor or node upgrades"** with the persistent flag:

```bash
# Permanent minor version control - allows control plane patches, blocks minor + node upgrades
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "no-minor-upgrades" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

This exclusion:
- **Allows**: Control plane security patches (critical for security posture)
- **Blocks**: Minor version upgrades AND node pool upgrades
- **Duration**: Automatically tracks End of Support - no need to chain exclusions
- **Prevents version skew**: Keeps control plane and nodes on the same minor version

## Complete Configuration for All Clusters

Apply this to each cluster in your fleet:

```bash
#!/bin/bash

CLUSTERS=("prod-cluster-1" "prod-cluster-2" "staging-cluster")
ZONE="us-central1-a"  # Adjust for your clusters

for CLUSTER in "${CLUSTERS[@]}"; do
  echo "Configuring maintenance exclusions for $CLUSTER..."
  
  # Permanent minor version control
  gcloud container clusters update $CLUSTER \
    --zone $ZONE \
    --add-maintenance-exclusion-name "no-minor-upgrades" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
  
  # June code freeze - Part 1
  gcloud container clusters update $CLUSTER \
    --zone $ZONE \
    --add-maintenance-exclusion-name "june-freeze-part1" \
    --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
  
  # BFCM freeze - Part 1  
  gcloud container clusters update $CLUSTER \
    --zone $ZONE \
    --add-maintenance-exclusion-name "bfcm-freeze-part1" \
    --add-maintenance-exclusion-start-time "2024-11-15T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-12-14T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
    
  echo "✓ Configured exclusions for $CLUSTER"
done
```

## Manual Upgrade Workflow

With these exclusions in place, here's how to handle minor version upgrades on your schedule:

```bash
# 1. Check available versions
gcloud container get-server-config --zone ZONE --format="yaml(channels)"

# 2. Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION

# 3. Upgrade node pools (exclusions don't affect manual upgrades)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

## Important Notes

1. **Manual upgrades bypass ALL exclusions** - you can still upgrade during exclusion periods if needed
2. **Security patches continue** on the control plane with the "no minor or node" exclusion
3. **Chain exclusion limits**: Maximum 3 "no upgrades" exclusions per cluster, with at least 48 hours available for maintenance in any 32-day window
4. **Version drift warning**: Extended "no upgrades" periods accumulate security debt - plan catch-up upgrades after each freeze
5. **Channel recommendation**: Stay on Regular or Stable channel for predictable upgrade timing

This configuration gives you maximum control while maintaining security posture through continued patch application on the control plane.
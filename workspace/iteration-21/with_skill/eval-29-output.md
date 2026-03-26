Based on your requirements, here's the exact configuration for your GKE maintenance exclusions:

## Configuration Strategy

You need a combination of **recurring exclusions** for predictable periods and **persistent exclusions** for ongoing control:

### 1. Persistent "No Minor" Control (Year-round)

This prevents minor version upgrades while still allowing security patches:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "no-minor-upgrades-permanent" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**What this does:**
- Blocks ALL minor version upgrades (requires your manual approval)
- Blocks node pool upgrades (prevents control plane/node version skew)
- Allows control plane security patches (critical for security)
- Automatically tracks End of Support dates - no need to manually renew

### 2. June Code Freeze (30-day exclusion)

Complete freeze during quarterly code freeze:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "june-code-freeze" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

### 3. Black Friday/Cyber Monday Freeze

Complete freeze during peak shopping season:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze" \
  --add-maintenance-exclusion-start-time "2024-11-20T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-05T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## Your Upgrade Workflow

With this configuration:

### Ongoing Operations
- **Security patches flow automatically** to control plane (except during June/BFCM freezes)
- **Minor versions are blocked** - you control when they happen
- **Node pools stay frozen** until you upgrade them manually

### When You Want to Upgrade
```bash
# Check what versions are available
gcloud container get-server-config --zone ZONE

# Upgrade control plane manually (exclusions don't block manual upgrades)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION

# Upgrade node pools manually
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

## Important Notes

⚠️ **"No upgrades" exclusion limits:**
- Maximum 30 days per exclusion
- Maximum 3 exclusions per cluster
- You'll need to create new exclusions each year for June/BFCM

⚠️ **Channel recommendation:**
Consider **Extended channel** for your conservative approach:
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```
Extended channel provides 24 months of support and does NOT auto-upgrade minor versions (only patches), giving you maximum control.

## Multi-Cluster Script

If you have multiple clusters, here's a script to apply this configuration:

```bash
#!/bin/bash
CLUSTERS=("prod-east" "prod-west" "staging")
ZONES=("us-east1-a" "us-west1-a" "us-central1-a")

for i in "${!CLUSTERS[@]}"; do
  CLUSTER=${CLUSTERS[$i]}
  ZONE=${ZONES[$i]}
  
  echo "Configuring $CLUSTER in $ZONE..."
  
  # Persistent no-minor exclusion
  gcloud container clusters update $CLUSTER \
    --zone $ZONE \
    --add-maintenance-exclusion-name "no-minor-upgrades-permanent" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
    
  # June freeze
  gcloud container clusters update $CLUSTER \
    --zone $ZONE \
    --add-maintenance-exclusion-name "june-code-freeze-2024" \
    --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
    
  # BFCM freeze
  gcloud container clusters update $CLUSTER \
    --zone $ZONE \
    --add-maintenance-exclusion-name "bfcm-freeze-2024" \
    --add-maintenance-exclusion-start-time "2024-11-20T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-12-05T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
done
```

This configuration gives you maximum control while maintaining security through automated patching outside of your critical periods.
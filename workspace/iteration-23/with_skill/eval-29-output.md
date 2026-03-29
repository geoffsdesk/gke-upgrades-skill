Based on your requirements, here's the exact configuration for your maintenance exclusions:

## Configuration for Your Three Requirements

### 1. Quarterly Code Freeze (June)
For your June code freeze, use a **"no upgrades"** exclusion that blocks ALL upgrades including patches:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "june-code-freeze" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

### 2. Black Friday/Cyber Monday (November)
For your critical retail period, use a **"no upgrades"** exclusion:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze" \
  --add-maintenance-exclusion-start-time "2024-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-15T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

### 3. No Minor Version Auto-Upgrades (Year-round)
For permanent control over minor version upgrades while still getting security patches, use a persistent **"no minor or node upgrades"** exclusion:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "manual-minor-control" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## Complete Setup Script

Here's a script to apply all three exclusions to a cluster:

```bash
#!/bin/bash
CLUSTER_NAME="your-cluster-name"
ZONE="your-zone"

# 1. Permanent minor version control (security patches still flow)
echo "Setting up permanent minor version control..."
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "manual-minor-control" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# 2. June code freeze
echo "Setting up June code freeze..."
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "june-code-freeze" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# 3. BFCM freeze
echo "Setting up BFCM freeze..."
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze" \
  --add-maintenance-exclusion-start-time "2024-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-15T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

echo "All exclusions configured successfully!"
```

## Key Points About This Configuration

**Security vs. Control Trade-offs:**
- The **permanent "no minor or node upgrades" exclusion** still allows control plane security patches to flow automatically
- The **quarterly and BFCM "no upgrades" exclusions** block even patches during critical periods
- This gives you maximum control over disruption while maintaining reasonable security posture

**How Manual Minor Upgrades Work:**
With the permanent exclusion in place, when you're ready for a minor version upgrade:

```bash
# Trigger minor upgrade manually (exclusion doesn't block manual upgrades)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_MINOR_VERSION

# Then upgrade node pools
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_MINOR_VERSION
```

**Exclusion Limits to Remember:**
- Maximum 3 "no upgrades" exclusions per cluster (you'll use 2 for June/BFCM)
- "No upgrades" exclusions limited to 30 days each
- The persistent "no minor or node" exclusion has no time limit - it tracks End of Support automatically

**For Multiple Clusters:**
Apply this same configuration to all clusters in your fleet by running the script with different `CLUSTER_NAME` and `ZONE` values.

This setup gives you exactly what you need: complete freeze during critical periods, permanent control over minor versions, and continued security patch flow during normal operations.
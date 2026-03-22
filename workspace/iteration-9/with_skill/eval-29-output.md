I'll provide the exact maintenance exclusion configurations for your three requirements. Here's how to set them up:

## 1. Quarterly Code Freeze (June)

Use a **"no upgrades"** exclusion that blocks ALL upgrades (patches, minor, nodes) during your code freeze:

```bash
# June code freeze - blocks everything for 30 days
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# For 2025 and beyond, create similar exclusions with updated dates
```

## 2. Black Friday/Cyber Monday (November)

Use **"no upgrades"** exclusion for your busiest traffic period:

```bash
# BFCM protection - blocks everything during peak traffic
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "bfcm-2024" \
  --add-maintenance-exclusion-start-time "2024-11-20T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-03T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## 3. No Minor Version Upgrades Without Approval

Use **"no minor or node upgrades"** exclusion that persists until End of Support and automatically renews:

```bash
# Persistent control over minor versions - allows CP patches, blocks minor + node upgrades
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "no-minor-upgrades-policy" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

## Complete Setup Script

Here's a script to apply all three exclusions to a cluster:

```bash
#!/bin/bash
CLUSTER_NAME="your-cluster-name"
ZONE="your-zone"

# 1. June code freeze
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# 2. BFCM protection
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "bfcm-2024" \
  --add-maintenance-exclusion-start-time "2024-11-20T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-03T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# 3. Persistent minor version control
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "no-minor-upgrades-policy" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

echo "All maintenance exclusions configured successfully"
```

## Verification

Check your exclusions are active:

```bash
gcloud container clusters describe $CLUSTER_NAME \
  --zone $ZONE \
  --format="yaml(maintenancePolicy.window.maintenanceExclusions)"
```

## Key Benefits of This Configuration

1. **June & November**: Complete protection during critical business periods
2. **Minor version control**: You'll still get security patches on the control plane, but no disruptive minor version or node upgrades without your approval
3. **Persistent exclusions**: The `--add-maintenance-exclusion-until-end-of-support` flag automatically tracks EoS dates and renews when you upgrade to new minor versions

## When You Want to Upgrade

When you're ready for a minor version upgrade:

```bash
# Remove the persistent exclusion temporarily
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --remove-maintenance-exclusion-name "no-minor-upgrades-policy"

# Perform your planned upgrade
gcloud container clusters upgrade $CLUSTER_NAME \
  --zone $ZONE \
  --master \
  --cluster-version TARGET_VERSION

# Re-add the exclusion for the new version
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "no-minor-upgrades-policy" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

This gives you complete control over when upgrades happen while still receiving critical security patches.
# GKE Maintenance Exclusion Configuration

Based on your requirements, here's the exact configuration to handle your three scenarios:

## 1. Quarterly Code Freeze (June) - "No upgrades" exclusion

This blocks ALL upgrades (patches, minor versions, nodes) during your code freeze:

```bash
# June code freeze (example: June 1-30, 2024)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

**Key points:**
- Maximum 30-day duration (covers your quarterly freeze)
- Blocks everything including critical security patches
- Honored even after version End of Support
- Must be recreated each quarter with new dates

## 2. Black Friday/Cyber Monday (November) - "No upgrades" exclusion

Same pattern for your busiest commercial period:

```bash
# BFCM protection (example: November 15 - December 5, 2024)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze-2024" \
  --add-maintenance-exclusion-start-time "2024-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-05T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## 3. Block Minor Version Upgrades (Permanent) - "No minor or node upgrades" exclusion

This gives you maximum control - allows security patches on the control plane but blocks all disruptive upgrades:

```bash
# Permanent minor version control (example: valid until 1.32 EoS)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "no-minor-upgrades-permanent" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-06-01T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

**Why "no minor or node upgrades" instead of "no minor upgrades":**
- Blocks both minor version AND node pool upgrades
- Still allows control plane security patches (critical for security)
- You maintain full control over when disruptive changes happen
- Can be extended up to the version's End of Support date

## Complete setup script

Here's a script to configure all three exclusions on a cluster:

```bash
#!/bin/bash

CLUSTER_NAME="your-cluster-name"
ZONE="us-central1-a"
YEAR="2024"

# 1. June code freeze
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "june-code-freeze-$YEAR" \
  --add-maintenance-exclusion-start-time "${YEAR}-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "${YEAR}-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# 2. BFCM freeze
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "bfcm-freeze-$YEAR" \
  --add-maintenance-exclusion-start-time "${YEAR}-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "${YEAR}-12-05T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# 3. Permanent minor version control
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "no-minor-upgrades-permanent" \
  --add-maintenance-exclusion-start-time "${YEAR}-01-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-06-01T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

echo "All maintenance exclusions configured for $CLUSTER_NAME"
```

## Verification

Check your exclusions are active:

```bash
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(maintenancePolicy.window.maintenanceExclusions)"
```

## Important management notes

1. **Annual renewal required:** The permanent "no minor or node upgrades" exclusion needs to be extended before it expires (set end date to the current version's EoS date).

2. **Security patches still flow:** During the permanent exclusion, you'll still get control plane security patches automatically - only disruptive upgrades are blocked.

3. **Manual upgrade capability:** You can still manually upgrade whenever YOU choose, even with exclusions active. The exclusions only block auto-upgrades.

4. **End of Support override:** The 30-day "no upgrades" exclusions (June, BFCM) will be honored even past version EoS. The permanent exclusion will be overridden at EoS.

5. **Channel recommendation:** Ensure your clusters are on a release channel (Regular or Stable recommended) rather than legacy "No channel" to get the full power of these exclusion types.

This configuration gives you complete control over when disruptive changes happen while maintaining security through automated patching.
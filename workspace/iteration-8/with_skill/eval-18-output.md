# GKE Maintenance Windows & Exclusions for SOX Compliance

I'll help you configure maintenance windows and exclusions for your regulated environment. This setup will ensure auto-upgrades only occur on weekends while respecting your compliance requirements.

## Recommended Configuration Strategy

### Release Channel Selection
For SOX compliance, I recommend migrating to **Stable** channel if not already:
- Versions are thoroughly tested before reaching Stable
- More predictable upgrade timing
- Full SLA coverage
- Better suited for regulated environments

### Maintenance Window Configuration

**Weekend-only upgrades with Saturday maintenance windows:**

```bash
# Apply to all 3 clusters
for CLUSTER in cluster-prod cluster-staging cluster-dev; do
  gcloud container clusters update $CLUSTER \
    --zone YOUR_ZONE \
    --maintenance-window-start "2024-01-06T02:00:00Z" \
    --maintenance-window-end "2024-01-06T08:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
done
```

**Key decisions made:**
- **Saturday 2:00-8:00 AM UTC** (adjust timezone as needed)
- **6-hour window** to accommodate large cluster upgrades
- **Weekly recurrence** for consistent scheduling

### Maintenance Exclusion Strategy

**1. Quarterly Code Freezes (persistent exclusions):**

```bash
# Example: Q1 2024 code freeze (adjust dates for your quarters)
gcloud container clusters update CLUSTER_NAME \
  --zone YOUR_ZONE \
  --add-maintenance-exclusion-name "Q1-2024-code-freeze" \
  --add-maintenance-exclusion-start-time "2024-03-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-03-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades

# Repeat for Q2, Q3, Q4 with your specific dates
```

**2. Annual November Audit (conservative exclusion):**

```bash
# Block all upgrades during audit period
gcloud container clusters update CLUSTER_NAME \
  --zone YOUR_ZONE \
  --add-maintenance-exclusion-name "annual-audit-2024" \
  --add-maintenance-exclusion-start-time "2024-11-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-11-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

**3. SOX-Friendly Baseline Control (recommended):**

For maximum control while still receiving security patches:

```bash
# Apply persistent "no minor or node upgrades" exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone YOUR_ZONE \
  --add-maintenance-exclusion-name "sox-baseline-control" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-until-end-of-support \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

This allows control plane security patches but blocks disruptive changes.

## Exclusion Type Comparison

| Exclusion Scope | What it blocks | Max Duration | Use Case |
|----------------|---------------|-------------|----------|
| **"no_upgrades"** | All upgrades (patches, minor, nodes) | 30 days | Code freezes, audit periods |
| **"no_minor_or_node_upgrades"** | Minor + node upgrades. Allows CP patches. | Until EoS | SOX baseline control |
| **"no_minor_upgrades"** | Minor only. Allows patches + node upgrades. | Until EoS | Less conservative option |

## Complete Setup Script

```bash
#!/bin/bash
# GKE Maintenance Configuration for SOX Compliance

# Variables - CUSTOMIZE THESE
CLUSTERS=("cluster-prod" "cluster-staging" "cluster-dev")
ZONE="us-central1-a"
MAINTENANCE_START="2024-01-06T02:00:00Z"  # Saturday 2 AM UTC
MAINTENANCE_END="2024-01-06T08:00:00Z"    # Saturday 8 AM UTC

# 1. Configure weekend maintenance windows
for CLUSTER in "${CLUSTERS[@]}"; do
  echo "Configuring maintenance window for $CLUSTER..."
  gcloud container clusters update $CLUSTER \
    --zone $ZONE \
    --maintenance-window-start $MAINTENANCE_START \
    --maintenance-window-end $MAINTENANCE_END \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
done

# 2. Apply baseline SOX control (allows CP patches, blocks disruptive changes)
for CLUSTER in "${CLUSTERS[@]}"; do
  echo "Applying SOX baseline exclusion for $CLUSTER..."
  gcloud container clusters update $CLUSTER \
    --zone $ZONE \
    --add-maintenance-exclusion-name "sox-baseline-control" \
    --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
    --add-maintenance-exclusion-until-end-of-support \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades
done

# 3. Add November 2024 audit exclusion
for CLUSTER in "${CLUSTERS[@]}"; do
  echo "Adding audit period exclusion for $CLUSTER..."
  gcloud container clusters update $CLUSTER \
    --zone $ZONE \
    --add-maintenance-exclusion-name "annual-audit-2024" \
    --add-maintenance-exclusion-start-time "2024-11-01T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-11-30T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
done

echo "Configuration complete. Verify with:"
echo "gcloud container clusters describe CLUSTER_NAME --zone $ZONE --format='yaml(maintenancePolicy)'"
```

## SOX Compliance Benefits

This configuration provides:

✅ **Predictable timing**: Upgrades only on Saturday maintenance windows
✅ **Change control**: Baseline exclusion prevents unexpected minor/node upgrades
✅ **Security patches**: Control plane patches still flow through (critical for compliance)
✅ **Audit protection**: Complete upgrade freeze during November audit
✅ **Code freeze respect**: Quarterly exclusions block all changes during critical periods
✅ **Audit trail**: All maintenance exclusions are logged and visible in the console

## Validation Commands

```bash
# Check current maintenance policy
gcloud container clusters describe CLUSTER_NAME \
  --zone YOUR_ZONE \
  --format="yaml(maintenancePolicy)"

# View all exclusions
gcloud container clusters describe CLUSTER_NAME \
  --zone YOUR_ZONE \
  --format="table(maintenancePolicy.window.maintenanceExclusions[].name,
                   maintenancePolicy.window.maintenanceExclusions[].startTime,
                   maintenancePolicy.window.maintenanceExclusions[].endTime,
                   maintenancePolicy.window.maintenanceExclusions[].scope)"

# Check auto-upgrade status and target versions
gcloud container clusters get-upgrade-info CLUSTER_NAME --region YOUR_REGION
```

## Operational Recommendations

1. **Upgrade Planning**: During non-excluded periods, manually initiate upgrades at the start of your Saturday window for predictability rather than waiting for auto-upgrade

2. **Quarterly Process**: Before each quarter, review and add the next quarter's code freeze exclusion

3. **Version Monitoring**: Use the GKE deprecation insights dashboard to track API usage before upgrades

4. **Documentation**: Maintain a changelog of all cluster version changes for audit purposes

5. **Emergency Patches**: For critical security patches during exclusions, you can still manually upgrade (exclusions don't block manual upgrades, only auto-upgrades)

This setup gives you maximum control while maintaining the benefits of GKE's automated lifecycle management within your compliance requirements.
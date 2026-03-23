# GKE 1.30 End of Support Impact Analysis

## EoS Timeline & What Will Happen

**GKE 1.30 Standard Support ends:** February 2025
**Extended Support ends:** February 2026

### Regular Channel Clusters (3 clusters)
**What happens:** When 1.30 reaches EoS in February 2025, these clusters will be **automatically force-upgraded** to GKE 1.31 (the next supported minor version). Both control plane AND all node pools will be upgraded together following your cluster-level maintenance policies.

**Timeline:** The force upgrade will occur during your configured maintenance windows, respecting any active maintenance exclusions. If you have no maintenance window configured, upgrades can happen at any time.

### Extended Channel Clusters (2 clusters)
**What happens:** These clusters get a **1-year reprieve**. They'll continue receiving patches and stay on 1.30 until February 2026. However, **minor version upgrades are NOT automated** on Extended channel - you must plan and execute the 1.30→1.31 upgrade yourself before extended support expires.

**Critical note:** Extended channel provides extra time but requires proactive minor version management. Don't assume these clusters will auto-upgrade to 1.31.

### Legacy "No Channel" Cluster (1 cluster)
**What happens:** This cluster faces the **most aggressive enforcement**. When 1.30 reaches EoS:
- Control plane: Force-upgraded to 1.31
- Node pools: Force-upgraded to the next supported version **even if auto-upgrade is disabled**

The only temporary delay available is a 30-day "no upgrades" maintenance exclusion.

## Preparation Options by Cluster Type

### For Regular Channel Clusters

**Option 1: Let auto-upgrade handle it (recommended for most)**
```bash
# Verify your maintenance windows are set appropriately
gcloud container clusters describe CLUSTER_NAME --region REGION \
  --format="value(maintenancePolicy)"

# Set maintenance window if needed (example: Saturdays 2-6 AM UTC)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-window-start "2025-01-11T02:00:00Z" \
  --maintenance-window-end "2025-01-11T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Option 2: Proactive upgrade to 1.31 before EoS**
- Gives you control over timing
- Allows testing and validation in your schedule
- Prevents unexpected force-upgrades

**Option 3: Use maintenance exclusions for controlled timing**
```bash
# Block upgrades during critical periods, allow during maintenance windows
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "no-upgrades-holiday-season" \
  --add-maintenance-exclusion-start-time "2024-12-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-01-05T00:00:00Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

### For Extended Channel Clusters

**Required action:** You MUST upgrade these to 1.31 before February 2026. Extended channel won't do this automatically.

**Recommended approach:**
1. Plan manual upgrade to 1.31 in Q4 2024 or Q1 2025
2. Test compatibility with 1.31 in staging
3. Execute upgrade during planned maintenance window
4. Continue Extended channel or migrate to Regular/Stable

```bash
# Manual upgrade command (when ready)
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --cluster-version "1.31.x-gke.xxxx"
```

### For Legacy "No Channel" Cluster

**Strongly recommended:** Migrate to a release channel BEFORE the 1.30 EoS upgrade happens.

**Migration path:**
```bash
# Migrate to Regular channel (most similar to "No channel" behavior)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --release-channel regular

# Or Extended if you want maximum upgrade control
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --release-channel extended
```

**Why migrate now:**
- Release channels give you more sophisticated maintenance exclusion options
- "No minor or node upgrades" exclusions (not available on "No channel")
- Better integration with maintenance windows
- Extended channel option for longer support cycles

## Recommended Action Plan

### Immediate (Next 30 days)
1. **Migrate the "No channel" cluster** to Regular or Extended channel
2. **Verify maintenance windows** on all Regular channel clusters
3. **Plan 1.31 upgrade timeline** for Extended channel clusters

### Before February 2025
1. **Test 1.31 compatibility** in staging environments
2. **Execute proactive upgrades** if you prefer control over timing
3. **Apply maintenance exclusions** around any critical business periods

### Monitoring & Preparation
```bash
# Check current auto-upgrade targets and EoS dates
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Review deprecation insights for 1.30→1.31 compatibility
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=REGION \
  --project=PROJECT_ID
```

## Key Differences Summary

| Cluster Type | EoS Behavior | Your Control Level | Recommended Action |
|--------------|--------------|-------------------|-------------------|
| **Regular** | Auto force-upgrade CP+nodes to 1.31 | Maintenance windows + exclusions | Configure maintenance windows |
| **Extended** | Manual upgrade required by Feb 2026 | Full control over minor upgrades | Plan manual 1.31 upgrade |
| **No channel** | Aggressive force-upgrade | Limited (30-day exclusions only) | **Migrate to release channel first** |

The Extended channel clusters are actually in the best position - they have the most time and control. The "No channel" cluster needs immediate attention due to limited exclusion options.

Would you like me to create specific upgrade runbooks for any of these cluster types, or help you plan the migration timeline?
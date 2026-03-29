# GKE 1.30 End of Support Impact Analysis

Based on your cluster configuration, here's what will happen to each cluster type when GKE 1.30 reaches End of Support:

## End of Support Timeline

**GKE 1.30 End of Support dates:**
- **Standard support ends:** March 2025 (estimated)
- **Extended support ends:** March 2027 (estimated, for Extended channel only)

## Impact by Cluster Type

### Regular Channel Clusters (3 clusters)
**What happens at EoS:**
- **Control plane:** Force-upgraded to 1.31 (next supported minor version)
- **Node pools:** Force-upgraded to 1.31 following cluster-level upgrade policies
- **Timing:** Upgrades happen during your maintenance windows if configured, otherwise at GKE's discretion
- **No exceptions:** Cannot defer beyond EoS date except with temporary "no upgrades" exclusions (30-day max)

### Extended Channel Clusters (2 clusters)
**What happens at EoS:**
- **Standard support period (until March 2025):** Same behavior as Regular channel - force-upgraded to 1.31
- **Extended support period (March 2025 - March 2027):** 
  - **Additional cost applies** during extended period only
  - Continue receiving patches but NO automatic minor version upgrades
  - Must manually upgrade to newer minors before extended support expires
  - At end of extended support (March 2027): Force-upgraded if still on 1.30

### Legacy "No Channel" Cluster (1 cluster)
**What happens at EoS:**
- **Control plane:** Force-upgraded to 1.31
- **Node pools:** Systematic force-upgrade enforcement - ALL node pools upgraded to supported version even if "no auto-upgrade" is configured
- **Limited protection:** Only 30-day "no upgrades" exclusions can defer (no "no minor" exclusion available)
- **Higher risk:** Lacks advanced maintenance controls available on release channels

## Preparation Options

### Immediate Actions (All Clusters)

```bash
# Check current auto-upgrade targets
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Verify deprecated API usage (common upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Check GKE deprecation insights
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=LOCATION --project=PROJECT_ID
```

### Strategy 1: Proactive Manual Upgrade (Recommended)
**Best for:** Controlled timing, testing, and validation

```bash
# Sequential minor upgrades (required path)
# Control plane first: 1.30 → 1.31 → 1.32 → 1.33
gcloud container clusters upgrade CLUSTER_NAME \
    --master --cluster-version=1.31.x-gke.latest

# Then node pools (can skip-level within 2-version skew)
gcloud container node-pools upgrade POOL_NAME \
    --cluster=CLUSTER_NAME --cluster-version=1.33.x-gke.latest
```

**Upgrade sequence:**
1. **Control plane:** Must upgrade sequentially (1.30→1.31→1.32→1.33)
2. **Node pools:** Can skip-level upgrade (1.30→1.32 or 1.30→1.33) once CP is at target

### Strategy 2: Controlled Auto-Upgrade
**Best for:** Hands-off approach with timing control

```bash
# Configure maintenance windows for predictable timing
gcloud container clusters update CLUSTER_NAME \
    --maintenance-window-start "2024-12-01T02:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Optional: Add disruption intervals to slow upgrade pace
gcloud container clusters update CLUSTER_NAME \
    --maintenance-minor-version-disruption-interval=2592000s  # 30 days between minor upgrades
```

### Strategy 3: Migrate Legacy Cluster
**Critical for your "No channel" cluster:**

```bash
# Migrate to Regular channel (closest to legacy behavior)
gcloud container clusters update CLUSTER_NAME \
    --release-channel regular

# Or Extended channel for maximum EoS flexibility
gcloud container clusters update CLUSTER_NAME \
    --release-channel extended
```

**Why migrate:** Your "No channel" cluster lacks the powerful maintenance exclusion types ("no minor or node upgrades") that provide better upgrade control than the legacy per-nodepool settings.

### Strategy 4: Temporary Deferral (Emergency Only)

```bash
# 30-day deferral (can chain up to 3 exclusions, max 90 days total)
gcloud container clusters update CLUSTER_NAME \
    --add-maintenance-exclusion-name "eos-defer" \
    --add-maintenance-exclusion-start "2025-03-01T00:00:00Z" \
    --add-maintenance-exclusion-end "2025-03-31T23:59:59Z" \
    --add-maintenance-exclusion-scope no_upgrades
```

**Warning:** Deferring accumulates security debt. Use only for critical business periods.

## Recommended Action Plan

### Phase 1: Immediate (This Week)
1. **Migrate the "No channel" cluster** to Regular or Extended channel
2. **Check deprecated API usage** across all clusters - this is the #1 upgrade failure cause
3. **Configure maintenance windows** on all clusters for predictable timing

### Phase 2: Testing (Next 2 Weeks)
1. **Create staging clusters** at target versions (1.33+) 
2. **Test workload compatibility** - especially admission webhooks, operators, and GPU workloads
3. **Validate skip-level node pool upgrades** in staging

### Phase 3: Production Upgrades (Before March 2025)
1. **Start with Extended channel clusters** - you have the most flexibility
2. **Use skip-level node pool upgrades** where possible (1.30→1.33) to minimize disruption
3. **Sequence upgrades** across environments: dev → staging → prod

### Configuration Commands

```bash
# Check current status
for cluster in cluster1 cluster2 cluster3; do
  echo "=== $cluster ==="
  gcloud container clusters describe $cluster --region=REGION \
    --format="table(name,currentMasterVersion,releaseChannel.channel,nodePools[].version)"
done

# Recommended maintenance exclusion for maximum control (Extended clusters)
gcloud container clusters update CLUSTER_NAME \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support

# Monitor scheduled upgrades (72h advance notice)
gcloud container clusters update CLUSTER_NAME \
    --send-scheduled-upgrade-notifications
```

## Key Warnings

1. **Extended channel cost:** Additional charges apply ONLY during the extended support period (March 2025-2027), not before
2. **Snowflake risk:** Avoid indefinite version freezing - it compounds upgrade difficulty and creates security debt
3. **Version skew:** Node pools can't be more than 2 minor versions behind control plane
4. **Deprecated APIs:** Check and fix before upgrading - GKE automatically pauses auto-upgrades when deprecated usage is detected

The Extended channel clusters give you the most flexibility, but all clusters need attention before March 2025 EoS enforcement begins.
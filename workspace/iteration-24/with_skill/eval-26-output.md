# GKE 1.30 End of Support Impact Analysis

Your clusters will face **different EoS enforcement behaviors** depending on their channel configuration. Here's what will happen to each:

## EoS Enforcement by Channel Type

### Regular Channel Clusters (3 clusters)
**What happens:** Automatic upgrade to GKE 1.31 when 1.30 reaches End of Standard Support
- **Control plane:** Force-upgraded to 1.31 (next supported minor version)
- **Node pools:** Force-upgraded to 1.31 following cluster-level policies
- **Timing:** When 1.30 reaches End of Standard Support (~14 months after release)
- **Override options:** 30-day "no upgrades" maintenance exclusion can defer temporarily

### Extended Channel Clusters (2 clusters) 
**What happens:** **NO automatic upgrade** when 1.30 reaches End of Standard Support
- **Extended support period:** Up to 24 months total support (extra 10 months beyond standard)
- **Only patches auto-applied** during extended period — minor upgrades must be user-initiated
- **Final enforcement:** Automatic upgrade to next supported version only at **end of extended support**
- **Cost:** Additional charges apply only during the extended support period (months 15-24)

### Legacy "No Channel" Cluster (1 cluster)
**What happens:** Systematic EoS enforcement (applies to GKE 1.32+ going forward)
- **Control plane:** Force-upgraded to 1.31 when 1.30 reaches EoS
- **Node pools:** Force-upgraded even if "no auto-upgrade" is configured
- **Limited options:** Only 30-day "no upgrades" exclusion can provide temporary deferral

## Your Preparation Options

### Option 1: Proactive Manual Upgrades (Recommended)
Upgrade all clusters to GKE 1.31+ before EoS enforcement kicks in:

```bash
# Check current upgrade targets
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --master \
  --cluster-version 1.31.X-gke.XXXX \
  --region REGION

# Then upgrade node pools (Standard clusters only)
gcloud container node-pools upgrade POOL_NAME \
  --cluster CLUSTER_NAME \
  --cluster-version 1.31.X-gke.XXXX \
  --region REGION
```

**Benefits:** 
- Full control over timing and sequencing
- Avoid forced upgrade disruption
- Test and validate at your own pace

### Option 2: Extended Channel Migration (for clusters needing more time)
Move your Regular channel clusters to Extended channel for additional runway:

```bash
# Migrate Regular → Extended (gives you extra 10 months)
gcloud container clusters update CLUSTER_NAME \
  --release-channel extended \
  --region REGION
```

**Important migration consideration:** If your current 1.30 version isn't yet available in Extended channel, your cluster will be "ahead of channel" and won't receive auto-upgrades until Extended catches up to 1.30.

### Option 3: "No Channel" Migration Strategy
For the legacy cluster, migrate to Extended channel for maximum control:

```bash
# No channel → Extended (recommended path)
gcloud container clusters update CLUSTER_NAME \
  --release-channel extended \
  --region REGION
```

This gives you:
- Up to 24 months of support for 1.30
- Manual control over minor version upgrades
- Only patches auto-applied
- More granular maintenance exclusion options

## Maintenance Exclusion Strategy

If you need to defer the forced upgrades temporarily, apply exclusions **before** EoS date:

```bash
# 30-day emergency deferral (works on all cluster types)
gcloud container clusters update CLUSTER_NAME \
  --add-maintenance-exclusion-name "eos-deferral" \
  --add-maintenance-exclusion-start $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end $(date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades \
  --region REGION
```

## Recommended Action Plan

### Immediate (Next 2 weeks)
1. **Check EoS timeline:** `gcloud container clusters get-upgrade-info` for all clusters
2. **Migrate legacy cluster:** Move "No channel" → Extended channel for better control
3. **Plan upgrade sequence:** Dev → Staging → Production with validation gaps

### Short-term (Next month)
1. **Test 1.31 in development:** Validate workload compatibility
2. **Review breaking changes:** Check GKE 1.30→1.31 release notes for deprecated APIs
3. **Configure maintenance windows:** Set predictable upgrade timing for each cluster

### Before EoS enforcement
1. **Proactively upgrade** Regular channel clusters to 1.31
2. **Keep Extended channel clusters on 1.30** if you need maximum stability (they won't be force-upgraded)
3. **Monitor GKE release schedule** for actual EoS dates

## Key Insight: Extended Channel Advantage

Your **Extended channel clusters are in the best position** — they won't face forced upgrades when 1.30 reaches standard EoS. You can stay on 1.30 for up to 24 months total, giving you maximum flexibility to upgrade on your timeline.

Consider migrating your Regular channel clusters to Extended if you need more time to prepare for 1.31.

**Next steps:** Run `gcloud container clusters get-upgrade-info` on all clusters to see exact EoS timestamps and current auto-upgrade targets, then decide your upgrade timeline based on your operational constraints.
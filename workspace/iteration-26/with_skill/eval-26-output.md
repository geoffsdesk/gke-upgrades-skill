# GKE 1.30 End of Support Impact Analysis

## What Happens at EoS for Each Configuration

### Regular Channel Clusters (3 clusters)
**Automatic enforcement:** When 1.30 reaches EoS, these clusters will be **force-upgraded to 1.31** (next supported minor version) automatically. This affects both control plane and all node pools.

- **Timing:** EoS enforcement is systematic and unavoidable
- **Scope:** Control plane upgraded first, then all node pools follow
- **No manual intervention required** — but also no way to prevent it except temporary exclusions

### Extended Channel Clusters (2 clusters) 
**Protected until end of extended support:** These clusters have up to **24 months of support** for 1.30, so they won't be force-upgraded when standard support ends.

- **Extended timeline:** Standard EoS becomes irrelevant — you get additional time
- **Cost:** Extra charges apply ONLY during the extended support period (after standard EoS)
- **Manual minor upgrades:** During extended support, minor version upgrades are NOT automatic for the control plane — you must trigger them manually when ready

### Legacy "No Channel" Cluster (1 cluster)
**Same enforcement as Regular:** Despite being on "No channel," this cluster will be **force-upgraded to 1.31** at EoS just like the Regular channel clusters.

- **No special protection:** "No channel" doesn't exempt you from EoS enforcement
- **Limited exclusion options:** Only supports 30-day "no upgrades" exclusions, not the granular controls available on release channels

## Your Options to Prepare

### Option 1: Accept Automatic Upgrades (Recommended for most)
**For Regular channel clusters:**
- Configure maintenance windows for acceptable timing
- Ensure workloads are upgrade-ready (PDBs, no deprecated APIs)
- Let GKE handle the upgrade automatically

**Commands:**
```bash
# Set maintenance window (example: Saturday 2-6 AM)
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --maintenance-window-start "2024-12-07T02:00:00Z" \
    --maintenance-window-end "2024-12-07T06:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### Option 2: Manual Upgrade Control
**Upgrade proactively before EoS enforcement:**
- Trigger manual upgrades to 1.31 (or newer) at your preferred timing
- Apply temporary "no upgrades" exclusion during critical periods
- Resume auto-upgrades after catching up

**Commands:**
```bash
# Manual control plane upgrade
gcloud container clusters upgrade CLUSTER_NAME \
    --zone ZONE \
    --master \
    --cluster-version 1.31.X-gke.XXX

# Then upgrade node pools
gcloud container node-pools upgrade NODE_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version 1.31.X-gke.XXX
```

### Option 3: Temporary Deferral (Maximum 30 days)
**For critical business periods:**
```bash
# Block all upgrades temporarily (works even past EoS)
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "eos-deferral" \
    --add-maintenance-exclusion-start-time "2024-12-15T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2025-01-15T00:00:00Z" \
    --add-maintenance-exclusion-scope no_upgrades
```

### Option 4: Migrate Legacy Cluster to Extended Channel
**For the "No channel" cluster:**
```bash
# Move to Extended channel for maximum flexibility
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --release-channel extended
```

**Benefits:**
- Up to 24 months of support instead of forced upgrade
- Access to better maintenance exclusion controls
- Manual control over minor version upgrades during extended support

## Recommended Action Plan

### Immediate (Next 2 weeks):
1. **Migrate the "No channel" cluster** to Extended channel — this gives you the most options and flexibility around EoS timing
2. **Configure maintenance windows** on Regular channel clusters for acceptable upgrade timing
3. **Run deprecation checks** on all clusters:
   ```bash
   kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
   ```

### Pre-EoS (4-6 weeks before):
1. **Test 1.31 in staging** — deploy representative workloads and validate compatibility
2. **Update admission webhooks and operators** that may not support 1.31
3. **Set up monitoring** for the upgrade events

### Critical Business Periods:
- Use 30-day "no upgrades" exclusions to defer past EoS if needed for events like BFCM
- Plan to catch up quickly after the critical period ends

## Key Warnings

⚠️ **Version drift accumulation:** The longer clusters stay on 1.30, the harder the eventual upgrade becomes. Deprecated APIs accumulate, and the blast radius of forced upgrades increases.

⚠️ **Extended channel costs:** Extra charges apply only during extended support, but make sure this fits your budget for the 2 Extended channel clusters.

⚠️ **No permanent freezing:** Even Extended channel clusters eventually reach end of extended support and face the same enforcement. Use the extra time to plan and execute controlled upgrades.

## Timeline Check

Use these commands to check your current EoS timeline:
```bash
# Check exact EoS dates for your clusters
gcloud container clusters get-upgrade-info CLUSTER_NAME --zone ZONE

# Check GKE release schedule for EoS estimates
# Visit: https://cloud.google.com/kubernetes-engine/docs/release-schedule
```

The Extended channel clusters are your safest bet for avoiding forced upgrades, while the Regular channel clusters should be prepared for automatic upgrade with proper maintenance windows and workload readiness.
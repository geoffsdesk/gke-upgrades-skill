# GKE 1.30 End of Support Impact Analysis

Based on your cluster configuration, here's what will happen to each cluster type when GKE 1.30 reaches End of Support, plus your preparation options.

## End of Support Timeline for 1.30

- **Standard support ends:** May 28, 2025
- **Extended support ends:** May 28, 2026 (Extended channel only)

## Impact by Cluster Configuration

### Regular Channel Clusters (3 clusters)
**What happens at EoS:**
- **Automatic upgrade to 1.31** (next supported minor version)
- Both control plane AND node pools upgraded automatically
- No way to prevent this except temporary "no upgrades" exclusion (30 days max)
- Upgrade follows your existing maintenance windows and exclusion policies

**Current auto-upgrade behavior:**
- Already receiving 1.31 patches if 1.31 is the current auto-upgrade target
- Will be upgraded to 1.31 minor when it becomes the Regular channel target

### Extended Channel Clusters (2 clusters)
**What happens at standard EoS (May 28, 2025):**
- **Nothing** — clusters continue running 1.30 with continued support
- Receive security patches until extended support ends (May 28, 2026)
- **Minor version auto-upgrades are disabled** — only patches auto-apply

**What happens at extended EoS (May 28, 2026):**
- **Automatic upgrade to next supported minor version**
- Same enforcement as Regular channel, just delayed 12 months

### Legacy "No Channel" Cluster (1 cluster)
**What happens at EoS:**
- **Control plane:** Auto-upgraded to 1.31 (systematic enforcement)
- **Node pools:** Auto-upgraded to 1.31 even if "no auto-upgrade" is configured
- Only the 30-day "no upgrades" exclusion can defer this temporarily

**Current behavior:**
- Upgrades at the pace of Stable channel for minor releases
- Already should be receiving patches at Regular channel pace

## Your Preparation Options

### Option 1: Proactive Manual Upgrade (Recommended)
Upgrade all clusters to 1.31+ before EoS enforcement:

```bash
# For each cluster
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.31.3-gke.1146000  # or latest 1.31 patch

# Then upgrade node pools
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.3-gke.1146000
```

**Advantages:**
- Full control over timing and sequence
- Can test thoroughly in dev/staging first
- Avoid forced upgrades during business hours

### Option 2: Migrate Legacy Cluster to Extended Channel
Move your "No channel" cluster to Extended for maximum control:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

**Benefits:**
- Gains 12 months additional time (until May 2026)
- Access to persistent maintenance exclusions
- Better upgrade control tools than "No channel"

### Option 3: Configure Maintenance Controls
For clusters staying on auto-upgrade, ensure proper timing:

```bash
# Set maintenance window (example: Saturday 2-6 AM)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2025-01-04T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Optional: Add "no minor or node upgrades" exclusion for max control
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support \
  --add-maintenance-exclusion-name "production-stability"
```

### Option 4: Temporary Deferral (Emergency Only)
If you need to defer EoS enforcement temporarily:

```bash
# 30-day "no upgrades" exclusion (honored even past EoS)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "eos-deferral" \
  --add-maintenance-exclusion-start-time "2025-05-28T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-06-27T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

⚠️ **Warning:** This accumulates security debt. Only use for critical business periods.

## Pre-Upgrade Preparation Checklist

```markdown
Pre-1.31 Upgrade Preparation
- [ ] Check deprecated API usage: `kubectl get --raw /metrics | grep deprecated`
- [ ] Review GKE release notes for 1.30→1.31 breaking changes
- [ ] Test 1.31 in dev/staging clusters first
- [ ] Verify third-party operators support Kubernetes 1.31
- [ ] Configure PDBs for critical workloads
- [ ] Set appropriate maintenance windows for auto-upgrading clusters
- [ ] Document rollback plan (though minor version rollbacks require support)
```

## Recommended Timeline

**Immediate (January 2025):**
1. Test 1.31 upgrade in dev environment
2. Configure maintenance windows for all clusters
3. Consider migrating "No channel" cluster to Extended

**February-March 2025:**
1. Manually upgrade staging clusters to 1.31
2. Validate application compatibility
3. Plan production upgrade sequence

**April 2025:**
1. Manually upgrade production clusters (before forced EoS)
2. This gives you control over timing vs waiting for enforcement

**Key insight:** Your Extended channel clusters have the most time (until May 2026), but Regular and "No channel" clusters will be force-upgraded in May 2025. Proactive upgrades in Q1 2025 give you maximum control.

Would you like me to create specific upgrade runbooks for any of these clusters, or help you set up the maintenance controls?
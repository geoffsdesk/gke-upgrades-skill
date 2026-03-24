# GKE 1.30 End of Support - What Happens & Your Options

## EoS Timeline & Impact by Channel

**GKE 1.30 End of Standard Support:** Expected **March 2025** (14 months after 1.30 GA)
**GKE 1.30 End of Extended Support:** **March 2026** (24 months after 1.30 GA)

## What Happens to Each Cluster Type

### Regular Channel Clusters (3 clusters)
**When 1.30 reaches EoS in March 2025:**
- ✅ **Control plane:** Auto-upgraded to 1.31 (next supported minor version)
- ✅ **Node pools:** Auto-upgraded to 1.31 following your configured upgrade strategy
- **Timeline:** Force upgrade occurs systematically when 1.30 reaches EoS
- **No escape:** Even maintenance exclusions won't prevent EoS enforcement long-term

### Extended Channel Clusters (2 clusters) 
**Advantage: You have more time**
- ⏰ **March 2025:** No forced upgrade (still in extended support period)
- ⏰ **March 2026:** Force upgrade to next supported minor when extended support ends
- **Key difference:** Extended channel gives you an **extra 12 months** to plan and execute upgrades
- **Cost:** Additional charges apply only during the extended support period (March 2025-2026)

### Legacy "No Channel" Cluster (1 cluster)
**Most vulnerable - lacks upgrade control tools:**
- 🚨 **Control plane:** Force-upgraded to 1.31 when 1.30 reaches EoS (March 2025)
- 🚨 **Node pools:** Force-upgraded even if auto-upgrade is disabled
- **Limited protection:** Only 30-day "no upgrades" exclusions available (not the granular control of release channels)
- **Recommendation:** Migrate this cluster to a release channel BEFORE EoS

## Your Options to Prepare

### Option 1: Proactive Manual Upgrades (Recommended)
**Timeline:** Start January 2025 (before EoS enforcement)

```bash
# Check current auto-upgrade targets
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Plan upgrades: 1.30 → 1.31 → 1.32 (if desired)
# Control plane first, then node pools
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version 1.31.X-gke.XXXX

# Node pools (after CP upgrade completes)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.31.X-gke.XXXX
```

**Benefits:**
- Control timing and sequence
- Test in dev/staging first
- Avoid forced upgrade during business hours

### Option 2: Leverage Extended Channel
**For the Regular channel clusters:**

```bash
# Migrate to Extended channel for more time
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --release-channel extended
```

**Benefits:**
- Buys 12 additional months until March 2026
- Same auto-upgrade behavior as Regular, just extended timeline
- Cost only applies during extended period

### Option 3: Configure Upgrade Controls
**Add maintenance windows and exclusions:**

```bash
# Set maintenance windows (off-peak hours)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-window-start "2025-01-15T02:00:00Z" \
  --maintenance-window-duration "4h" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"

# Add "no minor or node upgrades" exclusion for maximum control
# (allows CP security patches, blocks disruptive upgrades)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "controlled-upgrade-2025" \
  --add-maintenance-exclusion-start-time "2025-01-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-03-01T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

### Option 4: Fix the Legacy "No Channel" Cluster
**Critical: This cluster lacks proper upgrade controls**

```bash
# Check current channel
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="value(releaseChannel.channel)"

# Migrate to Regular or Extended channel
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --release-channel regular  # or extended for max flexibility
```

**Why this matters:** Release channels provide:
- "No minor or node upgrades" exclusions (not available on "No channel")
- Better EoS management
- Rollout sequencing capabilities

## Recommended Action Plan

### Phase 1: Immediate (December 2024)
1. **Migrate the "No channel" cluster** to Regular or Extended channel
2. **Configure maintenance windows** on all clusters for predictable timing
3. **Review workload readiness:** PDBs, deprecated APIs, StatefulSet backups

### Phase 2: January 2025 (Before EoS)
4. **Test 1.31 upgrade** on dev/staging clusters first
5. **Execute production upgrades** during planned maintenance windows
6. **Use skip-level upgrades** where possible (1.30→1.32) to reduce upgrade cycles

### Phase 3: Monitor & Validate
7. **Track upgrade progress:** `gcloud container operations list`
8. **Validate post-upgrade:** All workloads healthy, no API compatibility issues
9. **Document lessons learned** for future upgrade cycles

## Key Considerations

**API Compatibility:** Check for deprecated API usage before upgrading:
```bash
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
```

**Version Availability:** Verify 1.31 is available in your channels:
```bash
gcloud container get-server-config --region REGION --format="yaml(channels)"
```

**Multi-Cluster Sequencing:** If you have dev→staging→prod environments, ensure they upgrade in sequence. Consider rollout sequencing for automated coordination.

**Extended Channel Cost:** Additional charges only apply during the extended support period (March 2025-2026), not before.

The bottom line: **The Extended channel clusters have the most flexibility** (extra 12 months), the **Regular channel clusters need action by March 2025**, and the **"No channel" cluster should be migrated immediately** to gain proper upgrade controls.
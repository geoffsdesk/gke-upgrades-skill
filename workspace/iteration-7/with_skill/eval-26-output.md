# GKE 1.30 End of Support Impact & Preparation Plan

## EoS Enforcement by Cluster Type

### Regular Channel Clusters (3 clusters)
**What happens:** Force-upgraded to 1.31 when 1.30 reaches EoS
- **Control plane:** Automatically upgraded to 1.31
- **Node pools:** Automatically upgraded to 1.31 
- **Timing:** Follows your maintenance windows but will override exclusions at EoS
- **No override available:** Even "no upgrades" exclusions are bypassed at EoS

### Extended Channel Clusters (2 clusters)  
**What happens:** **No forced upgrade** — you have flexibility
- **Support period:** Up to 24 months total (vs 14 months standard)
- **Minor upgrades:** NOT automatic on Extended — you must initiate them
- **Patches:** Still auto-applied for security
- **At 24-month limit:** Then force-upgraded like other channels

### Legacy "No Channel" Cluster (1 cluster)
**What happens:** Force-upgraded to 1.31 when 1.30 reaches EoS
- **Enforcement:** Systematic node-level EoS enforcement applies from 1.32 onward
- **Current 1.30:** Will be force-upgraded as part of legacy cleanup
- **Timing:** Less predictable than release channel clusters

## Your Preparation Options

### Option 1: Proactive Manual Upgrade (Recommended)
Upgrade before EoS hits to maintain control over timing and sequencing.

```bash
# Check current versions and available targets
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, releaseChannel.channel)"

# Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.31.X-gke.Y

# Then upgrade node pools (can skip-level to save time)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.X-gke.Y
```

### Option 2: Migrate Legacy Cluster to Extended Channel
Your "No channel" cluster should be migrated to Extended for maximum flexibility.

```bash
# Migrate to Extended channel
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

**Why Extended over Regular/Stable for this cluster:**
- Gives you up to 24 months on each version
- Minor upgrades are manual (you control when)
- Only patches are auto-applied
- More flexibility around EoS timing

### Option 3: Use Maintenance Exclusions for Timing Control
Apply exclusions to defer automatic upgrades during critical periods.

```bash
# "No minor or node upgrades" - allows CP patches, blocks disruptive changes
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "pre-eos-planning" \
  --add-maintenance-exclusion-start-time "2024-MM-DDTHH:MM:SSZ" \
  --add-maintenance-exclusion-end-time "2024-MM-DDTHH:MM:SSZ" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

**Important:** Even "no upgrades" exclusions are bypassed at EoS. Use exclusions for timing, not to avoid upgrades indefinitely.

## Upgrade Strategy by Environment

### Regular Channel Clusters
```markdown
Upgrade Plan - Regular Channel (3 clusters)
- [ ] Target version: 1.31.3-gke.1535000+ (current Regular default)
- [ ] Sequence: Dev → Staging → Prod with 1-week soak time
- [ ] Maintenance windows: Configure for low-traffic periods
- [ ] Node pools: Use skip-level upgrades (1.30→1.31 direct) to reduce disruption
```

### Extended Channel Clusters  
```markdown
Extended Channel Strategy (2 clusters)
- [ ] Advantage: No forced minor upgrades - you control timing
- [ ] Current: Stay on 1.30 until you're ready (up to 24 months total)
- [ ] Planning: Schedule manual upgrade to 1.31 when convenient
- [ ] Note: Patches still auto-apply for security
```

### Legacy "No Channel" Cluster
```markdown
Legacy Cluster Migration (1 cluster)
- [ ] Priority: Migrate to Extended channel first
- [ ] Reason: Better upgrade controls than staying on "No channel"
- [ ] Timeline: Migrate channel, then plan 1.31 upgrade
- [ ] Benefit: Gains access to "no minor or node upgrades" exclusion type
```

## Pre-Upgrade Checklist for 1.30→1.31

```markdown
1.30→1.31 Compatibility Checks
- [ ] Deprecated APIs: Check for v1beta1 CronJob usage (removed in 1.31)
- [ ] GKE release notes: Review 1.31 breaking changes
- [ ] Third-party operators: Verify Istio/Prometheus/etc compatibility with 1.31
- [ ] PDBs: Ensure not overly restrictive (common drain blocker)
- [ ] Resource requests: All containers have requests/limits (mandatory for Autopilot)
```

## Timeline Recommendations

**Immediate (next 2 weeks):**
1. Migrate "No channel" cluster to Extended channel
2. Check 1.31 compatibility for critical workloads
3. Configure maintenance windows for all clusters

**Before EoS (4-6 weeks lead time):**
1. Upgrade dev/staging clusters to 1.31 for validation
2. Apply maintenance exclusions if you need to control exact timing
3. Plan production upgrade sequence

**Extended channel clusters:**
- Take advantage of the flexibility — upgrade when convenient
- Monitor for patches but no rush on minor version

## Monitoring EoS Approach

```bash
# Check auto-upgrade target and timeline
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(autopilot.upgradeSettings,releaseChannel)"

# Enable 72-hour advance notifications
# (Configure in Cloud Logging, filter for GKE upgrade notifications)
```

The key insight: **Extended channel clusters give you the most control** — they won't be force-upgraded at standard EoS timing. Consider migrating your legacy cluster there and using Extended for any future clusters where you want maximum upgrade flexibility.
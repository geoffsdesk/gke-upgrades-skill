# GKE 1.30 End of Support - Impact Analysis & Preparation Plan

## EoS Impact by Configuration

### Regular Channel Clusters (3 clusters)
**What happens:** Automatic force-upgrade to 1.31 when 1.30 reaches EoS
- Control plane upgrades first, then all node pools follow
- Upgrade timing respects your maintenance windows but CANNOT be indefinitely delayed
- Both control plane and nodes will be upgraded to the next supported minor (1.31)

### Extended Channel Clusters (2 clusters)  
**What happens:** No immediate action - you have breathing room
- Extended channel provides up to 24 months of support for 1.30 (vs standard 14 months)
- **Important:** Minor version upgrades are NOT automated on Extended channel
- You'll get security patches automatically, but you must manually upgrade to 1.31 before extended support expires
- Additional cost applies only during the extended support period (months 15-24)

### Legacy "No Channel" Cluster (1 cluster)
**What happens:** Systematic force-upgrade enforcement
- Control plane: Auto-upgraded to 1.31 at EoS
- Node pools: Force-upgraded even if "no auto-upgrade" is configured
- **No escape:** The 30-day "no upgrades" exclusion is your only temporary deferral option

## Your Preparation Options

### Option 1: Proactive Manual Upgrades (Recommended)
Get ahead of the EoS deadline by upgrading on your schedule:

**For Regular channel clusters:**
```bash
# Check current auto-upgrade targets
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Upgrade control plane to 1.31
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.31.x-gke.xxxx

# Upgrade node pools (can skip-level from 1.30→1.32 if desired)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxxx
```

**For Extended channel clusters:**
- You MUST manually upgrade - no auto-upgrade for minor versions
- Plan your upgrade timeline before extended support expires
- Same commands as above, but entirely your responsibility to initiate

**For "No channel" cluster:**
- **Strongly recommend migrating to Regular channel first:**
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular
```
- This gives you better upgrade controls (maintenance exclusions, rollout sequencing)

### Option 2: Controlled Auto-Upgrade Timing
Use maintenance controls to manage WHEN the forced upgrade happens:

**Set maintenance windows for predictable timing:**
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start 2024-12-07T02:00:00Z \
  --maintenance-window-end 2024-12-07T06:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Use maintenance exclusions for temporary deferrals:**
```bash
# "No minor or node upgrades" - blocks disruptive changes, allows CP patches
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "holiday-freeze" \
  --add-maintenance-exclusion-start-time 2024-12-15T00:00:00Z \
  --add-maintenance-exclusion-end-time 2025-01-15T00:00:00Z \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# "No upgrades" - blocks everything for up to 30 days (emergency only)
# This works even AFTER EoS for temporary deferral
```

### Option 3: Extended Channel Migration
For clusters needing maximum flexibility around EoS:

```bash
# Migrate Regular → Extended for longer planning runway
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

**Benefits:**
- Up to 24 months of support instead of 14
- No forced minor upgrades (but YOU must manage the upgrade lifecycle)
- Better than "No channel" because you get modern maintenance exclusion types

**Tradeoffs:**
- Additional cost during extended support period
- Manual upgrade responsibility - no auto-upgrade safety net

## Immediate Action Plan

### Week 1: Assessment
- [ ] Check exact 1.30 EoS date: `gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION`
- [ ] Review GKE 1.31+ release notes for breaking changes
- [ ] Test 1.31 upgrade in dev/staging environment
- [ ] Audit deprecated API usage: check GKE deprecation insights dashboard

### Week 2-3: "No Channel" Migration
- [ ] **Priority:** Migrate your "No channel" cluster to Regular channel
- [ ] Configure maintenance windows aligned with your change management
- [ ] Set up "no minor or node upgrades" exclusion if you need tight control

### Week 4+: Upgrade Execution
**Recommended sequence:**
1. **Extended channel clusters:** Plan manual upgrades within your timeline
2. **Regular channel clusters:** Either upgrade proactively or ensure maintenance windows are set
3. **Former "No channel":** Now follows Regular channel behavior

## Key Gotchas to Avoid

1. **Extended channel assumption:** Many assume Extended = automatic upgrades with longer runway. **Wrong.** You must manually upgrade minor versions on Extended.

2. **"No channel" control illusion:** The "no auto-upgrade" setting on "No channel" does NOT prevent EoS enforcement. Node pools get force-upgraded regardless.

3. **Version skew limits:** Node pools must stay within 2 minor versions of control plane. If CP is force-upgraded to 1.31, nodes on 1.28 would be out of skew.

4. **PDB timeout:** During forced upgrades, GKE respects PDBs for up to 1 hour, then may force-drain. Ensure PDBs aren't overly restrictive.

## Questions to Clarify Your Strategy

1. **Risk tolerance:** Can you tolerate force-upgrades during business hours, or do you need tight control over timing?
2. **Workload sensitivity:** Any long-running training jobs, stateful databases, or GPU workloads that need special handling?
3. **Upgrade cadence preference:** Want to stay current automatically (Regular channel), or prefer manual control (Extended channel)?

**Bottom line:** Your Regular channel clusters will auto-upgrade at EoS whether you like it or not. Your Extended channel clusters won't auto-upgrade minor versions ever - you must drive that. Your "No channel" cluster should be migrated to a release channel for better control tools before EoS hits.

Would you like me to produce specific upgrade runbooks for any of these clusters, or help you choose the best strategy for each environment?
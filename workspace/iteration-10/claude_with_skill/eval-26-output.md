# GKE 1.30 End of Support Action Plan

## Current State Analysis

| Cluster Type | Count | Current EoS Behavior | Action Required |
|--------------|-------|---------------------|-----------------|
| **Regular channel** | 3 | Auto-upgrade to 1.31 at EoS | Configure maintenance controls |
| **Extended channel** | 2 | **No auto-upgrade until end of extended support** | Manual upgrade planning needed |
| **Legacy "No channel"** | 1 | Force-upgrade to 1.31 at EoS | **High priority** - migrate to release channel |

## What Happens at 1.30 EoS

### Regular Channel Clusters (3 clusters)
- **Automatic upgrade to 1.31** when 1.30 reaches End of Support
- Both control plane AND node pools upgraded together
- Upgrade timing follows your maintenance windows (if configured)
- Can be delayed with maintenance exclusions (see options below)

### Extended Channel Clusters (2 clusters) 
- **No automatic upgrade** - Extended channel extends support up to 24 months
- You get additional time but must **manually upgrade before end of extended support**
- Still receive security patches during extended support period
- ⚠️ **Key point**: Minor version upgrades are NOT automated on Extended - you must initiate them

### Legacy "No Channel" Cluster (1 cluster)
- **Force-upgrade to 1.31** at EoS - no way to avoid except temporary exclusions
- Missing critical upgrade controls available in release channels
- **Strongly recommend migrating** to a release channel before EoS

## Recommended Action Plan

### Immediate Actions (Next 2 weeks)

#### 1. Migrate "No Channel" cluster to Regular channel
```bash
# Check current status
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(releaseChannel.channel,currentMasterVersion)"

# Migrate to Regular channel (closest to current behavior)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular
```

**Why Regular over Extended?** Regular provides the automated lifecycle you're used to, with better upgrade controls than "No channel."

#### 2. Configure maintenance controls for all clusters

**For maximum control (recommended):**
```bash
# Add "no minor or node upgrades" exclusion - allows CP security patches, blocks disruptive changes
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "controlled-upgrades-2024" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Set maintenance windows:**
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-MM-DDTHH:MM:SSZ" \
  --maintenance-window-end "2024-MM-DDTHH:MM:SSZ" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### Medium-term Planning (Next 1-2 months)

#### Extended Channel Strategy
Since your Extended channel clusters won't auto-upgrade, you need to plan manual upgrades:

1. **Test 1.31 compatibility** in a staging environment
2. **Schedule manual upgrades** during maintenance windows:
```bash
# Control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.31.x-gke.xxxx

# Then node pools (can skip-level upgrade from 1.30→1.31)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.xxxx
```

#### Regular Channel Strategy
For your Regular channel clusters, you have these options:

**Option A: Let auto-upgrade happen (recommended for most)**
- Configure maintenance windows for predictable timing
- Use "no minor or node upgrades" exclusion if you need to delay
- Remove exclusion when ready to upgrade

**Option B: Upgrade proactively**
- Manually upgrade to 1.31 before auto-upgrade kicks in
- Gives you more control over timing
- Same commands as Extended channel above

## Upgrade Control Options Summary

| Control Method | Max Duration | What it blocks | Best for |
|----------------|--------------|----------------|----------|
| **"No upgrades" exclusion** | 30 days | ALL upgrades (patches, minor, nodes) | Code freezes, critical periods |
| **"No minor or node upgrades"** | Until EoS | Minor + node upgrades, allows CP patches | Maximum control while staying secure |
| **"No minor upgrades"** | Until EoS | Minor upgrades only, allows patches + node upgrades | Teams comfortable with node churn |

## Pre-Upgrade Checklist Template

```markdown
- [ ] Cluster: ___ | Channel: ___ | Current: 1.30.x | Target: 1.31.x

Compatibility
- [ ] Test 1.31 in staging environment
- [ ] Check deprecated API usage (GKE deprecation insights dashboard)
- [ ] Review 1.30→1.31 release notes for breaking changes
- [ ] Verify third-party operators compatible with 1.31

Workload Readiness
- [ ] PDBs configured (not overly restrictive)
- [ ] No bare pods - all managed by controllers
- [ ] Adequate terminationGracePeriodSeconds
- [ ] Resource requests set (mandatory for Autopilot)
- [ ] Backup stateful workloads

Infrastructure
- [ ] Node pool upgrade strategy: surge vs blue-green
- [ ] Maintenance windows configured
- [ ] Sufficient quota for surge nodes
- [ ] Monitoring baseline captured
```

## Timeline Recommendations

1. **Week 1**: Migrate "No channel" cluster, configure maintenance windows
2. **Week 2-3**: Set up maintenance exclusions, test 1.31 in staging
3. **Week 4-6**: Plan and execute upgrades during maintenance windows
4. **Extended clusters**: Manual upgrade within 2-3 months (no rush due to extended support)

## Key Takeaways

- **Regular channel clusters**: Will auto-upgrade unless you configure exclusions
- **Extended channel clusters**: Won't auto-upgrade - you must plan manual upgrades
- **"No channel" cluster**: **High priority** to migrate - lacks modern upgrade controls
- **All clusters**: Should have maintenance windows and exclusions configured for predictable timing

Would you like me to generate specific runbooks for any of these clusters, or help you plan the upgrade sequence across your environment?
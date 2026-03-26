# GKE 1.30 End of Support Impact Analysis

Based on your cluster configuration, here's exactly what will happen to each cluster type when GKE 1.30 reaches End of Support:

## Impact by Channel Type

### Regular Channel Clusters (3 clusters)
**What happens:** Automatic force-upgrade to 1.31 (next supported minor version)
- **Control plane:** Upgraded automatically to 1.31
- **Node pools:** Upgraded automatically to 1.31
- **Timing:** Follows Regular channel's auto-upgrade schedule
- **Control:** Respects maintenance windows and exclusions (except "no upgrades" which is limited to 30 days)

### Extended Channel Clusters (2 clusters)
**What happens:** NO automatic force-upgrade at 1.30 EoS
- **Control plane:** Remains at 1.30 until end of **extended support** (up to 24 months total)
- **Node pools:** Remain at 1.30 until end of extended support
- **Cost impact:** Additional charges apply ONLY during the extended support period (months 15-24)
- **Manual upgrades:** You must plan and execute minor version upgrades yourself (patches are still auto-applied)

### Legacy "No Channel" Cluster (1 cluster)
**What happens:** Systematic force-upgrade enforcement
- **Control plane:** Force-upgraded to 1.31 at EoS
- **Node pools:** Force-upgraded even if auto-upgrade is disabled per-nodepool
- **No exceptions:** The 30-day "no upgrades" exclusion is the only temporary deferral available

## Timeline and Preparation Options

### Check Current EoS Status
```bash
# Check exact EoS dates for your clusters
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Check GKE release schedule for 1.30 EoS timeline
# Visit: https://cloud.google.com/kubernetes-engine/docs/release-schedule
```

### Recommended Actions by Cluster Type

#### For Regular Channel Clusters (Proactive Control)
**Option 1 — Let auto-upgrade handle it (recommended for most)**
```bash
# Ensure maintenance windows are configured for acceptable timing
gcloud container clusters update CLUSTER_NAME \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Option 2 — Manual upgrade ahead of EoS (for control)**
```bash
# Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --master \
  --cluster-version 1.31.X-gke.XXXX

# Then upgrade node pools (can skip-level 1.30→1.31)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --cluster-version 1.31.X-gke.XXXX
```

**Option 3 — Defer with exclusion (temporary, 30 days max)**
```bash
gcloud container clusters update CLUSTER_NAME \
  --add-maintenance-exclusion-name "defer-eos-upgrade" \
  --add-maintenance-exclusion-start-time "2024-12-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

#### For Extended Channel Clusters (Manual Planning Required)
**Key insight:** Extended channel does NOT auto-upgrade minor versions. You must plan these upgrades yourself.

```bash
# Check when 1.31 becomes available in Extended channel
gcloud container get-server-config --region REGION \
  --format="yaml(channels.EXTENDED)"

# Manual upgrade when ready (before end of extended support)
gcloud container clusters upgrade CLUSTER_NAME \
  --master \
  --cluster-version 1.31.X-gke.XXXX
```

**Planning considerations:**
- Extended support for 1.30 ends ~24 months after initial release
- You'll pay additional costs during months 15-24 only
- Plan internal processes for manual minor version upgrades
- Security patches continue automatically throughout

#### For Legacy "No Channel" Cluster (Migrate First)
**Strongly recommend:** Migrate to Regular channel before EoS enforcement
```bash
# Migrate to Regular channel (closest to current behavior)
gcloud container clusters update CLUSTER_NAME \
  --release-channel regular

# Or migrate to Extended for maximum flexibility
gcloud container clusters update CLUSTER_NAME \
  --release-channel extended
```

**Why migrate:** "No channel" lacks modern upgrade control features:
- No "no minor upgrades" exclusions (only 30-day "no upgrades")
- No persistent exclusions that track EoS
- Limited rollout sequencing options
- No extended support availability

## Pre-Upgrade Checklist for All Clusters

```markdown
## 1.30 → 1.31 Upgrade Preparation
- [ ] Review GKE 1.31 release notes for breaking changes
- [ ] Check deprecated API usage: `kubectl get --raw /metrics | grep deprecated`
- [ ] Verify third-party operators support Kubernetes 1.31
- [ ] Test workloads in staging cluster at 1.31
- [ ] Configure PDBs for critical workloads
- [ ] Back up StatefulSet data
- [ ] Set maintenance windows for acceptable upgrade timing
- [ ] Plan node pool surge settings (recommend 5% of pool size, maxUnavailable=0)
- [ ] Communicate upgrade timeline to stakeholders
```

## Monitoring and Alerting

Set up proactive notifications:
```bash
# Enable scheduled upgrade notifications (72h advance warning)
gcloud container clusters update CLUSTER_NAME \
  --send-scheduled-upgrade-notifications

# Monitor upgrade events in Cloud Logging
# Query: resource.type="gke_cluster" protoPayload.metadata.operationType="UPGRADE_MASTER"
```

## Summary Recommendations

1. **Regular channel clusters:** Configure maintenance windows, let auto-upgrade handle the transition
2. **Extended channel clusters:** Plan manual upgrade process, budget for extended support costs
3. **"No channel" cluster:** Migrate to Regular or Extended channel immediately for better control
4. **All clusters:** Test 1.31 compatibility in staging before production upgrades hit

The key insight: Extended channel gives you the most time and control, but requires manual planning. Regular channel automates the process with maintenance windows for timing control. Legacy "No channel" provides the least control and should be migrated.

Would you like me to create specific runbooks for any of these upgrade scenarios?
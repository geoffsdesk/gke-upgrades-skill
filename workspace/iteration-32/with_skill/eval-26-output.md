# GKE 1.30 End of Support Impact Analysis

## What happens at EoS for each cluster type

### Regular Channel Clusters (3 clusters)
**Behavior:** Systematic force-upgrade to 1.31 (next supported minor version)
- Control plane upgraded first, then all node pools
- No way to prevent this except temporary "no upgrades" exclusion (30-day max)
- Upgrade happens automatically when 1.30 reaches EoS date
- Standard 14-month support period applies

### Extended Channel Clusters (2 clusters)  
**Behavior:** No immediate forced upgrade
- Extended support continues until **up to 24 months** from 1.30's original GA date
- Only security patches auto-applied during extended period
- **Minor version upgrades are NOT automatic** - you control when to upgrade from 1.30
- Additional cost applies **only during the extended support period** (months 15-24)
- At end of extended support: systematic force-upgrade to next supported version

### Legacy "No Channel" Cluster (1 cluster)
**Behavior:** Same systematic force-upgrade as Regular channel
- Control plane and node pools upgraded to 1.31 at EoS
- "No auto-upgrade" per-nodepool settings are **ignored** during EoS enforcement
- Only the 30-day "no upgrades" exclusion can temporarily defer

## Timeline and Planning

**Current status:** 1.30 reached GA in May 2024, so standard support ends ~May 2025. Extended support available until ~May 2026.

**Key dates to track:**
- Standard EoS: ~May 2025 (affects Regular + No channel clusters)  
- Extended EoS: ~May 2026 (affects Extended channel clusters)
- Check exact dates: [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule)

## Recommended Actions by Cluster Type

### For Regular Channel Clusters (Urgent - ~3 months to prepare)

**Option 1 - Proactive manual upgrade (Recommended):**
```bash
# Check current auto-upgrade target
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Upgrade control plane to 1.31
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version 1.31.X-gke.Y

# Upgrade node pools
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.31.X-gke.Y
```

**Option 2 - Migrate to Extended channel:**
```bash
# Migrate to Extended for longer runway
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --release-channel extended
```
This gives you until ~May 2026 to upgrade, with control over minor version timing.

### For Extended Channel Clusters (Less urgent - ~1 year runway)

**Current state:** You have until ~May 2026 before forced upgrade
- Continue receiving 1.30 security patches automatically
- Plan manual upgrade to 1.31+ when ready
- Monitor for 1.31 availability in Extended channel

**When ready to upgrade:**
```bash
# Check available versions in Extended channel  
gcloud container get-server-config --region REGION \
  --format="yaml(channels.EXTENDED)"

# Manual upgrade when 1.31+ reaches Extended
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version 1.31.X-gke.Y
```

### For "No Channel" Cluster (Urgent - migrate first)

**Recommended approach - Migrate to Extended channel:**
```bash
# Step 1: Add temporary exclusion during migration
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "channel-migration" \
  --add-maintenance-exclusion-start $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end $(date -u -d '+1 day' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades

# Step 2: Migrate to Extended channel
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --release-channel extended

# Step 3: Remove temporary exclusion
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --remove-maintenance-exclusion "channel-migration"
```

This transforms your "No channel" cluster to Extended, giving you the same ~1 year runway as your Extended clusters.

## Pre-Upgrade Checklist for All Clusters

Before upgrading any cluster from 1.30 → 1.31:

```
- [ ] Check deprecated API usage: kubectl get --raw /metrics | grep deprecated
- [ ] Review 1.31 release notes for breaking changes
- [ ] Verify third-party operators support K8s 1.31
- [ ] Test in staging cluster first
- [ ] Configure appropriate PDBs for workloads
- [ ] Plan maintenance windows for production upgrades
- [ ] Take application-level backups for stateful workloads
```

## Upgrade Strategy Recommendations

**Staging-first approach:**
1. Upgrade staging/dev clusters to 1.31 immediately
2. Validate workload compatibility over 2-4 weeks  
3. Proceed with production once validated

**Staggered production approach:**
1. Extended channel clusters: defer until 1.31 proven stable (~6 months)
2. Regular channel clusters: upgrade soon to avoid forced upgrade
3. "No channel" cluster: migrate to Extended, then follow Extended timeline

## Cost Considerations

- **Extended channel:** Additional cost applies only during extended support period (months 15-24 after GA)
- **Migration timing:** Migrating Regular → Extended now avoids forced 1.30 upgrade and gives you control over 1.31 timing
- **No additional cost** during standard 14-month support period on Extended channel

## Summary Action Plan

**Immediate (next 2 weeks):**
- [ ] Migrate "No channel" cluster to Extended channel
- [ ] Plan 1.31 upgrade path for Regular channel clusters

**Next 1-2 months:**  
- [ ] Upgrade staging/dev Regular clusters to 1.31
- [ ] Validate workload compatibility

**Next 2-3 months:**
- [ ] Upgrade production Regular clusters to 1.31 (before forced upgrade)
- [ ] Plan Extended cluster upgrade timeline (can defer up to 1 year)

This approach gives you maximum control while avoiding forced upgrades and minimizing operational risk.
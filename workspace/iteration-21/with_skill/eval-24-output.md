# Legacy "No Channel" Migration Guide

## What You're Missing on "No Channel"

You're running a **legacy configuration** that lacks GKE's most powerful upgrade control features. Here's what you're missing compared to release channels:

| Feature | Release Channels | Your "No Channel" |
|---------|-----------------|-------------------|
| **"No minor or node upgrades" exclusion** | ✅ Available (cluster-level + per-nodepool) | ❌ **Missing** — only 30-day "no upgrades" available |
| **"No minor upgrades" exclusion** | ✅ Available | ❌ **Missing** |
| **Extended support (24 months)** | ✅ Available | ❌ **Missing** |
| **Rollout sequencing** (fleet coordination) | ✅ Available | ❌ **Missing** |
| **Persistent exclusions** (auto-renew at EoS) | ✅ Available | ❌ **Missing** |
| **Granular auto-upgrade control** | Full (windows + exclusions + intervals) | Limited |
| **Channel-specific maintenance exclusion scopes** | ✅ Full range | ❌ **Only "no upgrades" (30-day max)** |

**Key insight:** The most powerful upgrade control tools are ONLY available on release channels. Staying on "No channel" gives you LESS control, not more.

## Your Current EoS Risk

- **Legacy "No channel" EoS enforcement:** When versions reach End of Support, control plane AND node pools are force-upgraded to the next minor version — even with "no auto-upgrade" configured on node pools
- **No escape mechanism:** Only the 30-day "no upgrades" exclusion can defer EoS enforcement, but you can only chain 3 exclusions maximum
- **Version 1.31 timeline:** Check the [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) for 1.31's EoS date — you're vulnerable to forced upgrades

## Recommended Migration Path

### Target Configuration: Regular Channel + Maintenance Exclusions

This gives you maximum control while maintaining automated security patches:

```bash
# Migrate each cluster to Regular channel (closest to "No channel" behavior)
gcloud container clusters update CLUSTER_NAME \
    --region REGION \
    --release-channel regular

# Add persistent "no minor or node upgrades" exclusion
gcloud container clusters update CLUSTER_NAME \
    --region REGION \
    --add-maintenance-exclusion-name "production-stability" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support

# Configure maintenance window for predictable patch timing
gcloud container clusters update CLUSTER_NAME \
    --region REGION \
    --maintenance-window-start "2026-01-01T02:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**What this gives you:**
- **Control plane security patches** applied automatically during maintenance windows
- **No automatic minor version upgrades** — you control when they happen
- **No automatic node pool upgrades** — you control when they happen
- **Exclusion auto-renews** when new minor versions are adopted
- **No 30-day limit** on exclusions (tracks EoS automatically)

### Alternative: Extended Channel (Maximum Control)

For ultimate flexibility around EoS enforcement:

```bash
gcloud container clusters update CLUSTER_NAME \
    --region REGION \
    --release-channel extended
```

**Extended channel benefits:**
- **24 months of support** (vs standard 14 months)
- **No automatic minor upgrades** except at end of extended support
- **Only patches auto-applied** — gives you manual control over minor timing
- **Additional cost only during extended period** (months 15-24)

## Migration Execution Plan

### Phase 1: Pre-Migration Assessment (Week 1)
```markdown
- [ ] Audit all 8 clusters: versions, node pools, current exclusions
- [ ] Document existing per-nodepool "no auto-upgrade" settings
- [ ] Check which clusters have maintenance windows configured
- [ ] Verify no clusters are approaching 1.31 EoS
- [ ] Choose target channel (Regular vs Extended) per cluster
```

Commands for assessment:
```bash
# List all clusters with versions and channels
gcloud container clusters list --format="table(name,location,currentMasterVersion,releaseChannel.channel,nodePools[].version)"

# Check existing maintenance exclusions
for cluster in CLUSTER1 CLUSTER2; do
  echo "=== $cluster ==="
  gcloud container clusters describe $cluster --region REGION --format="yaml(maintenancePolicy)"
done
```

### Phase 2: Dev/Staging Migration (Week 2)
Migrate 2-3 non-production clusters first:

```bash
# Before migration - add temporary "no upgrades" exclusion
gcloud container clusters update DEV_CLUSTER \
    --region REGION \
    --add-maintenance-exclusion-name "migration-freeze" \
    --add-maintenance-exclusion-start-time "2025-01-15T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2025-01-22T00:00:00Z" \
    --add-maintenance-exclusion-scope no_upgrades

# Migrate to Regular channel
gcloud container clusters update DEV_CLUSTER \
    --region REGION \
    --release-channel regular

# Configure new exclusion model
gcloud container clusters update DEV_CLUSTER \
    --region REGION \
    --add-maintenance-exclusion-name "dev-stability" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support

# Remove temporary exclusion
gcloud container clusters update DEV_CLUSTER \
    --region REGION \
    --remove-maintenance-exclusion-name "migration-freeze"
```

**Validation:**
- Verify auto-upgrade target changed: `gcloud container clusters get-upgrade-info DEV_CLUSTER --region REGION`
- Confirm exclusions active: `gcloud container clusters describe DEV_CLUSTER --format="yaml(maintenancePolicy)"`

### Phase 3: Production Migration (Week 3-4)
Migrate production clusters during maintenance windows:

```bash
# Production clusters - use more conservative approach
gcloud container clusters update PROD_CLUSTER \
    --region REGION \
    --release-channel regular \
    --add-maintenance-exclusion-name "prod-stability" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support \
    --maintenance-window-start "2026-01-01T02:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## Multi-Cluster Upgrade Strategy (Post-Migration)

With all clusters on Regular channel + "no minor or node" exclusions:

### Progressive Manual Minor Upgrades
```bash
# When new minor version (e.g., 1.32) becomes available in Regular:

# 1. Dev clusters first
gcloud container clusters upgrade DEV_CLUSTER1 \
    --region REGION \
    --master \
    --cluster-version 1.32.x-gke.latest

# Wait 3-5 days, validate workloads

# 2. Staging clusters
gcloud container clusters upgrade STAGING_CLUSTER \
    --region REGION \
    --master \
    --cluster-version 1.32.x-gke.latest

# Wait 1 week, validate integration tests

# 3. Production clusters (staggered)
gcloud container clusters upgrade PROD_CLUSTER1 \
    --region REGION \
    --master \
    --cluster-version 1.32.x-gke.latest

# Wait 48 hours between prod clusters
```

### Node Pool Upgrades
```bash
# After control plane upgrade, upgrade node pools with skip-level jumps
gcloud container node-pools upgrade POOL_NAME \
    --cluster PROD_CLUSTER1 \
    --region REGION \
    --cluster-version 1.32.x-gke.latest

# Configure conservative surge settings for production
gcloud container node-pools update POOL_NAME \
    --cluster PROD_CLUSTER1 \
    --region REGION \
    --max-surge-upgrade 1 \
    --max-unavailable-upgrade 0
```

## Migration Checklist

```markdown
Migration Readiness Checklist

Pre-Migration
- [ ] All clusters documented: names, regions, versions, node pools
- [ ] Current maintenance exclusions backed up
- [ ] Target channel selected per cluster (Regular vs Extended)
- [ ] Migration scheduled during maintenance windows
- [ ] Stakeholders notified of change in upgrade behavior

Migration Execution  
- [ ] Apply temporary "no upgrades" exclusion before channel change
- [ ] Migrate to target channel (Regular/Extended)
- [ ] Configure new exclusion model ("no minor or node upgrades")
- [ ] Set up maintenance windows for predictable patch timing
- [ ] Remove temporary exclusion
- [ ] Validate auto-upgrade targets and exclusion status

Post-Migration
- [ ] Document new manual minor upgrade process
- [ ] Set up monitoring for version drift across environments
- [ ] Schedule first manual minor upgrade cycle
- [ ] Update runbooks and team documentation
- [ ] Configure GKE release schedule monitoring
```

## Key Benefits After Migration

1. **Better EoS protection:** Extended timeline + persistent exclusions that auto-renew
2. **Security posture:** Automatic control plane patches while controlling disruptive changes
3. **Progressive rollout capability:** Manual minor upgrades with proper dev→staging→prod sequencing
4. **Future-proofing:** Access to rollout sequencing, disruption intervals, and other advanced features
5. **Cost optimization:** Extended channel available for maximum flexibility (cost only during extended period)

## Timeline

- **Week 1:** Assessment and planning
- **Week 2:** Dev/staging migration and validation  
- **Week 3-4:** Production migration during maintenance windows
- **Ongoing:** Manual minor upgrade cycles every 2-3 months

**Bottom line:** Migration to Regular channel + maintenance exclusions gives you MORE control than "No channel" while maintaining automated security patching. This is the recommended path for platform teams who need predictable, controlled upgrades.
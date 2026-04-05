# Channel Migration: Rapid → Stable

## Key Implications

**⚠️ Critical Warning: Version Compatibility**
Moving from Rapid (1.32) to Stable when 1.32 is not yet available in Stable will freeze your cluster at 1.32 indefinitely. You'll receive patches but NO minor version upgrades until Stable's version progression reaches 1.32, then you resume normal auto-upgrades.

**Check version availability first:**
```bash
gcloud container get-server-config --zone YOUR_ZONE --format="yaml(channels)"
```

Look for 1.32 in the Stable channel's available versions. If it's not there yet, you have two options:

## Migration Options

### Option 1: Immediate Migration (if 1.32 is available in Stable)
```bash
# Add temporary exclusion to prevent immediate auto-upgrade
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "channel-migration" \
  --add-maintenance-exclusion-start-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-end-time "$(date -u -d '+7 days' +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-scope no_upgrades

# Migrate to Stable channel
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel stable

# Remove exclusion when ready for auto-upgrades
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "channel-migration"
```

### Option 2: Wait-and-migrate (if 1.32 not in Stable)
1. Stay on Rapid until Stable reaches 1.32 (~4-8 weeks typically)
2. Monitor the [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule)
3. Migrate when versions align

### Option 3: Downgrade first (if urgent migration needed)
```bash
# Downgrade to highest Stable version (e.g., 1.31)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.31.X-gke.XXXX  # Use latest 1.31 patch

# Then node pools
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.X-gke.XXXX

# Then migrate channel
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel stable
```

## Channel Differences Impact

| Aspect | Rapid (current) | Stable (target) | Impact |
|--------|----------------|-----------------|---------|
| **New versions arrive** | First (~2 weeks after K8s release) | Last (~6-10 weeks after Rapid) | Much slower access to new features |
| **Upgrade cadence** | Fastest | Slowest | Fewer disruptions, longer validation |
| **SLA coverage** | **No SLA for upgrade stability** | Full SLA | Higher stability guarantee |
| **Security patches** | First | Same timing as Regular | No delay on security fixes |
| **Production suitability** | Dev/test only | Production-ready | Appropriate for prod workloads |

**Key insight:** Rapid channel lacks SLA coverage for upgrade stability — versions may have issues caught before reaching Stable. This is the primary risk beyond timing.

## Recommended Migration Plan

### Phase 1: Pre-migration (now)
- [ ] Check if 1.32 is available in Stable channel
- [ ] If not available, set calendar reminder to check monthly
- [ ] Document current auto-upgrade behavior and maintenance windows
- [ ] Test upgrade procedures in a dev cluster on Stable channel

### Phase 2: Migration execution (when versions align)
```bash
# 1. Set maintenance exclusion during migration
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "channel-migration" \
  --add-maintenance-exclusion-start-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-end-time "$(date -u -d '+24 hours' +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-scope no_upgrades

# 2. Migrate channel
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel stable

# 3. Verify new channel
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(releaseChannel.channel)"

# 4. Check auto-upgrade target
gcloud container clusters get-upgrade-info CLUSTER_NAME \
  --zone ZONE

# 5. Remove exclusion when ready
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "channel-migration"
```

### Phase 3: Post-migration validation
- [ ] Verify no immediate auto-upgrade triggers
- [ ] Confirm maintenance windows still apply
- [ ] Monitor for ~1 week to ensure stable behavior
- [ ] Update documentation and runbooks for Stable channel cadence

## Alternative: Extended Channel Consideration

For production workloads wanting maximum control, consider **Extended channel** instead:
- Up to 24 months support (vs 14 months)
- Control plane minor upgrades are manual (not automatic)
- Only patches auto-apply
- Extra cost only during extended support period
- Better for compliance/regulated environments

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

## Timing Recommendation

**Best practice:** Wait for version alignment rather than downgrading. Moving from 1.32 on Rapid to 1.31 on Stable creates unnecessary disruption and temporarily puts you on an older version. The 4-8 week wait is typically worth avoiding the downgrade complexity.

**Monitor progress:** Check the [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) monthly for Stable channel version progression estimates.
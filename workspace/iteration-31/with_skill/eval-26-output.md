# GKE 1.30 End of Support Impact Analysis

## What will happen at EoS (March 2025)

**All clusters will be force-upgraded regardless of channel configuration.** EoS enforcement is systematic across all channels and "No channel" clusters.

### Your clusters by configuration:

**Regular channel clusters (3 clusters):**
- ✅ **Auto-upgraded before EoS** - These will upgrade to 1.31 automatically during maintenance windows
- Timeline: 1.31 became available in Regular in December 2024, auto-upgrade target by January 2025
- **Action needed:** Minimal - just monitor the auto-upgrades

**Extended channel clusters (2 clusters):**
- ⚠️ **Force-upgraded at EoS** - Extended delays EoS enforcement but doesn't prevent it
- Extended support for 1.30 ends March 2025 (same as standard support)
- **Key point:** Extended channel only provides longer support for versions 1.27+, but 1.30's extended period coincides with standard EoS
- **Action needed:** Plan manual upgrade or prepare for forced upgrade

**Legacy "No channel" cluster (1 cluster):**
- ⚠️ **Force-upgraded at EoS** - Same systematic enforcement applies
- Control plane and nodes both upgraded to 1.31
- Any per-nodepool "no auto-upgrade" settings will be overridden for EoS enforcement
- **Action needed:** Plan migration strategy

## Recommended preparation strategy

### Phase 1: Immediate (January 2025)
```bash
# Audit current state
gcloud container clusters list --format="table(name,location,currentMasterVersion,releaseChannel.channel,status)"

# Check upgrade targets and EoS dates
for cluster in $(gcloud container clusters list --format="value(name)"); do
  echo "=== $cluster ==="
  gcloud container clusters get-upgrade-info $cluster --region=REGION
done
```

### Phase 2: Extended and "No channel" clusters

**For Extended channel clusters:**
```bash
# Option A: Stay on Extended, plan manual upgrade
gcloud container clusters upgrade CLUSTER_NAME \
  --cluster-version=1.31.latest \
  --master

# Option B: Migrate to Regular for automatic lifecycle
gcloud container clusters update CLUSTER_NAME \
  --release-channel=regular
```

**For "No channel" cluster (highest priority):**
```bash
# Recommended: Migrate to Regular channel first
gcloud container clusters update CLUSTER_NAME \
  --release-channel=regular

# This enables modern maintenance controls:
# - "No minor or node upgrades" exclusions
# - Rollout sequencing capability  
# - Extended support options for future versions
```

### Phase 3: Risk mitigation

**Pre-upgrade checklist for all clusters:**
- [ ] Check deprecated API usage: `kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated`
- [ ] Review GKE deprecation insights in console
- [ ] Verify third-party operators support 1.31
- [ ] Configure PDBs for critical workloads
- [ ] Test application compatibility in staging

**Add maintenance exclusions if needed:**
```bash
# For clusters needing controlled timing (blocks auto-upgrade temporarily)
gcloud container clusters update CLUSTER_NAME \
  --add-maintenance-exclusion-name "planned-upgrade-window" \
  --add-maintenance-exclusion-start-time "2025-02-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-03-01T00:00:00Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

## Migration timeline recommendation

**Week 1 (Now):** 
- Migrate "No channel" cluster to Regular channel
- Verify Regular channel auto-upgrades are proceeding normally

**Week 2-3:**
- Decide Extended channel strategy: manual upgrade or migrate to Regular
- Apply maintenance exclusions if you need to control exact timing

**Week 4+ (Before March EoS):**
- Complete any manual upgrades
- Remove temporary maintenance exclusions
- Document lessons learned for future EoS events

## Key insights for future planning

1. **Extended channel advantage is for 1.27+ versions** - For 1.30, it doesn't provide longer support than standard
2. **"No channel" lacks modern controls** - Missing rollout sequencing, granular exclusions, and extended support options
3. **EoS enforcement is unavoidable** - Plan around it rather than trying to prevent it
4. **Auto-upgrade is the recommended path** - Release channels + maintenance windows provide better control than manual freezing

The Regular channel clusters are already handling this correctly. Focus your effort on migrating the "No channel" cluster and deciding the Extended channel strategy.
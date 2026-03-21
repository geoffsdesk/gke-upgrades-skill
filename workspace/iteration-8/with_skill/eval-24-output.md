# Legacy "No Channel" Migration Assessment & Plan

Your platform team is right to be concerned — staying on "No channel" means missing GKE's most powerful upgrade control features. Here's what you're losing and how to migrate.

## What You're Missing on "No Channel"

| Feature | Release channels | Your current "No channel" |
|---------|-----------------|----------------------------|
| **"No minor or node upgrades" exclusion** | ✅ Available (cluster-level + per-nodepool) | ❌ **Not available** — only basic 30-day "no upgrades" type |
| **"No minor upgrades" exclusion** | ✅ Available | ❌ **Not available** |
| **Per-nodepool maintenance exclusion granularity** | ✅ Full scope options | ❌ Limited to 30-day "no upgrades" only |
| **Extended support (24 months)** | ✅ Available for 1.27+ | ❌ **Not available** |
| **Rollout sequencing** (fleet coordination) | ✅ Available | ❌ **Not available** |
| **Persistent exclusions** (auto-tracks EoS) | ✅ Available with `--add-maintenance-exclusion-until-end-of-support` | ❌ **Not available** |
| **Granular disruption interval control** | ✅ Full control (patch + minor intervals) | ❌ Limited |

**The key insight:** The most advanced upgrade control tools are ONLY available on release channels. "No channel" doesn't give you more control — it gives you less.

## Your Current EoS Risk

Since you're on 1.31 "No channel":
- **1.31 End of Support:** ~March 2025 (check current GKE release schedule)
- **Forced upgrade behavior:** When 1.31 hits EoS, your clusters will be force-upgraded to 1.32
- **Your only defense:** 30-day "no upgrades" exclusion (can delay but not prevent)
- **Missing protection:** You can't use "no minor upgrades" exclusion to allow security patches while blocking the minor version bump

## Recommended Migration Strategy

### Phase 1: Immediate Assessment (Week 1)

```bash
# Check current auto-upgrade targets for all 8 clusters
for cluster in cluster1 cluster2 cluster3 cluster4 cluster5 cluster6 cluster7 cluster8; do
  echo "=== $cluster ==="
  gcloud container clusters get-upgrade-info $cluster --region REGION --format="table(name,autoUpgradeStatus,endOfStandardSupportTimestamp,minorTargetVersion,patchTargetVersion)"
done

# Verify maintenance exclusions currently active
for cluster in cluster1 cluster2 cluster3 cluster4 cluster5 cluster6 cluster7 cluster8; do
  echo "=== $cluster ==="
  gcloud container clusters describe $cluster --region REGION --format="value(maintenancePolicy.window,maintenancePolicy.resourceVersion)"
done
```

### Phase 2: Migration to Release Channels (Weeks 2-4)

**Target channel recommendation:** **Regular** or **Extended**
- **Regular:** Closest to your current "No channel" behavior, full SLA
- **Extended:** If you want maximum flexibility around EoS enforcement (minor upgrades NOT automated, 24-month support available)

**Migration sequence (per cluster):**

```bash
# Step 1: Apply temporary protection BEFORE channel migration
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "channel-migration-protection" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time $(date -u -d "+30 days" +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-scope no_upgrades

# Step 2: Migrate to Regular channel
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --release-channel regular

# Step 3: Replace with proper channel-based exclusion
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --remove-maintenance-exclusion-name "channel-migration-protection" \
  --add-maintenance-exclusion-name "production-control" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-until-end-of-support \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Step 4: Configure maintenance windows
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-window-start 2024-12-15T02:00:00Z \
  --maintenance-window-end 2024-12-15T06:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"
```

**Important migration note:** When migrating from "No channel" with existing maintenance exclusions, only exclusions of type "no_upgrades" translate between the configurations. Your current exclusions may be ignored after migration — that's why we apply the temporary protection first.

### Phase 3: Implement Advanced Controls (Weeks 3-6)

With release channels, you now have access to powerful new controls:

**1. Granular exclusion strategy:**
```bash
# Option A: Allow security patches, block disruptive changes (recommended)
--add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Option B: Allow patches + node upgrades, block minor versions only
--add-maintenance-exclusion-scope no_minor_upgrades

# Option C: Block everything during critical periods (code freeze, BFCM)
--add-maintenance-exclusion-scope no_upgrades  # 30-day max
```

**2. Disruption interval tuning:**
```bash
# Slow down patch frequency (default 7 days → 30 days)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-patch-version-disruption-interval 30d

# Slow down minor frequency (default 30 days → 90 days)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-minor-version-disruption-interval 90d
```

**3. Rollout sequencing (if desired):**
```bash
# Example: Dev → Staging → Prod progression with 7-day soak
gcloud container clusters update prod-cluster \
  --region REGION \
  --rollout-sequencing-enabled \
  --rollout-predecessors dev-cluster,staging-cluster \
  --rollout-soak-time 7d
```

## Recommended Channel & Strategy by Environment

```
Dev clusters (2):     Regular channel + minimal exclusions
Staging clusters (2): Regular channel + "no minor" exclusions  
Prod clusters (4):    Regular channel + "no minor or node upgrades" exclusions
```

This gives you:
- **Dev:** Fast feedback on new versions
- **Staging:** Security patches but controlled minor upgrades
- **Prod:** Maximum control — only security patches auto-applied

## Extended Channel Alternative

If your team wants even more control, consider **Extended channel** for production:

```bash
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --release-channel extended
```

**Extended benefits:**
- Minor version upgrades are NOT automated (you initiate them)
- 24-month support available for 1.27+
- No extra cost during standard support period
- Better migration path from "No channel" mindset

**Extended considerations:**
- You must plan and execute minor upgrades proactively
- Extra cost during extended support period (months 15-24)
- Still get automatic patches

## Migration Timeline

```
Week 1: Assessment + planning
Week 2: Migrate dev clusters (test the process)
Week 3: Migrate staging clusters 
Week 4-5: Migrate production clusters (2 per week)
Week 6: Implement advanced controls (rollout sequencing, disruption intervals)
```

## Immediate Action Items

1. **Check EoS dates** — 1.31 support ends soon
2. **Choose target channel** — Regular (recommended) or Extended
3. **Start with non-prod** — test the migration process
4. **Document current exclusions** — they may not translate
5. **Plan maintenance windows** — you'll have better control post-migration

## Benefits You'll Gain

✅ **True upgrade control** — "no minor or node upgrades" exclusion blocks disruptive changes while allowing security patches  
✅ **No more forced minor upgrades** — persistent exclusions track EoS automatically  
✅ **Better fleet coordination** — rollout sequencing for multi-cluster environments  
✅ **Extended support option** — up to 24 months for compliance needs  
✅ **Granular disruption control** — separate intervals for patches vs minors  
✅ **Future-proof architecture** — new GKE features target release channels, not "No channel"  

The migration will solve your forced upgrade pain and give you the enterprise-grade lifecycle management your platform team needs.
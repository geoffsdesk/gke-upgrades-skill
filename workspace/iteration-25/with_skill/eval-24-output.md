# GKE Release Channel Migration Plan

## What You're Missing on "No Channel"

Your legacy "No channel" configuration is missing several **critical upgrade control features** that only exist on release channels:

| Feature | Release channels | No channel |
|---------|-----------------|------------|
| **"No minor or node upgrades" exclusion** | ✅ Yes (cluster-level + per-nodepool) | ❌ **No** — only the 30-day "no upgrades" type is available |
| **"No minor upgrades" exclusion** | ✅ Yes | ❌ **No** |
| **Extended support (24 months)** | ✅ Yes | ❌ **No** |
| **Rollout sequencing** | ✅ Yes (advanced) | ❌ **No** |
| **Persistent exclusions (tracks EoS)** | ✅ Yes | ❌ **No** |
| **Granular auto-upgrade control** | ✅ Full (windows + exclusions + intervals) | ❌ Limited |

**Key insight:** The most powerful upgrade control tools are **only available on release channels**. "No channel" actually gives you LESS control, not more.

## Current Pain Points You're Experiencing

1. **EoS enforcement is systematic regardless of channel** — when 1.31 reaches End of Support, your clusters will be force-upgraded to 1.32 even on "No channel"
2. **Limited exclusion types** — you can only use 30-day "no upgrades" exclusions, which don't track EoS dates
3. **No minor-only control** — you can't block minor upgrades while allowing patches
4. **No fleet coordination** — each cluster upgrades independently with no sequencing

## Migration Strategy: "No Channel" → Release Channels

### Recommended Target: Regular Channel + Maintenance Controls

**Why Regular over Stable:**
- Regular provides the closest timing to your current "No channel" behavior
- Stable adds +2 weeks delay on security patches (may not align with security requirements)
- Extended requires manual minor upgrades (good for maximum control, but adds operational overhead)

### Migration Steps

#### Phase 1: Prepare for Migration (Week 1)
```bash
# 1. Audit current cluster versions
for cluster in cluster1 cluster2 cluster3 cluster4 cluster5 cluster6 cluster7 cluster8; do
  echo "=== $cluster ==="
  gcloud container clusters describe $cluster --zone ZONE \
    --format="table(name, currentMasterVersion, nodePools[].version, nodePools[].name)"
done

# 2. Check version availability in Regular channel
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels.REGULAR.validVersions)"

# 3. Apply temporary "no upgrades" exclusion BEFORE channel migration
for cluster in cluster1 cluster2 cluster3 cluster4 cluster5 cluster6 cluster7 cluster8; do
  gcloud container clusters update $cluster --zone ZONE \
    --add-maintenance-exclusion-name "channel-migration-freeze" \
    --add-maintenance-exclusion-start $(date -u +%Y-%m-%dT%H:%M:%SZ) \
    --add-maintenance-exclusion-end $(date -u -d '+7 days' +%Y-%m-%dT%H:%M:%SZ) \
    --add-maintenance-exclusion-scope no_upgrades
done
```

#### Phase 2: Migrate to Regular Channel (Week 2)
```bash
# Migrate each cluster to Regular channel
for cluster in cluster1 cluster2 cluster3 cluster4 cluster5 cluster6 cluster7 cluster8; do
  echo "Migrating $cluster to Regular channel..."
  gcloud container clusters update $cluster --zone ZONE \
    --release-channel regular
done

# Verify migration
for cluster in cluster1 cluster2 cluster3 cluster4 cluster5 cluster6 cluster7 cluster8; do
  gcloud container clusters describe $cluster --zone ZONE \
    --format="value(releaseChannel.channel)"
done
```

#### Phase 3: Configure Advanced Upgrade Controls (Week 2-3)

**For maximum control (recommended for production clusters):**
```bash
# Replace temporary exclusion with persistent "no minor or node" exclusion
for cluster in prod-cluster1 prod-cluster2 prod-cluster3; do
  # Remove temporary exclusion
  gcloud container clusters update $cluster --zone ZONE \
    --remove-maintenance-exclusion "channel-migration-freeze"
  
  # Add persistent exclusion for maximum control
  gcloud container clusters update $cluster --zone ZONE \
    --add-maintenance-exclusion-name "production-control" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
done

# Set maintenance windows for production (example: Saturday 2-6 AM)
for cluster in prod-cluster1 prod-cluster2 prod-cluster3; do
  gcloud container clusters update $cluster --zone ZONE \
    --maintenance-window-start "2025-01-01T02:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
done
```

**For dev/staging clusters (allow auto-upgrades with timing control):**
```bash
# Remove temporary exclusion and allow auto-upgrades
for cluster in dev-cluster1 dev-cluster2 staging-cluster1 staging-cluster2; do
  gcloud container clusters update $cluster --zone ZONE \
    --remove-maintenance-exclusion "channel-migration-freeze"
  
  # Set maintenance windows (example: weekday nights)
  gcloud container clusters update $cluster --zone ZONE \
    --maintenance-window-start "2025-01-01T01:00:00Z" \
    --maintenance-window-duration 6h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=TU,WE,TH"
done
```

#### Phase 4: Implement Rollout Sequencing (Advanced - Optional)

If you want automated fleet-wide upgrade orchestration:
```bash
# Set up rollout sequencing: dev → staging → prod
# Dev fleet upgrades first
gcloud container fleet clusterupgrade update \
  --project DEV_PROJECT_ID \
  --default-upgrade-soaking 2d

# Staging fleet waits for dev
gcloud container fleet clusterupgrade update \
  --project STAGING_PROJECT_ID \
  --upstream-fleet projects/DEV_PROJECT_ID/locations/global/fleets/default \
  --default-upgrade-soaking 3d

# Prod fleet waits for staging
gcloud container fleet clusterupgrade update \
  --project PROD_PROJECT_ID \
  --upstream-fleet projects/STAGING_PROJECT_ID/locations/global/fleets/default \
  --default-upgrade-soaking 7d
```

## Recommended Architecture: Two-Tier Control Strategy

**Tier 1: Dev/Staging Clusters**
- **Channel:** Regular
- **Exclusions:** None (full auto-upgrade)
- **Maintenance windows:** Weeknight hours
- **Purpose:** Early validation of new versions

**Tier 2: Production Clusters**
- **Channel:** Regular
- **Exclusions:** "No minor or node upgrades" (persistent, tracks EoS)
- **Maintenance windows:** Weekend off-peak
- **Purpose:** Manual control over disruptive changes, auto-patches only

## New Capabilities You'll Gain

### 1. Granular Upgrade Control
```bash
# Block minor upgrades, allow patches (impossible on "No channel")
--add-maintenance-exclusion-scope no_minor_upgrades

# Block ALL node disruption, allow CP patches (maximum control)
--add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

### 2. Persistent Exclusions
```bash
# Exclusion automatically tracks EoS dates - no manual renewal needed
--add-maintenance-exclusion-until-end-of-support
```

### 3. Extended Support Option
```bash
# 24-month support for versions 1.27+ (costs extra only during extended period)
gcloud container clusters update CLUSTER --zone ZONE \
  --release-channel extended
```

### 4. Coordinated Fleet Upgrades
- Dev clusters upgrade first, soak for 2 days
- Staging upgrades next, soak for 3 days  
- Production upgrades last, with 7-day validation

## Migration Timeline & Rollback Safety

**Week 1:** Audit + apply temporary exclusions (safe, reversible)
**Week 2:** Channel migration (safe, can revert to "No channel" if needed)  
**Week 3:** Configure advanced controls (builds on channel migration)
**Week 4:** Test and validate new control mechanisms

**Rollback plan:** If issues arise, you can revert to "No channel" and remove exclusions:
```bash
gcloud container clusters update CLUSTER --zone ZONE \
  --release-channel ""
```

## Immediate Action Items

1. **Apply temporary exclusions NOW** to prevent forced upgrades during migration:
   ```bash
   --add-maintenance-exclusion-scope no_upgrades
   ```

2. **Choose your target strategy:**
   - Maximum control: Regular channel + "no minor or node" exclusions
   - Balanced: Regular channel + maintenance windows only
   - Extended lifecycle: Extended channel + manual minor upgrades

3. **Migrate 1-2 dev clusters first** as proof of concept

4. **Plan your maintenance windows** aligned with business requirements

## Key Benefits After Migration

✅ **Better EoS protection** — persistent exclusions track EoS automatically  
✅ **Patch-only mode** — get security updates without disruption  
✅ **Fleet coordination** — upgrade dev before prod automatically  
✅ **Extended support option** — 24-month lifecycle available  
✅ **Superior tooling** — better insights, notifications, and controls

The migration path gives you **more control, not less**. Your current "No channel" setup is actually the most restrictive option available.
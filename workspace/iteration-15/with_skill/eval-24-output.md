# Legacy "No Channel" → Release Channel Migration Guide

## What You're Missing on "No Channel"

The "No channel" configuration is **severely limiting your upgrade control options**. Here's what you're losing compared to release channels:

| Feature | Release Channels | No Channel |
|---------|-----------------|------------|
| **"No minor or node upgrades" exclusion** | ✅ Yes (cluster-level + per-nodepool) | ❌ **No** — only 30-day "no upgrades" available |
| **"No minor upgrades" exclusion** | ✅ Yes | ❌ **No** |
| **Per-nodepool maintenance exclusion scope** | ✅ Full control (no_minor, no_minor_or_node) | ❌ Limited to "no upgrades" only |
| **Extended support (24 months)** | ✅ Yes (versions 1.27+) | ❌ **No** |
| **Rollout sequencing** | ✅ Yes (fleet-based upgrade orchestration) | ❌ **No** |
| **Persistent exclusions (auto-tracks EoS)** | ✅ Yes (`--until-end-of-support`) | ❌ **No** |
| **Granular auto-upgrade control** | ✅ Full (windows + exclusions + intervals) | ❌ Limited |

### The Control Paradox

**Key insight:** The most powerful upgrade control tools are **ONLY available on release channels**. Customers who want maximum control should use release channels WITH exclusions, not avoid channels entirely. This is the opposite of what most teams assume.

### EoS Enforcement Issues You're Facing

On "No channel," when versions reach End of Support:
- **Control plane:** EoS minor versions are auto-upgraded to next supported minor
- **Node pools:** EoS versions are auto-upgraded **EVEN when "no auto-upgrade" is configured**
- **Only escape:** The 30-day "no upgrades" exclusion — but you can only use this 3 times per cluster with a 48-hour gap requirement

## Migration Strategy for Your 8 Clusters

### Recommended Target: Regular Channel + Exclusions

For your 8-cluster fleet, I recommend migrating to **Regular channel** with strategic maintenance exclusions:

**Why Regular over Stable:**
- Regular provides the right balance of stability and feature access
- Versions arrive ~2-4 weeks after Rapid validation
- Full SLA coverage (unlike Rapid)
- Sufficient time for testing before auto-upgrade

**Alternative: Extended Channel**
If your team does manual upgrades exclusively and needs maximum flexibility around EoS enforcement, consider **Extended channel** (24-month support for versions 1.27+).

### Phase 1: Immediate Risk Mitigation (This Week)

Before migration, protect your current clusters from forced upgrades:

```bash
# Add 30-day "no upgrades" exclusion to all 8 clusters
for cluster in cluster-1 cluster-2 cluster-3 cluster-4 cluster-5 cluster-6 cluster-7 cluster-8; do
  gcloud container clusters update $cluster \
    --zone YOUR_ZONE \
    --add-maintenance-exclusion-name "pre-migration-freeze" \
    --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
    --add-maintenance-exclusion-end-time $(date -u -d "+30 days" +"%Y-%m-%dT%H:%M:%SZ") \
    --add-maintenance-exclusion-scope no_upgrades
done
```

This buys you 30 days to execute the migration without forced upgrades.

### Phase 2: Channel Migration (Weeks 2-3)

#### Pre-Migration Checklist

```
Pre-Migration Checklist (per cluster)
- [ ] Current version verified: 1.31.x
- [ ] Version 1.31 available in Regular channel (confirm with `gcloud container get-server-config`)
- [ ] Deprecated API usage checked (GKE console insights)
- [ ] Maintenance windows configured
- [ ] Team trained on new exclusion types
- [ ] Rollback plan documented
```

#### Migration Commands

**Step 1: Migrate to Regular Channel**
```bash
# Migrate each cluster
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular
```

**Step 2: Configure Maintenance Windows**
```bash
# Set recurring weekend maintenance windows
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-12-07T02:00:00Z" \
  --maintenance-window-end "2024-12-07T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Step 3: Apply Strategic Exclusions**
```bash
# For maximum control: "no minor or node upgrades" (allows CP patches, blocks disruptive changes)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "controlled-upgrades" \
  --add-maintenance-exclusion-until-end-of-support \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

### Phase 3: Fleet-Level Controls (Week 4)

#### Environment-Based Channel Strategy

For better fleet management, consider differentiated channels by environment:

```
Environment Mapping:
- Dev clusters (2): Regular channel, auto-upgrades enabled
- Staging clusters (2): Regular channel, "no minor" exclusions
- Production clusters (4): Regular channel, "no minor or node upgrades" exclusions
```

#### Rollout Sequencing (Advanced)

If you want automated fleet-wide upgrade orchestration:

```bash
# Enable fleet management
gcloud container fleet create --project=PROJECT_ID

# Configure rollout sequence: dev → staging → prod
gcloud container fleet clusterupgrade update \
  --project=PROJECT_ID \
  --upstream-fleet=dev-fleet \
  --default-upgrade-soaking=7d
```

**Note:** Rollout sequencing requires all clusters on the same channel. Only recommend this if you have 10+ clusters or explicit multi-cluster coordination needs.

## Maintenance Exclusion Strategy

### Recommended Exclusion Types by Environment

**Production Clusters:**
```bash
# "No minor or node upgrades" - maximum control, allows CP security patches
--add-maintenance-exclusion-scope no_minor_or_node_upgrades
--add-maintenance-exclusion-until-end-of-support
```

**Staging Clusters:**
```bash
# "No minor upgrades" - allows node patches, blocks minor versions
--add-maintenance-exclusion-scope no_minor_upgrades
--add-maintenance-exclusion-until-end-of-support
```

**Dev Clusters:**
```bash
# No exclusions - full auto-upgrade for early detection
```

### Managing Upgrade Timing

With exclusions in place, you control when upgrades happen:

1. **Control plane minor upgrades:** Manual trigger when ready
2. **Node pool upgrades:** Manual trigger with your chosen strategy
3. **Patches:** Auto-applied (CP only with "no minor or node" exclusion)

```bash
# When ready to upgrade (your timeline, not GKE's)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.latest

# Then upgrade node pools with controlled strategy
gcloud container node-pools upgrade POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

## Migration Timeline

```
Week 1: Risk Mitigation
- Apply 30-day "no upgrades" exclusions to all clusters
- Validate current state, check for deprecated APIs

Week 2: Channel Migration (Clusters 1-4)
- Migrate dev/staging clusters to Regular channel
- Configure maintenance windows and exclusions
- Test new exclusion behavior

Week 3: Channel Migration (Clusters 5-8)
- Migrate production clusters to Regular channel
- Apply "no minor or node upgrades" exclusions
- Validate control is working as expected

Week 4: Fleet Optimization
- Implement environment-specific exclusion strategies
- Set up monitoring for upgrade notifications
- Document new operational procedures
```

## Operational Changes

### New Workflows Your Team Gains

1. **Predictable upgrade timing:** Maintenance windows + exclusions give you full control
2. **Granular control:** Choose exactly what auto-upgrades (patches vs minor vs nodes)
3. **Extended support option:** 24-month support for compliance requirements
4. **Fleet orchestration:** Rollout sequencing for multi-cluster environments

### Monitoring & Alerting

Set up proactive monitoring:

```bash
# Check auto-upgrade targets
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Monitor for deprecation insights
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=LOCATION \
  --project=PROJECT_ID
```

## Expected Benefits Post-Migration

1. **No more surprise forced upgrades** at EoS
2. **Granular control** over what gets upgraded when
3. **Security patches** continue automatically (with "no minor or node" exclusions)
4. **Persistent exclusions** that track version EoS automatically
5. **Future-proofing** for Extended channel and rollout sequencing features

## Migration Risks & Mitigation

**Risk:** Current version (1.31) not immediately available in Regular channel
**Mitigation:** Check version availability first. If 1.31 isn't in Regular yet, your cluster will be "ahead of channel" and won't auto-upgrade until Regular catches up.

**Risk:** Exclusion types don't translate between "No channel" and release channels
**Mitigation:** Only "no_upgrades" exclusions translate. Remove other exclusion types before migration.

**Risk:** Team unfamiliarity with new exclusion scopes
**Mitigation:** Training on the three exclusion types and their use cases.

Your 8-cluster fleet will have **significantly more control** on release channels than on "No channel." The migration is straightforward and immediately improves your upgrade management capabilities.
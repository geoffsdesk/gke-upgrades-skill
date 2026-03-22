# GKE Release Channel Migration Plan

Your team is missing significant upgrade control capabilities by staying on legacy "No channel". Here's what you need to know and your migration path.

## What You're Missing on "No Channel"

| Feature | Release channels | No channel |
|---------|-----------------|------------|
| **"No minor or node upgrades" exclusion** | ✅ Yes (cluster-level + per-nodepool) | ❌ **No** — only the 30-day "no upgrades" type is available |
| **"No minor upgrades" exclusion** | ✅ Yes | ❌ **No** |
| **Per-nodepool maintenance exclusion** | ✅ Yes | ⚠️ Yes (but limited to "no upgrades" 30 days) |
| **Extended support (24 months)** | ✅ Yes | ❌ **No** |
| **Rollout sequencing** | ✅ Yes (advanced) | ❌ **No** |
| **Persistent exclusions (tracks EoS)** | ✅ Yes | ❌ **No** |
| **Granular auto-upgrade control** | ✅ Full (windows + exclusions + intervals) | ⚠️ Limited |

### The Control Paradox

The most powerful upgrade control tools are **only available on release channels**. Customers who want maximum control should use release channels WITH exclusions, not avoid channels entirely. This is the opposite of what most teams assume.

### EoS Enforcement Differences

**"No channel" EoS behavior:**
- Control plane EoS minor versions are auto-upgraded to the next supported minor version
- EoS node pools are auto-upgraded to the next supported version **EVEN when "no auto-upgrade" is configured**
- Only escape: 30-day "no upgrades" exclusion (then enforcement resumes)

**Release channel EoS behavior:**
- Systematic enforcement follows cluster-level policies
- "No minor or node upgrades" exclusion can block upgrades up to EoS
- Extended channel delays EoS enforcement until end of extended support (up to 24 months)

## Recommended Migration Strategy

### Target Channel Selection

For your 8 clusters, I recommend:

**Primary recommendation: Regular channel**
- Closest match to legacy "No channel" behavior
- Full SLA coverage
- Standard 14-month support lifecycle
- Good balance of stability and currency

**Alternative: Extended channel (if you need maximum EoS flexibility)**
- Up to 24 months support for versions 1.27+
- Minor version upgrades are NOT automated (you control timing)
- Extra cost only during extended support period (months 15-24)
- Best for teams that want to manually control all minor upgrades

### Migration Path

**Phase 1: Prepare (1-2 weeks)**

```bash
# For each cluster, audit current state
for cluster in cluster-1 cluster-2 cluster-3 cluster-4 cluster-5 cluster-6 cluster-7 cluster-8; do
  echo "=== $cluster ==="
  gcloud container clusters describe $cluster \
    --zone ZONE \
    --format="table(name, currentMasterVersion, nodePools[].version, releaseChannel.channel)"
done

# Check maintenance exclusions (these may not translate 1:1)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="yaml(maintenancePolicy)"
```

**Phase 2: Test Migration (1 cluster first)**

```bash
# Choose your least critical cluster for testing
# Add temporary "no upgrades" exclusion first (safety net)
gcloud container clusters update test-cluster-1 \
  --zone ZONE \
  --add-maintenance-exclusion-name "migration-safety" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time $(date -u -d "+30 days" +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-scope no_upgrades

# Migrate to Regular channel
gcloud container clusters update test-cluster-1 \
  --zone ZONE \
  --release-channel regular

# Replace with persistent "no minor or node upgrades" exclusion (maximum control)
gcloud container clusters update test-cluster-1 \
  --zone ZONE \
  --remove-maintenance-exclusion-name "migration-safety" \
  --add-maintenance-exclusion-name "platform-team-control" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-until-end-of-support \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Verify migration
gcloud container clusters describe test-cluster-1 \
  --zone ZONE \
  --format="value(releaseChannel.channel,maintenancePolicy)"
```

**Phase 3: Roll Out to Remaining Clusters**

Migrate 2-3 clusters per week to allow for observation and issue resolution.

```bash
# Script for batch migration
#!/bin/bash
CLUSTERS=("cluster-2" "cluster-3" "cluster-4" "cluster-5" "cluster-6" "cluster-7" "cluster-8")
ZONE="your-zone"

for cluster in "${CLUSTERS[@]}"; do
  echo "Migrating $cluster..."
  
  # Safety exclusion
  gcloud container clusters update $cluster \
    --zone $ZONE \
    --add-maintenance-exclusion-name "migration-safety" \
    --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
    --add-maintenance-exclusion-end-time $(date -u -d "+30 days" +"%Y-%m-%dT%H:%M:%SZ") \
    --add-maintenance-exclusion-scope no_upgrades
  
  # Migrate to Regular channel
  gcloud container clusters update $cluster \
    --zone $ZONE \
    --release-channel regular
  
  # Add persistent control exclusion
  gcloud container clusters update $cluster \
    --zone $ZONE \
    --remove-maintenance-exclusion-name "migration-safety" \
    --add-maintenance-exclusion-name "platform-team-control" \
    --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
    --add-maintenance-exclusion-until-end-of-support \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades
  
  echo "$cluster migrated. Waiting 1 week before next cluster..."
  sleep 7d  # Remove this for faster migration if desired
done
```

## Post-Migration Control Strategy

Once migrated, you'll have much more granular control:

### Maintenance Exclusion Types Available

```bash
# Maximum control: blocks minor versions AND node upgrades, allows CP patches
--add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Moderate control: blocks minor versions, allows patches + node upgrades  
--add-maintenance-exclusion-scope no_minor_upgrades

# Emergency control: blocks ALL upgrades (30 days max)
--add-maintenance-exclusion-scope no_upgrades
```

### Recommended Ongoing Strategy

**For maximum control (recommended for your team):**
```bash
# Apply "no minor or node upgrades" exclusion with persistent tracking
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "platform-control" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-until-end-of-support \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

This gives you:
- ✅ Control plane security patches (automatic)
- ✅ Full control over minor version timing (you decide when)
- ✅ Full control over node pool upgrades (you decide when)
- ✅ No forced upgrades until actual EoS (not just channel promotion)
- ✅ Automatic EoS tracking (exclusion renews when you do upgrade to next minor)

### Maintenance Windows

Configure predictable windows for when auto-upgrades can occur:
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-01T02:00:00Z" \
  --maintenance-window-end "2024-01-01T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"
```

## Migration Risks and Mitigations

### Risk 1: Exclusion Translation
**Problem:** Current "No channel" exclusions may not translate properly
**Mitigation:** Add temporary "no upgrades" exclusion before migration, then replace with channel-specific exclusion

### Risk 2: Version Availability
**Problem:** Your current 1.31 version may not be available in the target channel
**Mitigation:** Check available versions first:
```bash
gcloud container get-server-config --zone ZONE --format="yaml(channels)"
```

### Risk 3: Auto-upgrade Timing Changes
**Problem:** Channel migration might trigger immediate upgrade eligibility
**Mitigation:** Use maintenance exclusions to control timing from day 1

## Long-term Benefits

After migration, your platform team will have:

1. **Persistent exclusions** that automatically track EoS dates
2. **Granular control** over exactly which upgrade types are allowed
3. **Extended support option** for versions that need longer lifecycles
4. **Multi-cluster rollout sequencing** capabilities (if needed for your 8 clusters)
5. **Better predictability** with scheduled upgrade notifications (72h advance notice)

## Timeline Summary

- **Week 1-2:** Audit current state, plan migration
- **Week 3:** Test migrate 1 cluster, validate behavior
- **Week 4-10:** Migrate remaining 7 clusters (2-3 per week)
- **Ongoing:** Enjoy much better upgrade control

The key insight: release channels + maintenance exclusions give you **more** control than "No channel", not less. Your forced upgrade issues will be resolved, and you'll have the granular control your platform team needs.
# Legacy "No Channel" Migration Plan

Your team is missing critical upgrade control features by staying on "No channel." Here's what you're missing and how to migrate safely.

## What You're Missing on "No Channel"

| Feature | Release channels | No channel |
|---------|-----------------|------------|
| **"No minor or node upgrades" exclusion** | ✅ Yes (cluster-level + per-nodepool) | ❌ **No** — only the 30-day "no upgrades" type is available |
| **"No minor upgrades" exclusion** | ✅ Yes | ❌ **No** |
| **Extended support (24 months)** | ✅ Yes | ❌ **No** |
| **Rollout sequencing** | ✅ Yes (advanced) | ❌ **No** |
| **Persistent exclusions (tracks EoS)** | ✅ Yes | ❌ **No** |
| **Granular auto-upgrade control** | ✅ Full (windows + exclusions + intervals) | ❌ Limited |

### Key Problems with "No Channel"

**1. EoS enforcement is identical:** You get the same forced upgrades on "No channel" that you're trying to avoid. When a version reaches End of Support, clusters are force-upgraded to the next minor version — this applies equally to release channels AND "No channel."

**2. Limited exclusion types:** You only have access to 30-day "no upgrades" exclusions. You can't block just minor versions while allowing patches — it's all-or-nothing.

**3. No Extended support:** You can't get 24-month support periods to reduce upgrade frequency.

**4. Operational complexity:** You lose access to rollout sequencing, persistent exclusions that track EoS automatically, and the most powerful upgrade control tools.

## Recommended Migration Path

**Target configuration:** Regular or Extended release channel with maintenance exclusions for maximum control.

### Option 1: Conservative Migration (Regular Channel)
```bash
# For each cluster:
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --release-channel regular \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
```

**What this gives you:**
- Regular channel = closest match to legacy "No channel" timing
- "No minor or node upgrades" exclusion = **maximum control** (blocks both CP minor versions AND node upgrades)
- Only control plane patches are auto-applied (security updates)
- Manual control over when minor upgrades happen
- Up to EoS tracking (no 30-day limit like "No channel")

### Option 2: Maximum Flexibility (Extended Channel)
```bash
# For each cluster:
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --release-channel extended
```

**What Extended gives you:**
- Up to 24 months of support (cost only during extended period)
- Control plane minor versions are NOT auto-upgraded (except at end of extended support)
- Patches still arrive at Regular channel timing (no delay)
- Maximum flexibility around EoS enforcement
- Best migration path for teams that want manual control

## Pre-Migration Checklist

```
Pre-Migration Checklist
- [ ] Check current version availability in target channel
- [ ] Apply temporary "no upgrades" exclusion before migration
- [ ] Verify no deprecated API usage
- [ ] Plan migration during maintenance window
- [ ] Document current per-nodepool exclusion settings (if any)

Version Compatibility Check
- [ ] Cluster 1: ___ (current version 1.31.x)
- [ ] Cluster 2: ___ 
- [ ] Cluster 3: ___
- [ ] Cluster 4: ___
- [ ] Cluster 5: ___
- [ ] Cluster 6: ___
- [ ] Cluster 7: ___
- [ ] Cluster 8: ___
```

## Migration Commands

### Step 1: Pre-migration safety
```bash
# Add temporary freeze to prevent immediate auto-upgrades after channel switch
for cluster in CLUSTER1 CLUSTER2 CLUSTER3 CLUSTER4 CLUSTER5 CLUSTER6 CLUSTER7 CLUSTER8; do
    gcloud container clusters update $cluster \
        --zone ZONE \
        --add-maintenance-exclusion-name "migration-freeze" \
        --add-maintenance-exclusion-start "2024-01-15T00:00:00Z" \
        --add-maintenance-exclusion-end "2024-01-22T00:00:00Z" \
        --add-maintenance-exclusion-scope no_upgrades
done
```

### Step 2: Migrate to Regular channel with permanent control
```bash
# Conservative approach - Regular channel + "no minor or node upgrades"
for cluster in CLUSTER1 CLUSTER2 CLUSTER3 CLUSTER4 CLUSTER5 CLUSTER6 CLUSTER7 CLUSTER8; do
    gcloud container clusters update $cluster \
        --zone ZONE \
        --release-channel regular \
        --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
        --add-maintenance-exclusion-until-end-of-support
done
```

### Step 3: Configure maintenance windows
```bash
# Set predictable maintenance windows (example: Saturday 2-6 AM)
for cluster in CLUSTER1 CLUSTER2 CLUSTER3 CLUSTER4 CLUSTER5 CLUSTER6 CLUSTER7 CLUSTER8; do
    gcloud container clusters update $cluster \
        --zone ZONE \
        --maintenance-window-start "2024-01-20T02:00:00Z" \
        --maintenance-window-end "2024-01-20T06:00:00Z" \
        --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
done
```

### Step 4: Remove temporary freeze
```bash
# After verifying the permanent exclusions are in place
for cluster in CLUSTER1 CLUSTER2 CLUSTER3 CLUSTER4 CLUSTER5 CLUSTER6 CLUSTER7 CLUSTER8; do
    gcloud container clusters update $cluster \
        --zone ZONE \
        --remove-maintenance-exclusion-name "migration-freeze"
done
```

## Post-Migration Benefits

**Immediate gains:**
- **Control plane patches auto-applied** during your maintenance windows (security without disruption)
- **Minor versions blocked** until you manually trigger them
- **Node upgrades blocked** until you manually trigger them
- **No more 30-day exclusion limits** — exclusions track EoS automatically

**Future capabilities you can add:**
- **Rollout sequencing:** Upgrade dev → staging → prod automatically with soak time
- **Disruption intervals:** Control minimum gap between upgrades
- **Extended support:** Migrate to Extended channel for 24-month support periods

## Alternative: Extended Channel Only

If you want maximum flexibility and are comfortable with manual minor upgrades:

```bash
# Extended channel - simplest migration
for cluster in CLUSTER1 CLUSTER2 CLUSTER3 CLUSTER4 CLUSTER5 CLUSTER6 CLUSTER7 CLUSTER8; do
    gcloud container clusters update $cluster \
        --zone ZONE \
        --release-channel extended
done
```

**Extended channel behavior:**
- Control plane minor versions are NOT auto-upgraded (except at end of extended support)
- Node versions follow control plane by default (can be blocked with exclusions)
- Patches arrive at Regular channel timing
- Up to 24 months support (extra cost only during extended period)

## Validation Commands

```bash
# Verify migration success
gcloud container clusters describe CLUSTER_NAME \
    --zone ZONE \
    --format="value(releaseChannel.channel)"

# Check exclusions are active
gcloud container clusters describe CLUSTER_NAME \
    --zone ZONE \
    --format="table(maintenancePolicy.window,maintenancePolicy.resourceVersion)"

# Verify auto-upgrade target
gcloud container clusters get-upgrade-info CLUSTER_NAME --zone ZONE
```

## Migration Timeline

**Recommended approach:** Migrate 2 clusters per week to validate behavior.

- **Week 1:** Migrate 2 clusters, monitor for 1 week
- **Week 2:** Migrate 2 more clusters  
- **Week 3:** Migrate 2 more clusters
- **Week 4:** Migrate final 2 clusters

This staged approach lets you validate the new behavior and catch any issues before migrating your entire fleet.

**Bottom line:** You're not getting more control by staying on "No channel" — you're getting LESS control. Release channels with maintenance exclusions give you everything "No channel" provides plus significantly more powerful tools for managing upgrades.
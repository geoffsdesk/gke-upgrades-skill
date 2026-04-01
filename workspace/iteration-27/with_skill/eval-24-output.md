# Migration from Legacy "No Channel" to Release Channels

Your platform team is right to be concerned — staying on "No channel" limits your upgrade control options and creates operational risk. Here's what you're missing and how to migrate.

## What You're Missing on "No Channel"

| Feature | Release Channels | No Channel |
|---------|-----------------|------------|
| **"No minor or node upgrades" exclusion** | ✅ Cluster-level, tracks EoS automatically | ❌ Not available |
| **"No minor upgrades" exclusion** | ✅ Available | ❌ Not available |
| **Persistent exclusions (auto-renew at EoS)** | ✅ `--add-maintenance-exclusion-until-end-of-support` | ❌ Manual renewal only |
| **Extended support (24 months)** | ✅ Available for 1.27+ | ❌ Not available |
| **Rollout sequencing** | ✅ Multi-cluster upgrade orchestration | ❌ Not available |
| **Granular auto-upgrade control** | ✅ Full (windows + exclusions + intervals) | ❌ Limited to basic exclusions |
| **Per-nodepool "disable auto-upgrade"** | ❌ Use cluster-level exclusion scopes instead | ✅ Persistent until EoS |

**Key insight:** The most powerful upgrade control tools are ONLY available on release channels. Counter-intuitively, release channels give you MORE control, not less.

## Critical Issues with "No Channel"

### 1. EoS Enforcement is Still Systematic
- When versions reach End of Support, "No channel" clusters are force-upgraded just like release channel clusters
- Per-nodepool "no auto-upgrade" settings are IGNORED at EoS — nodes get force-upgraded anyway
- Only the 30-day "no upgrades" exclusion can defer EoS enforcement

### 2. Limited Exclusion Types
You can only use:
- 30-day "no upgrades" exclusions (max 3, must be chained)
- Per-nodepool persistent exclusions (ignored at EoS)

You CANNOT use:
- "No minor upgrades" — blocks minor versions but allows patches
- "No minor or node upgrades" — maximum control while allowing CP patches
- Persistent exclusions that auto-renew

### 3. No Extended Support
- Stuck with standard 14-month support lifecycle
- Can't extend critical versions to 24 months
- Must upgrade more frequently than Extended channel users

## Recommended Migration Strategy

### Target Architecture: Extended Channel + Maximum Control
For platform teams wanting ultimate control while maintaining security:

```bash
# Migrate to Extended channel with maximum control configuration
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --release-channel extended \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support \
    --maintenance-window-start "2024-12-15T02:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

This gives you:
- **Extended support:** Up to 24 months per version (cost only during extended period)
- **Patch-only auto-upgrades:** Control plane gets security patches automatically
- **No minor/node auto-upgrades:** You control when minor versions and node upgrades happen
- **Predictable timing:** Saturday 2-6 AM maintenance window
- **EoS flexibility:** Extended support delays EoS enforcement

### Step-by-Step Migration Process

#### Phase 1: Pre-Migration Safety (All Clusters)
```bash
# Add temporary "no upgrades" exclusion before channel change
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "channel-migration" \
    --add-maintenance-exclusion-start-time "2024-12-15T00:00:00Z" \
    --add-maintenance-exclusion-end-time "2024-12-16T00:00:00Z" \
    --add-maintenance-exclusion-scope no_upgrades
```

#### Phase 2: Migrate to Extended Channel
```bash
# Check version availability first
gcloud container get-server-config --zone ZONE --format="yaml(channels.EXTENDED)"

# Migrate to Extended channel
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --release-channel extended
```

**Version compatibility warning:** Your clusters at 1.31 should be fine — Extended channel supports 1.27+. However, verify 1.31 is available in Extended before migrating.

#### Phase 3: Configure Maximum Control
```bash
# Add persistent "no minor or node" exclusion
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support

# Set maintenance window
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --maintenance-window-start "2024-12-15T02:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Remove temporary migration exclusion
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --remove-maintenance-exclusion "channel-migration"
```

### Alternative: Regular Channel Migration
If Extended channel feels too aggressive, migrate to Regular channel instead:

```bash
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --release-channel regular \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
```

Regular channel provides the same exclusion capabilities but with standard 14-month support periods.

## Recommended Rollout Sequence for 8 Clusters

### Environment-Based Staging
1. **Dev/test clusters first** — migrate and validate the new behavior
2. **Staging clusters** — soak for 2-4 weeks  
3. **Production clusters** — migrate after validating dev/staging

### Timeline
- **Week 1:** Migrate 2 dev clusters
- **Week 2:** Migrate remaining dev + 2 staging clusters  
- **Week 4:** Begin production migration (2 clusters per week)
- **Week 7:** Complete all migrations

## What This Gets You

### Immediate Benefits
- **No more surprise EoS upgrades** — Extended support gives you up to 24 months per version
- **Patch-only mode** — CP gets security patches, you control everything else
- **Persistent exclusions** — no more manual renewal every 6 months
- **Better planning tools** — GKE release schedule shows Extended channel timelines

### Long-term Benefits  
- **Rollout sequencing** — orchestrate upgrades across all 8 clusters automatically
- **Scheduled upgrade notifications** — 72-hour advance warning via Cloud Logging
- **Extended support eligibility** — delay EoS for critical versions

## Migration Checklist

```markdown
Pre-Migration (Per Cluster)
- [ ] Current version: 1.31 confirmed available in Extended channel
- [ ] Temporary "no upgrades" exclusion applied
- [ ] Stakeholders notified of channel change
- [ ] Maintenance window requirements defined

Migration (Per Cluster)  
- [ ] Channel changed to Extended
- [ ] "No minor or node upgrades" exclusion applied with auto-renewal
- [ ] Maintenance window configured
- [ ] Temporary exclusion removed
- [ ] Auto-upgrade target verified: `gcloud container clusters get-upgrade-info`

Post-Migration Validation
- [ ] Cluster shows Extended channel: `gcloud container clusters describe --format="value(releaseChannel.channel)"`
- [ ] Exclusion active: `gcloud container clusters describe --format="yaml(maintenancePolicy.excludedOptions)"`  
- [ ] No unexpected auto-upgrades scheduled in next 30 days
- [ ] Team trained on new maintenance exclusion capabilities
```

## Cost Implications

- **Extended channel:** Extra cost only applies during the extended support period (months 15-24)
- **No cost during standard support** (first 14 months)
- **Patch upgrades:** Same frequency as Regular channel — no delay on security patches

## Next Steps

1. **Start with 1-2 dev clusters** to validate the migration process
2. **Document the new operational model** — your team now has much more granular control
3. **Plan your first manual minor upgrade** — you'll need to trigger 1.31→1.32 manually when ready
4. **Set up monitoring** for the new maintenance exclusions and auto-upgrade targets

The migration will significantly improve your upgrade control while maintaining security posture. Extended + "no minor or node upgrades" is the gold standard for platform teams needing maximum control.
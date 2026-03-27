# Migration from "No Channel" to Release Channels

Your platform team is right to be concerned. "No channel" is a legacy configuration that **severely limits** your upgrade control options. Here's what you're missing and how to migrate safely.

## What You're Missing on "No Channel"

| Feature | Release channels | No channel |
|---------|-----------------|------------|
| **"No minor or node upgrades" exclusion** | ✅ Yes (cluster-level + per-nodepool) | ❌ **No** — only the 30-day "no upgrades" type is available |
| **"No minor upgrades" exclusion** | ✅ Yes | ❌ **No** |
| **Per-nodepool maintenance exclusion (disable auto-upgrade)** | ❌ **No** — use cluster-level exclusion scopes | ✅ Yes (but limited to "no upgrades" 30 days) |
| **Extended support (24 months)** | ✅ Yes | ❌ **No** |
| **Rollout sequencing** | ✅ Yes (advanced) | ❌ **No** |
| **Persistent exclusions (tracks EoS)** | ✅ Yes | ❌ **No** |
| **Granular auto-upgrade control** | Full (windows + exclusions + intervals) | Limited |

### Key Problems You're Experiencing

1. **No "no minor" exclusion** — You can't block minor version upgrades while still getting security patches
2. **EoS enforcement is brutal** — When versions reach End of Support, both control plane AND node pools are force-upgraded with no granular control
3. **Only 30-day exclusions** — Your longest freeze period is 30 days, and you can only chain 3 of them
4. **No persistent exclusions** — Every exclusion has a hard end date; nothing automatically renews

## Recommended Migration Strategy

### Phase 1: Choose Target Channel (Immediate)

For your platform team's needs, I recommend **Regular channel** as the migration target:

- **Regular channel** closest matches "No channel" behavior — same minor upgrade pace as your current experience
- **Stable channel** if you want even more conservative upgrades (+2 weeks slower than Regular)
- **Extended channel** if you want maximum EoS flexibility (delays enforcement until end of extended support, but costs extra during extended period)

### Phase 2: Migration Process

**⚠️ Critical warning about version availability:**
Before migrating, check which versions are available in your target channel:

```bash
# Check current cluster version
gcloud container clusters describe CLUSTER_NAME --zone ZONE --format="value(currentMasterVersion)"

# Check available versions in target channel
gcloud container get-server-config --zone ZONE --format="yaml(channels)"
```

**If your current version (1.31.x) is not yet available in the target channel, your cluster will be "ahead of channel" and will NOT receive auto-upgrades until the channel catches up.**

### Safe Migration Steps

For each cluster:

1. **Add a temporary "no upgrades" exclusion** to prevent immediate auto-upgrades:
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "channel-migration" \
  --add-maintenance-exclusion-start $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end $(date -u -d '+7 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_upgrades
```

2. **Migrate to Regular channel:**
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular
```

3. **Configure your new maintenance controls** (replace the temporary exclusion):
```bash
# Remove temporary exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion "channel-migration"

# Add persistent "no minor or node" exclusion for maximum control
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "prod-control" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

4. **Set up maintenance windows:**
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2026-01-01T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## Your New Upgrade Control Model

After migration, you'll have **much better** control:

### Recommended Configuration for Platform Teams
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support \
  --maintenance-window-start "2026-01-01T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA" \
  --maintenance-patch-version-disruption-interval 604800s
```

This gives you:
- **Control plane security patches only** — no disruptive minor or node upgrades
- **Weekly 4-hour maintenance window** — upgrades only happen Saturday 2-6 AM
- **Minimum 7 days between patches** — prevents back-to-back patch disruptions
- **Persistent exclusion** — automatically renews when you upgrade minor versions

### When You Want to Upgrade Minor Versions

With this setup, minor upgrades become **your choice**:

```bash
# When you're ready for 1.32, trigger it manually
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.y

# The exclusion automatically tracks the new version's EoS date
```

## Timeline and Rollout

### Suggested Rollout Order
1. **Dev/test clusters first** — validate the new control model
2. **Staging clusters** — verify workload compatibility  
3. **Production clusters** — with the battle-tested configuration

### Per-Cluster Migration Window
- **Migration itself:** ~5 minutes per cluster
- **Configuration:** ~10 minutes to set up exclusions and windows
- **Total per cluster:** ~15 minutes

## What You Gain After Migration

1. **Real upgrade control** — "no minor or node" exclusions give you the control "No channel" promised but didn't deliver
2. **Security without disruption** — control plane patches keep you secure while blocking disruptive changes
3. **No more surprise forced upgrades** — exclusions automatically track EoS dates
4. **Progressive rollout capability** — rollout sequencing across your 8-cluster fleet (advanced feature)
5. **Longer exclusion periods** — up to 24 months with Extended support vs. 30-day max on "No channel"

## Migration Checklist

```
Migration Checklist (per cluster)
- [ ] Current version documented: ___
- [ ] Target channel chosen: Regular / Stable / Extended
- [ ] Version availability in target channel verified
- [ ] Temporary "no upgrades" exclusion applied
- [ ] Channel migration completed: `--release-channel regular`
- [ ] Maintenance window configured (off-peak hours)
- [ ] Persistent "no minor or node" exclusion configured
- [ ] Disruption interval set (minimum time between patches)
- [ ] Auto-upgrade status verified: `gcloud container clusters get-upgrade-info`
- [ ] Temporary exclusion removed
- [ ] Migration documented in runbook
```

Your platform team will have **dramatically better** upgrade control after this migration. The "No channel" configuration is a legacy trap — release channels with exclusions give you the control you actually need.
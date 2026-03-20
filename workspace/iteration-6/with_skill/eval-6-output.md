# Channel Migration: Rapid → Stable

This is a low-risk change that will give you better stability in production. Here's what happens and how to execute it safely.

## What changes when you migrate

| Aspect | Impact |
|--------|--------|
| **New version timing** | New K8s minors will arrive 2-4 weeks later than Rapid |
| **Current version** | No immediate change — 1.30 is already available in Stable |
| **Auto-upgrade behavior** | Future auto-upgrades will follow Stable channel timing |
| **Manual upgrades** | You can still manually upgrade to any version available in Stable |

## Pre-migration checks

```bash
# Verify 1.30 is available in Stable channel
gcloud container get-server-config --zone YOUR_ZONE \
  --format="yaml(channels.STABLE.validVersions)"

# Check current auto-upgrade target
gcloud container clusters describe YOUR_CLUSTER --zone YOUR_ZONE \
  --format="value(autopilot,releaseChannel,currentMasterVersion)"
```

## Migration steps

**1. Change the release channel:**
```bash
gcloud container clusters update YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --release-channel stable
```

**2. Verify the change:**
```bash
gcloud container clusters describe YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --format="value(releaseChannel.channel)"
# Should output: STABLE
```

That's it — the migration is immediate and non-disruptive.

## What to expect after migration

- **No immediate upgrades** — Your cluster stays at 1.30
- **Future auto-upgrades** follow Stable timing (slower, more validated)
- **Available versions** — Check periodically with `gcloud container get-server-config` to see what's available in Stable
- **More predictable** — Stable channel has fewer surprise upgrades

## Recommended next steps

**Configure maintenance windows** for predictable upgrade timing:
```bash
gcloud container clusters update YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --maintenance-window-start 2025-01-01T02:00:00Z \
  --maintenance-window-end 2025-01-01T06:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"
```

**Consider maintenance exclusions** for maximum control:
```bash
# "No minor or node upgrades" — allows CP patches, blocks disruptive changes
gcloud container clusters update YOUR_CLUSTER \
  --zone YOUR_ZONE \
  --add-maintenance-exclusion-name "production-stability" \
  --add-maintenance-exclusion-start-time "2025-01-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-06-15T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

## Multi-environment strategy

If you have dev/staging clusters, consider this progression:
- **Dev** → Stay on Rapid (get early access to new features)
- **Staging** → Regular channel (middle ground for integration testing)
- **Production** → Stable (maximum stability, what you're doing)

This gives you a testing pipeline where each environment validates the next.

## Risk assessment

**Very low risk change:**
- ✅ No version changes during migration
- ✅ No workload disruption
- ✅ Reversible (can go back to Rapid anytime)
- ✅ Common production pattern

The main "risk" is cultural — your team will get new K8s features 2-4 weeks later than before. Most production teams consider this a benefit, not a drawback.
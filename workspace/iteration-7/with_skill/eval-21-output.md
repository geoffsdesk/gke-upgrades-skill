# Extended Release Channel Migration Plan

## Extended Channel Tradeoffs

### Benefits
- **24-month support window** (vs. 14 months on Regular/Stable) — reduces upgrade frequency
- **Same version availability as Regular** — no delay in accessing new features
- **Full SLA coverage** — identical to Regular/Stable channels
- **Longer planning cycles** — more time to test and validate new versions
- **Compliance-friendly** — better for environments with slow change approval processes

### Key Limitations & Costs
- **Additional cost** — Extended support incurs extra charges (contact GCS for pricing)
- **Manual minor version upgrades required** — unlike Regular channel, minor version upgrades are NOT automated on Extended (except at End of Support). Your team must plan and execute minor upgrades proactively.
- **Only patches are auto-applied** — security and bug fixes still arrive automatically
- **Available for 1.27+ only** — older versions cannot use Extended channel
- **Requires internal upgrade discipline** — without auto-upgrades, teams may drift behind and accumulate upgrade debt

### Critical Operational Change
**Extended channel fundamentally changes your upgrade model.** On Regular channel, GKE automatically moves you from 1.31 → 1.32 → 1.33, etc. On Extended channel, you'll stay on 1.31.x patches indefinitely until YOU initiate the minor upgrade to 1.32.

This means you need internal processes to:
- Monitor GKE release schedules and plan minor upgrades
- Test new minor versions in staging environments
- Execute upgrades before reaching End of Support
- Maintain upgrade runbooks and team expertise

## Migration Process

### 1. Pre-migration validation
```bash
# Confirm current cluster state
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, releaseChannel.channel)"

# Verify 1.31+ (Extended requires 1.27+)
# Your 1.31 version is compatible
```

### 2. Switch to Extended channel
```bash
# Migrate cluster to Extended channel
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended

# Verify migration
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(releaseChannel.channel)"
```

### 3. Configure maintenance controls
Since you'll now manage minor upgrades manually, set up appropriate maintenance windows and exclusions:

```bash
# Set maintenance window for patches (these remain automatic)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start 2024-01-01T02:00:00Z \
  --maintenance-window-end 2024-01-01T06:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Optional: Add "no minor upgrades" exclusion to prevent any surprise minor upgrades
# (though Extended channel won't auto-upgrade minors anyway, except at EoS)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "no-minor-extended" \
  --add-maintenance-exclusion-start-time 2024-01-01T00:00:00Z \
  --add-maintenance-exclusion-end-time 2026-01-01T00:00:00Z \
  --add-maintenance-exclusion-scope no_minor_upgrades
```

## Post-Migration Operational Model

### What remains automatic on Extended:
- **Patch upgrades** (1.31.1 → 1.31.2 → 1.31.3, etc.)
- **Security updates** applied during maintenance windows
- **Node pool patches** follow cluster control plane patches

### What becomes manual on Extended:
- **Minor version upgrades** (1.31 → 1.32 → 1.33) — you must initiate these
- **Planning upgrade timing** — no automatic progression through minor versions
- **End of Support enforcement** — still applies, but you have 24 months instead of 14

### Recommended upgrade cadence on Extended:
- **Patches**: Let them auto-apply (maintain current maintenance windows)
- **Minor versions**: Plan to upgrade every 6-12 months, well before EoS
- **Testing**: Always validate new minor versions in staging before production

### Example workflow for future minor upgrades:
```bash
# When you're ready to move from 1.31 to 1.32 (customer-initiated):
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.X-gke.XXX

# Node pools (after control plane completes):
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.X-gke.XXX
```

## Multi-Cluster Strategy

If you have dev/staging/prod environments, consider:
- **Dev**: Keep on Rapid channel (early access to test new versions)
- **Staging**: Keep on Regular channel (validates versions before Extended gets them)
- **Production**: Extended channel (24-month support, manual minor upgrade control)

This gives you a validation pipeline: Dev tests bleeding-edge → Staging validates production-ready → Production gets long-term stability.

## Cost Considerations

Extended support has additional charges. The exact pricing depends on your cluster size and usage. Contact Google Cloud Sales or Customer Care for pricing details. Evaluate the cost against:
- **Reduced upgrade operational overhead** (fewer forced upgrade cycles)
- **Longer validation periods** (less risk of production issues)
- **Compliance benefits** (easier to meet slow-change requirements)

## Migration Timeline

The channel switch is immediate — no cluster downtime. However, the operational change (manual minor upgrades) takes effect immediately. Plan your first manual minor upgrade (1.31 → 1.32) within the next 6-12 months to maintain good upgrade hygiene.

Your 1.31.x version will continue receiving patches automatically. You have until 1.31's End of Support (approximately 24 months from the 1.31 GA date) to upgrade to 1.32 manually.
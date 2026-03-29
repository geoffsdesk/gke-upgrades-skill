# GKE Release Channel Migration: Rapid → Stable

## Critical Implications

**⚠️ Version Availability Warning**
Your cluster is currently at 1.32 on Rapid. Before migrating to Stable, you need to check if 1.32 is available in the Stable channel yet. If not, your cluster will be "ahead of channel" and **will NOT receive auto-upgrades** until Stable catches up to 1.32.

**Check version availability first:**
```bash
gcloud container get-server-config --zone YOUR_ZONE \
  --format="yaml(channels)" | grep -A 20 "stable"
```

If 1.32 is not listed in Stable's available versions, you have two options:
1. **Wait** until 1.32 becomes available in Stable (typically 2-4 weeks after Regular)
2. **Downgrade first** to a version that exists in Stable, then migrate

## Key Changes After Migration

| Aspect | Current (Rapid) | After (Stable) |
|--------|-----------------|----------------|
| **Upgrade cadence** | Fastest (new versions within ~2 weeks) | Slowest (after Regular validation) |
| **SLA for upgrade stability** | **No SLA** - versions may have issues | **Full SLA** - versions are battle-tested |
| **Security patches** | Same speed as other channels | ~2 weeks slower than Rapid |
| **Version progression** | 1-2 weeks ahead of Regular/Stable | 2-4 weeks behind Rapid |
| **Auto-upgrade timing** | Immediate when versions promote | Delayed until Stable validation complete |

**The primary benefit:** Moving from Rapid to Stable eliminates the risk of unstable versions. Rapid channel carries NO SLA for upgrade stability - you may get versions with issues that are caught before reaching Stable.

## Migration Process

### Step 1: Apply maintenance exclusion (prevent immediate upgrades)
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "channel-migration" \
  --add-maintenance-exclusion-start-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-end-time "$(date -u -d '+7 days' +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-scope no_upgrades
```

### Step 2: Migrate to Stable channel
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel stable
```

### Step 3: Verify channel change
```bash
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(releaseChannel.channel)"
```

### Step 4: Check auto-upgrade status
```bash
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION
```

### Step 5: Remove maintenance exclusion (when ready)
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "channel-migration"
```

## If 1.32 is NOT in Stable yet

You'll need to either wait or downgrade first. **Recommended approach:**

1. **Check Stable's latest version:**
```bash
gcloud container get-server-config --zone YOUR_ZONE \
  --format="value(channels.stable.defaultVersion)"
```

2. **Downgrade control plane to Stable's latest:**
```bash
# First, add "no minor or node upgrades" exclusion to prevent node skew
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Downgrade control plane
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version STABLE_LATEST_VERSION
```

3. **Then migrate to Stable channel**
4. **Remove exclusion to resume normal upgrades**

## Alternative: Extended Channel Consideration

Since your CTO wants maximum stability, consider **Extended channel** instead of Stable:
- **24-month support** (vs 14-month standard)
- **No automatic minor upgrades** (only patches auto-apply)
- **Full manual control** over when minor upgrades happen
- **Same SLA as Stable** with longer support window

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

## Production Rollout Strategy

**Don't migrate production first.** Recommended sequence:
1. **Dev/staging → Stable** first (validate the new upgrade cadence)
2. **Production → Stable** after 2-4 weeks of observation
3. Keep all environments on the **same channel** to avoid version drift

## Post-Migration Monitoring

- **Upgrade velocity will slow significantly** - expect 2-4 week delays on new versions
- **Security patches will be ~2 weeks slower** than your current Rapid cadence
- **Monitor the [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule)** for Stable version availability
- **Set up scheduled upgrade notifications** (72h advance warning):
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --send-scheduled-upgrade-notifications
```

## Key Decision Point

**If production stability is the primary concern, Extended channel might be better than Stable** - it gives you complete control over minor upgrades while still getting security patches. Discuss with your CTO whether they want slower automatic upgrades (Stable) or manual control over all minor upgrades (Extended).

Would you like me to help you check if 1.32 is available in Stable, or would you prefer guidance on the Extended channel approach?
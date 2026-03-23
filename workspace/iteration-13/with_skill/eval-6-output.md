# GKE Channel Migration: Rapid → Stable

## Migration Analysis

**Current state:** Standard cluster on Rapid channel at 1.32  
**Target:** Stable channel  
**Implication:** This is a **conservative move** that will reduce upgrade frequency and increase stability.

## Key Implications

### Version Availability Changes
- **Immediate effect:** Your cluster will remain at 1.32 until that version becomes available in Stable channel
- **Timeline:** Versions typically take 4-6 weeks to progress from Rapid → Regular → Stable
- **Current 1.32 status:** Check if 1.32 is already available in Stable (it may be, depending on when you upgraded)

### Auto-upgrade Behavior Changes
- **Frequency:** Much slower upgrade cadence - Stable gets versions weeks after Rapid
- **Stability:** Higher - versions are battle-tested through Rapid and Regular first
- **Security patches:** Same patch velocity across all channels for critical security fixes

### Support and SLA
- **No change:** Both Rapid and Stable carry full SLA (unlike common misconceptions)
- **The key difference:** Rapid has no SLA for upgrade *stability* - versions may have issues caught before reaching Stable

## Migration Process

### 1. Pre-migration Check
```bash
# Check current version and channel
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, releaseChannel.channel, nodePools[].version)"

# Check version availability in Stable
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels.STABLE)"
```

### 2. Execute Channel Migration
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel stable
```

**Migration timing:** This is a metadata change only - no immediate cluster disruption. The operation completes in ~2-3 minutes.

### 3. Verify Migration
```bash
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(releaseChannel.channel)"
```

## Post-Migration Behavior

### If 1.32 is available in Stable
- ✅ **No immediate upgrade** - cluster stays at 1.32
- ✅ **Normal auto-upgrade schedule** applies going forward
- ✅ **Maintenance windows and exclusions** continue to work

### If 1.32 is NOT yet available in Stable
- ⚠️ **Cluster will be "ahead" of its channel** temporarily
- ⚠️ **No auto-upgrades until 1.32 reaches Stable** - you'll stay frozen at 1.32
- ⚠️ **Manual upgrades blocked** - can't upgrade to versions not yet in Stable
- ✅ **No forced downgrade** - GKE won't downgrade you

## Recommended Approach

### Option A: Direct Migration (Recommended if 1.32 is in Stable)
Execute the migration immediately if version compatibility exists.

### Option B: Staged Migration (If 1.32 not in Stable yet)
1. **Wait 2-4 weeks** for 1.32 to reach Stable channel
2. **Then migrate** to avoid the temporary "ahead of channel" state
3. **Alternative:** Migrate now, accept the temporary freeze

### Option C: Step-down Migration
If you want immediate alignment:
1. Check what version IS available in Stable (likely 1.31.x)
2. Consider if downgrading to that version is acceptable
3. **Not recommended** - creates unnecessary disruption

## Multi-Environment Strategy

If you have dev/staging/prod environments:

```
Current (problematic):
├── Dev: Rapid
├── Staging: ?
└── Prod: Rapid → Stable

Recommended end state:
├── Dev: Rapid or Regular  
├── Staging: Regular
└── Prod: Stable
```

**Why this matters:** Having all environments on different channels makes rollout sequencing impossible and creates version drift. Plan your staging environment channel strategy alongside this production change.

## Maintenance Exclusions Consideration

Since you're moving to a more conservative channel, consider whether you need maintenance exclusions:

```bash
# Add "no minor or node upgrades" exclusion for maximum control
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "stable-channel-control" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

This gives you manual control over when minor version upgrades happen while still getting security patches.

## Action Plan

```
□ Check if 1.32 is available in Stable channel
□ If yes: Execute migration immediately
□ If no: Decide between waiting vs. accepting temporary freeze
□ Update monitoring/alerting for new upgrade cadence expectations
□ Plan staging environment channel alignment
□ Consider maintenance exclusions for additional control
□ Communicate timeline changes to stakeholders (slower upgrades)
```

The migration itself is safe and reversible, but the timing strategy depends on current version availability in your target channel.
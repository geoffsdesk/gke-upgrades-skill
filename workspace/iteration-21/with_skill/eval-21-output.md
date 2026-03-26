# Extended Channel Migration Plan

## Extended Channel Overview

Extended channel provides **up to 24 months of support** (vs 14 months on Regular/Stable) but has important operational differences:

### Key Tradeoffs

| Aspect | Regular Channel | Extended Channel |
|--------|----------------|------------------|
| **Minor version auto-upgrades** | Automatic | **MANUAL ONLY** (except at end of extended support) |
| **Patch auto-upgrades** | Automatic | Automatic |
| **Support duration** | 14 months | Up to 24 months |
| **Additional cost** | None | **Extra cost during extended period only** (months 15-24) |
| **Minor upgrade responsibility** | GKE handles timing | **You must plan and execute** |

### Critical Operational Impact

**Extended channel does NOT auto-upgrade minor versions** — you'll need internal processes to:
- Monitor when new minor versions become available
- Plan minor upgrade windows during the standard support period (months 1-14)
- Execute manual minor upgrades: `gcloud container clusters upgrade --cluster-version NEW_VERSION`
- Track version lifecycle to avoid reaching end of extended support

**This is the primary tradeoff:** Maximum control and extended support in exchange for manual minor upgrade responsibility.

## Migration Process

### Pre-migration Checks

```bash
# 1. Verify current version availability in Extended channel
gcloud container get-server-config --zone ZONE --format="yaml(channels.EXTENDED)"

# 2. Check if 1.31 is available in Extended
# If not available, you'll be "ahead of channel" until Extended catches up
```

### Migration Steps

```bash
# 1. Apply temporary "no upgrades" exclusion (prevents immediate auto-upgrade)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "channel-migration" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time $(date -u -d "+7 days" +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-scope no_upgrades

# 2. Switch to Extended channel
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended

# 3. Verify channel change
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(releaseChannel.channel)"

# 4. Remove temporary exclusion after verifying behavior
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "channel-migration"
```

### Recommended Extended Channel Configuration

For maximum control while maintaining security posture:

```bash
# Configure Extended channel with controlled upgrade policy
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support \
  --maintenance-patch-version-disruption-interval=7776000s \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

This gives you:
- **Auto-applied security patches** on control plane (respects maintenance window)
- **Manual control** over minor version and node upgrades
- **90-day minimum** between patch upgrades
- **Saturday 2-6 AM** maintenance window

## Operational Changes Needed

### 1. Minor Upgrade Planning Process

Create internal processes for:

**Quarterly version review:**
```bash
# Check available versions
gcloud container get-server-config --zone ZONE --format="yaml(channels.EXTENDED)"

# Check current cluster versions
gcloud container clusters describe CLUSTER_NAME --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].version)"

# Check EoS timeline
gcloud container clusters get-upgrade-info CLUSTER_NAME --zone ZONE
```

**Manual minor upgrade execution:**
```bash
# 1. Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version NEW_MINOR_VERSION

# 2. Then upgrade node pools (skip-level where possible)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version NEW_MINOR_VERSION
```

### 2. Monitoring and Alerting

Set up alerts for:
- New Extended channel versions available
- Current version approaching end of standard support (month 14)
- Current version approaching end of extended support (month 24)

### 3. Cost Management

**Extended channel cost structure:**
- **Months 1-14:** Standard pricing (no extra cost)
- **Months 15-24:** Additional cost for extended support
- Cost applies per cluster node hour during extended period

**Cost optimization strategy:**
- Plan minor upgrades during months 1-14 to minimize extended support costs
- Consider upgrading before month 15 for cost-sensitive workloads
- Use cost monitoring to track extended support charges

## Alternative: Regular Channel with Maximum Control

If the operational overhead of manual minor upgrades is too high, consider staying on Regular channel with tight controls:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support \
  --maintenance-patch-version-disruption-interval=7776000s
```

This provides similar control (manual minor upgrades) with 14-month support and no additional cost.

## Recommendation

**Proceed with Extended channel if:**
- You have mature change management processes
- You can commit to quarterly version planning
- Extended support cost is acceptable for production stability
- You need maximum flexibility around EoS enforcement

**Stay on Regular channel if:**
- You prefer fully automated lifecycle management
- Cost optimization is a primary concern
- You lack resources for manual upgrade planning

The Extended channel is ideal for regulated environments (financial services, healthcare) that need maximum control and extended support windows, but it requires operational maturity around version lifecycle management.
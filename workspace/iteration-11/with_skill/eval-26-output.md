# GKE 1.30 End of Support Impact Analysis

## What happens when 1.30 hits EoS

### Regular Channel Clusters (3 clusters)
- **Control plane + node pools automatically upgraded** to 1.31 (next supported minor version)
- **Timing**: Follows Regular channel auto-upgrade schedule once 1.30 reaches EoS
- **Can be deferred**: Apply "no upgrades" maintenance exclusion for up to 30 days past EoS
- **Enforcement**: Systematic - will eventually be force-upgraded

### Extended Channel Clusters (2 clusters) 
- **Extended support continues** - no forced upgrade at standard EoS date
- **1.30 remains supported** until end of extended support period (up to 24 months from original release)
- **Cost**: Additional charges apply during extended support period
- **Minor upgrades**: Must be initiated manually (only patches are auto-applied)
- **End of extended support**: Force upgrade to next supported version when extended period expires

### Legacy "No Channel" Cluster (1 cluster)
- **Control plane**: Auto-upgraded to 1.31 at EoS (systematic enforcement from 1.32+ onward)
- **Node pools**: Force-upgraded even if auto-upgrade is disabled
- **No escape**: Only 30-day "no upgrades" exclusion can defer temporarily

## Preparation Options by Cluster Type

### Option 1: Proactive Manual Upgrade (All clusters)
**Timeline**: Initiate upgrades before EoS enforcement

```bash
# Check current auto-upgrade targets
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.31.X-gke.XXXX

# Then upgrade node pools (Standard clusters only)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.X-gke.XXXX
```

### Option 2: Configure Auto-Upgrade Controls (Regular channel)

**"No minor or node upgrades" exclusion** (recommended for maximum control):
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "controlled-upgrades" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

This allows control plane security patches while blocking disruptive upgrades until you're ready.

### Option 3: Maintenance Window Optimization (All release channels)
```bash
# Set predictable upgrade window
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start 2024-12-15T02:00:00Z \
  --maintenance-window-end 2024-12-15T06:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"
```

### Option 4: Migrate Legacy Cluster to Release Channel
**High priority** - your "No channel" cluster lacks critical features:

```bash
# Migrate to Regular channel (closest to legacy behavior)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular

# Or Extended channel for maximum EoS flexibility
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

**Why migrate**: "No channel" lacks "no minor" exclusions, persistent exclusions, and extended support options.

## Recommended Action Plan

### Immediate (Next 2 weeks)
1. **Migrate the "No channel" cluster** to Regular or Extended channel
2. **Check 1.30 EoS timeline** - when exactly does support end?
3. **Test 1.31 compatibility** in dev/staging clusters

### Short-term (Before EoS)
1. **Regular channel clusters**: Apply "no minor or node upgrades" exclusions to control timing
2. **Extended channel clusters**: Decide if you want to stay on 1.30 (additional cost) or upgrade proactively
3. **Plan upgrade sequence**: Dev → Staging → Production with soak time between

### Node Pool Upgrade Strategy Recommendations

**For GPU pools**: Use `maxSurge=0, maxUnavailable=1` (assumes no surge GPU capacity)
**For stateless pools**: Use `maxSurge=3, maxUnavailable=0` for faster completion
**For stateful pools**: Use `maxSurge=1, maxUnavailable=0` with proper PDB configuration

## Cost Considerations

- **Extended channel**: Additional charges during extended support period (after standard 14 months)
- **Regular channel**: No additional charges, standard support timeline
- **Upgrade windows**: Manual upgrades during maintenance windows vs. waiting for auto-upgrade

Would you like me to create specific upgrade runbooks for any of these clusters, or help you determine the exact EoS timeline for your 1.30 clusters?
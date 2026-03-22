# GKE 1.30 End of Support Impact Analysis

## What happens at EoS for each cluster type

### Regular Channel Clusters (3 clusters)
- **Automatic enforcement**: When 1.30 reaches EoS, these clusters will be **automatically upgraded to 1.31** (next supported minor version)
- **Control plane + nodes**: Both will be upgraded together to maintain version alignment
- **Timing**: Upgrades will respect your maintenance windows and exclusions, but will eventually be enforced
- **No escape**: Cannot avoid the upgrade indefinitely - EoS enforcement is systematic

### Extended Channel Clusters (2 clusters) 
- **Extended support continues**: 1.30 on Extended channel gets up to **24 months total support** (vs 14 months on Regular)
- **No immediate enforcement**: These clusters can stay on 1.30 longer - EoS enforcement only happens at the end of extended support
- **Minor upgrades NOT automated**: You must manually initiate minor version upgrades (1.30→1.31). Only patches are auto-applied
- **Cost**: Additional charges apply during the extended support period (months 15-24)

### Legacy "No Channel" Cluster (1 cluster)
- **Systematic EoS enforcement**: Control plane will be force-upgraded to 1.31 when 1.30 reaches EoS
- **Node pools**: Also systematically upgraded, even if auto-upgrade is disabled
- **Limited exclusion options**: Only 30-day "no upgrades" exclusion available to temporarily defer

## Your preparation options

### Option 1: Proactive manual upgrades (Recommended)
Upgrade all clusters to 1.31+ before EoS enforcement kicks in:

```bash
# Check current auto-upgrade targets
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Manual upgrade to 1.31 (control plane first)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.31.x-gke.xxxx

# Then upgrade node pools
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.xxxx
```

### Option 2: Configure auto-upgrade controls
For Regular channel clusters, use maintenance exclusions to control timing:

```bash
# "No minor or node upgrades" - allows CP patches, blocks disruptive changes
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "q4-freeze" \
  --add-maintenance-exclusion-start-time 2024-11-15T00:00:00Z \
  --add-maintenance-exclusion-end-time 2025-01-15T00:00:00Z \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

### Option 3: Migrate "No channel" cluster to Extended
Move your legacy cluster to Extended channel for maximum flexibility:

```bash
# First add temporary "no upgrades" exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "migration-protection" \
  --add-maintenance-exclusion-start-time NOW \
  --add-maintenance-exclusion-end-time NOW+7days \
  --add-maintenance-exclusion-scope no_upgrades

# Migrate to Extended channel
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

## Recommended strategy by cluster

### Regular Channel Clusters (3)
1. **Set maintenance windows** during off-peak hours
2. **Apply "no minor or node upgrades" exclusions** if you need to control timing
3. **Let auto-upgrade handle it** - this is GKE's primary value proposition
4. **Alternative**: Manual upgrade to 1.31+ now if you want to get ahead of the schedule

### Extended Channel Clusters (2)
1. **Plan manual minor upgrades** - remember, these won't auto-upgrade to 1.31
2. **Budget for extended support costs** during months 15-24
3. **Upgrade to 1.31+ manually** when your schedule allows
4. **Monitor extended support timeline** - enforcement will eventually happen

### "No Channel" Cluster (1)
1. **Migrate to Extended channel** for maximum flexibility (recommended)
2. **Or migrate to Regular/Stable** for standard auto-upgrade behavior
3. **Never leave on "No channel"** - you lose access to powerful maintenance exclusion types

## Timeline considerations

- **EoS notifications**: GKE sends notifications 90 days, 30 days, and 7 days before EoS
- **Check your auto-upgrade targets**: Use `gcloud container clusters get-upgrade-info` to see when upgrades are scheduled
- **Progressive rollout**: Force upgrades happen over 4-5 business days across all regions
- **30-day emergency brake**: Use "no upgrades" exclusion if you need to defer temporarily

## Pre-upgrade checklist for 1.30→1.31

- [ ] Review [GKE 1.31 release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes) for breaking changes
- [ ] Check deprecated API usage: `kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated`  
- [ ] Verify PDBs aren't overly restrictive
- [ ] Test critical workloads in a staging cluster running 1.31
- [ ] Ensure all containers have resource requests (especially important for newer versions)

**Bottom line**: Your Regular channel clusters will be automatically protected through GKE's auto-upgrade system. Your Extended clusters give you manual control but require active management. Your "No channel" cluster should be migrated to a release channel for better tooling and control options.
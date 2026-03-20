# GKE 1.28 End of Support Impact & Preparation Plan

## What happens to each cluster type at EoS

### Regular Channel Clusters (3 clusters)
- **Auto-upgrade to 1.29**: When 1.28 reaches EoS, these clusters will be automatically upgraded to the next available minor version (1.29) in the Regular channel
- **Control plane + nodes**: Both will be upgraded together to maintain compatibility
- **Timing**: Upgrades happen during your configured maintenance windows, or immediately if no window is set
- **Cannot be prevented**: Standard EoS enforcement applies - the upgrade will happen

### Extended Channel Clusters (2 clusters) 
- **Extended support continues**: These clusters can stay on 1.28 beyond the standard EoS date
- **Support period**: Up to 24 months total support (instead of the standard 14 months)
- **Additional cost**: Extended support incurs extra charges
- **Eventually enforced**: Even Extended channel clusters will be force-upgraded when Extended support for 1.28 ends

### Legacy "No Channel" Cluster (1 cluster) ⚠️
- **Node-level enforcement**: Individual nodes on EoS versions are systematically force-upgraded
- **Control plane separate**: May remain on 1.28 longer, but nodes will upgrade
- **Version skew risk**: Could create unsupported version combinations
- **Limited control**: Lacks the maintenance exclusion features of release channels

## Your preparation options

### Option 1: Proactive manual upgrades (Recommended)
Upgrade all clusters to 1.29+ before EoS enforcement:

**Benefits:**
- Full control over timing
- Avoid forced upgrades during business hours
- Test and validate on your schedule

**Commands:**
```bash
# Check current versions and available targets
gcloud container get-server-config --zone ZONE --format="yaml(channels)"

# Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.29.X-gke.Y

# Then upgrade node pools (Standard only)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.29.X-gke.Y
```

### Option 2: Use maintenance exclusions to control timing

**For Regular channel clusters:**
```bash
# Apply "no minor or node upgrades" exclusion (recommended - allows CP security patches)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "eos-prep-exclusion" \
  --add-maintenance-exclusion-start-time $(date -Iseconds) \
  --add-maintenance-exclusion-end-time "2024-12-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

This gives you time to plan upgrades while still receiving control plane security patches.

### Option 3: Fix the legacy "No channel" cluster first

**Migrate to a release channel before EoS:**
```bash
# Recommended: Move to Regular channel (closest to legacy behavior)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular

# Alternative: Extended channel if you need maximum upgrade control
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

**Why this matters:** Release channels provide better maintenance exclusion options and predictable upgrade behavior compared to legacy "No channel."

## Recommended action plan

### Immediate (Week 1-2)
1. **Migrate the "No channel" cluster** to Regular or Extended channel
2. **Apply maintenance exclusions** on Regular channel clusters to prevent forced upgrades
3. **Inventory workloads** on all clusters - identify stateful apps, GPU workloads, custom operators

### Short-term (Week 2-4)  
1. **Test 1.29** in a staging environment or one non-critical cluster
2. **Validate compatibility** - check deprecated APIs, third-party operators, admission webhooks
3. **Configure maintenance windows** for predictable upgrade timing
4. **Review node pool upgrade strategies** (surge settings, PDB configurations)

### Execute upgrades (Month 2)
1. **Dev clusters first** - validate applications work on 1.29
2. **Production clusters** - use lessons learned, upgrade during maintenance windows
3. **Monitor closely** - watch for workload issues, performance regressions

## Key considerations for 1.28 → 1.29 upgrade

- **API removals**: Check for deprecated APIs using `kubectl get --raw /metrics | grep deprecated`
- **Breaking changes**: Review [GKE 1.29 release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes) 
- **Node image changes**: GPU drivers may update with new CUDA versions
- **Workload disruption**: All upgrades require pod restarts (no live migration for VMs)

## Timeline awareness

- **1.28 EoS approaching**: Check the [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) for exact dates
- **Extended support costs**: Factor in additional charges if keeping Extended channel clusters on 1.28
- **Progressive rollout**: When forced upgrades begin, they roll out across regions over 4-5 business days

The combination of proactive manual upgrades + maintenance exclusions gives you maximum control while avoiding the risks of forced upgrades during business hours.
# GKE 1.30 End of Support Analysis & Migration Plan

## What happens at EoS for each cluster type

### Regular channel clusters (3 clusters)
- **Automatic upgrade to 1.31**: When 1.30 reaches EoS, these clusters will be force-upgraded to the next supported minor version (1.31) automatically
- **Control plane + nodes**: Both will be upgraded together to maintain version alignment
- **Timing**: Upgrades will respect your maintenance windows but **ignore maintenance exclusions** at EoS enforcement
- **No escape**: Cannot be deferred beyond EoS date except with temporary "no upgrades" exclusion (30 days max)

### Extended channel clusters (2 clusters) 
- **Extended support period**: 1.30 gets up to **24 months total support** instead of standard 14 months
- **Cost during extended period**: Additional charges apply **only during the extended support period** (months 15-24). No extra cost during standard support (months 1-14)
- **Manual minor upgrades required**: During extended support, minor version upgrades are **NOT automated**. You must manually upgrade from 1.30→1.31→1.32, etc. Only patches are auto-applied
- **EoS enforcement delayed**: Force-upgrade only happens at the end of extended support (~10 months from now)

### Legacy "No channel" cluster (1 cluster) ⚠️
- **Systematic EoS enforcement**: Node pools on EoS versions are force-upgraded automatically
- **Limited exclusion options**: Only "no upgrades" (30-day max) exclusions available - no "no minor" options
- **Missing features**: No Extended support, no persistent exclusions, no rollout sequencing
- **Recommendation**: **Migrate to a release channel immediately** before EoS hits

## Preparation options by cluster type

### For Regular channel clusters

**Option A - Let auto-upgrade happen (recommended for most):**
```bash
# Ensure maintenance windows are set for off-peak hours
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --maintenance-window-start "2024-01-01T02:00:00Z" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Option B - Upgrade proactively before EoS:**
- Upgrade to 1.31 now during a planned maintenance window
- Test 1.31 in dev/staging first
- Avoid the uncertainty of forced upgrade timing

**Option C - Brief deferral (emergency only):**
```bash
# 30-day maximum deferral
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "eos-deferral" \
    --add-maintenance-exclusion-start YYYY-MM-DDTHH:MM:SSZ \
    --add-maintenance-exclusion-end YYYY-MM-DDTHH:MM:SSZ \
    --add-maintenance-exclusion-scope no_upgrades
```

### For Extended channel clusters

**Option A - Stay on Extended (maximum flexibility):**
- No immediate action required
- Plan manual minor upgrades during the extended period
- Monitor for 1.31 compatibility issues in your dev environment
- Budget for extended support costs (~10 months from now)

**Option B - Migrate to Regular/Stable for auto-upgrade:**
```bash
# Move to Regular for balanced auto-upgrade cadence
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --release-channel regular
    
# Add persistent exclusion for maximum control
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
```

### For "No channel" cluster ⚠️ URGENT

**Immediate action required - migrate to release channel:**

```bash
# Option 1: Regular channel (closest to legacy behavior)
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --release-channel regular

# Option 2: Extended channel (maximum flexibility + cost)
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --release-channel extended
```

**Why migrate NOW:**
- "No channel" lacks powerful exclusion types ("no minor or node upgrades")
- No Extended support option (24 months)
- Missing rollout sequencing and persistent exclusions
- EoS enforcement is systematic and unavoidable

## Recommended migration strategy

### Phase 1: Immediate (this week)
- [ ] **Migrate "No channel" cluster to Extended channel** - gives maximum time and flexibility
- [ ] **Set maintenance windows on all clusters** for predictable upgrade timing
- [ ] **Take application-level backups** of stateful workloads before any upgrades

### Phase 2: Validation (next 2 weeks)  
- [ ] **Test 1.31 compatibility** in dev/staging environment
- [ ] **Check deprecated API usage**: `kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated`
- [ ] **Review GKE 1.31 release notes** for breaking changes
- [ ] **Verify admission webhooks** (cert-manager, etc.) support 1.31

### Phase 3: Production upgrades (planned maintenance windows)
- [ ] **Regular channel clusters**: Either upgrade proactively or let auto-upgrade happen
- [ ] **Extended channel clusters**: Choose to stay Extended or migrate to Regular based on operational preference

## Pre-upgrade checklist for all clusters

```bash
# Check current versions and auto-upgrade status
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Verify deprecated API usage
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Check PDB configurations aren't overly restrictive
kubectl get pdb -A -o wide

# Ensure all pods have controllers (no bare pods)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

## Key timeline considerations

- **1.30 EoS date**: Check the [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) for exact date
- **Regular channel**: Force-upgrade will happen at EoS regardless of exclusions
- **Extended channel**: ~10 additional months before force-upgrade
- **Migration safety**: Moving between channels during maintenance windows prevents unexpected immediate upgrades

The "No channel" cluster is your highest priority - migrate it immediately to avoid getting stuck with limited options at EoS enforcement.
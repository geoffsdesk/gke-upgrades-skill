# GKE 1.30 End of Support Impact & Preparation Plan

## What happens at EoS for each cluster type

### Regular Channel Clusters (3 clusters)
**What happens:** Systematic force-upgrade to 1.31 when 1.30 reaches EoS
- Control plane upgraded first, then all node pools
- Upgrade happens automatically regardless of maintenance windows
- Only a 30-day "no upgrades" exclusion can defer (temporarily)

### Extended Channel Clusters (2 clusters) 
**What happens:** **No forced upgrade at standard EoS** — this is Extended's key benefit
- 1.30 continues receiving patches during extended support period (up to 24 months total)
- Additional cost applies only during extended period (after standard 14-month support ends)
- Force-upgrade only occurs at end of extended support (~10 months from now)

### Legacy "No Channel" Cluster (1 cluster)
**What happens:** Same as Regular channel — systematic force-upgrade to 1.31 at EoS
- Despite being "No channel," EoS enforcement applies equally
- Per-nodepool "disable auto-upgrade" settings are overridden during EoS enforcement

## Timeline & Preparation Options

### Immediate Action Required: Legacy "No Channel" Migration
**High Priority:** Migrate your "No channel" cluster to a release channel before EoS hits:

```bash
# Option 1: Migrate to Regular (closest to current behavior)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular

# Option 2: Migrate to Extended (maximum flexibility, same behavior as your other Extended clusters)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

**Why migrate:** Extended channel gives you the same EoS deferral benefit as your other Extended clusters. Regular gives you standard auto-upgrade behavior with better control tools than "No channel."

### Options for Regular Channel Clusters (3 clusters)

**Option A: Proactive manual upgrade (recommended)**
Upgrade to 1.31+ before EoS enforcement kicks in:
```bash
# Control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.31.X-gke.Y

# Then node pools
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.X-gke.Y
```

**Option B: Migrate to Extended channel**
Buy more time (up to 24 months total support):
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```
Cost implication: Additional charges apply only during extended period.

**Option C: Temporary deferral**
Apply "no upgrades" exclusion for up to 30 days:
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "eos-deferral" \
  --add-maintenance-exclusion-start-time "2024-XX-XXTXX:XX:XXZ" \
  --add-maintenance-exclusion-end-time "2024-XX-XXTXX:XX:XXZ" \
  --add-maintenance-exclusion-scope no_upgrades
```
This only delays the inevitable — plan your upgrade within the 30-day window.

## Recommended Action Plan

### Week 1: Assessment & Channel Migration
1. **Check 1.30 EoS date:** `gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION`
2. **Migrate "No channel" cluster** to Extended channel (immediate)
3. **Review deprecated APIs** across all clusters:
   ```bash
   kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
   ```

### Week 2-3: Upgrade Planning
For Regular channel clusters, choose your path:
- **Path A:** Manual upgrade to 1.31+ (full control, immediate)
- **Path B:** Migrate to Extended channel (buy time, additional cost)
- **Path C:** Accept force-upgrade (happens automatically, least control)

### Week 4: Execute Plan
- Apply temporary exclusions if needed for timing control
- Execute manual upgrades during maintenance windows
- Validate workload health post-upgrade

## Key Considerations

**Extended Channel Benefits:**
- No force-upgrade at standard EoS (your 2 clusters are safe)
- Up to 24 months total support
- Additional cost only during extended period

**Version Compatibility:**
- All clusters can safely upgrade 1.30→1.31 (single minor version jump)
- Node pools can skip-level upgrade if control plane is already at 1.31+

**Breaking Changes:**
Check [GKE release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes) for 1.30→1.31 breaking changes, especially:
- Deprecated API removals
- System component changes
- Networking or storage behavior changes

## Monitoring EoS Status

Set up proactive monitoring:
```bash
# Check auto-upgrade status
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Monitor EoS notifications in Cloud Logging
resource.type="gke_cluster" 
jsonPayload.reason="MinorVersionAtOrNearEndOfSupport"
```

**Next Steps:** Start with migrating your "No channel" cluster to Extended channel today, then assess whether your Regular channel clusters need manual upgrades or Extended migration based on your risk tolerance and upgrade timeline.
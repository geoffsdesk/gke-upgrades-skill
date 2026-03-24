# GKE 1.30 End of Support Impact Assessment

Based on your cluster topology, here's what will happen to each cluster type when GKE 1.30 reaches End of Support, plus your preparation options.

## Impact by Cluster Configuration

### Regular Channel Clusters (3 clusters)
**What happens at EoS:**
- **Automatic upgrade to 1.31** - Both control plane and all node pools will be force-upgraded to the next supported minor version
- **No way to avoid it** except temporary 30-day "no upgrades" exclusions
- **Timing:** Follows Regular channel auto-upgrade schedule (typically 2-4 weeks after 1.31 reaches "auto-upgrade target" status in Regular)

### Extended Channel Clusters (2 clusters)  
**What happens at EoS:**
- **Standard support period (14 months):** Same as Regular - automatic upgrade to 1.31
- **Extended support period (up to 24 months):** No automatic minor upgrades during extended period
- **At end of extended support:** Force-upgrade to next supported minor version
- **Key advantage:** You control when to upgrade during the extended period, but patches are still auto-applied

### Legacy "No Channel" Cluster (1 cluster)
**What happens at EoS:**
- **Control plane:** Force-upgraded to 1.31 (follows Stable channel EoS timeline)
- **Node pools:** Force-upgraded to 1.31 even if "no auto-upgrade" is configured
- **No exceptions** except 30-day "no upgrades" exclusions
- **Systematic enforcement:** GKE 1.32+ has systematic EoS enforcement - no cluster stays on EoS versions

## Your Preparation Options

### Option 1: Proactive Manual Upgrades (Recommended)
**Timeline:** Before EoS enforcement begins

**Commands for each cluster type:**
```bash
# Check current auto-upgrade targets
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Manual control plane upgrade (all cluster types)
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version 1.31.X-gke.XXXX

# Manual node pool upgrade (Standard clusters only)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.31.X-gke.XXXX
```

**Advantages:**
- Control timing and sequencing
- Test in dev/staging first
- Validate workloads before production
- Avoid forced upgrades during business hours

### Option 2: Maintenance Exclusions + Controlled Auto-upgrade
**For Regular channel clusters:**
```bash
# Add "no minor or node upgrades" exclusion to control timing
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "planned-upgrade-window" \
  --add-maintenance-exclusion-start-time 2024-XX-XXTHH:MM:SSZ \
  --add-maintenance-exclusion-end-time 2024-XX-XXTHH:MM:SSZ \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

**For Extended channel clusters:**
- Extended clusters don't auto-upgrade during extended support period
- Plan manual upgrades during maintenance windows

**For "No channel" cluster:**
```bash
# Only 30-day "no upgrades" exclusions available
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "emergency-freeze" \
  --add-maintenance-exclusion-start-time 2024-XX-XXTHH:MM:SSZ \
  --add-maintenance-exclusion-end-time 2024-XX-XXTHH:MM:SSZ \
  --add-maintenance-exclusion-scope no_upgrades
```

### Option 3: Migrate "No Channel" Cluster (Strongly Recommended)
**Before dealing with the upgrade, migrate your legacy cluster:**

```bash
# Migrate to Regular channel (closest to legacy behavior)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --release-channel regular

# Or migrate to Extended for maximum control
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --release-channel extended
```

**Why migrate first:**
- Access to better maintenance exclusion types ("no minor or node upgrades" vs just "no upgrades")
- Extended channel option for 24-month support
- Consistent fleet management
- Future-proofing for better upgrade controls

## Recommended Action Plan

### Phase 1: Immediate (Next 2 weeks)
1. **Migrate the "No channel" cluster** to Regular or Extended channel
2. **Check GKE 1.31 compatibility** in your dev environment:
   ```bash
   # Test deprecated API usage
   kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
   
   # Check GKE deprecation insights
   gcloud recommender insights list \
     --insight-type=google.container.DiagnosisInsight \
     --location=REGION \
     --project=PROJECT_ID
   ```
3. **Configure maintenance windows** for all clusters (off-peak hours)

### Phase 2: Testing (Weeks 3-4)
1. **Manually upgrade 1 Regular channel cluster** to 1.31 as a pilot
2. **Validate all workloads** - check for API compatibility issues
3. **Test rollback procedures** on the pilot cluster

### Phase 3: Production Rollout (Weeks 5-6)
1. **Sequence remaining clusters:** Dev → Staging → Production
2. **Use maintenance exclusions** to control exact timing if needed
3. **Extended channel clusters:** Plan manual upgrades during maintenance windows

### Phase 4: Extended Channel Decision
For your 2 Extended channel clusters, decide:
- **Upgrade now** to stay current with the fleet
- **Use extended support** for up to 24 months if you need stability
- **Note:** Extended support has additional costs during the extended period

## Timeline Considerations

**GKE 1.30 EoS timeline:**
- Standard support ends ~14 months after 1.30 GA
- Extended support available until ~24 months after GA (for Extended channel only)
- Check exact dates: `gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION`

**Force upgrade timing:**
- Regular channel: 2-4 weeks after 1.31 reaches auto-upgrade target
- Extended channel: At end of standard support (unless you're in extended period)
- "No channel": Follows Stable channel timeline for EoS enforcement

## Monitoring and Alerts

Set up proactive monitoring:
```bash
# Enable scheduled upgrade notifications (72h advance warning)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --send-scheduled-upgrade-notifications

# Monitor EoS status programmatically
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION \
  --format="table(name,endOfStandardSupportTimestamp,endOfExtendedSupportTimestamp)"
```

The key is taking proactive control rather than waiting for forced upgrades. Your Regular channel clusters will be upgraded automatically, but you can control the timing. Your Extended channel clusters give you the most flexibility, and your "No channel" cluster should be migrated first to gain access to better control mechanisms.
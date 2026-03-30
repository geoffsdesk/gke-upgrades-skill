# GKE 1.30 End of Support Impact & Preparation Plan

## EoS Timeline for 1.30
- **Standard support ends:** March 2025 (approximately)
- **Extended support ends:** March 2027 (for Extended channel clusters only)
- **EoS enforcement:** Systematic force-upgrade when standard support expires

## Impact by Cluster Configuration

### Regular Channel Clusters (3 clusters)
**What happens at EoS:**
- **Automatic force-upgrade** to 1.31 (next supported minor version)
- Both control plane AND node pools upgraded together
- No way to prevent this except temporary "no upgrades" exclusion (30 days max)
- Upgrade will happen regardless of maintenance windows

**Timeline:**
- EoS enforcement triggers in March 2025
- Clusters will be upgraded to whatever 1.31 patch is the auto-upgrade target in Regular channel at that time

### Extended Channel Clusters (2 clusters) 
**What happens at EoS:**
- **No immediate action** — Extended channel provides up to 24 months support
- Standard EoS (March 2025): Clusters continue running 1.30, receiving patches
- Extended EoS (March 2027): Force-upgrade to next supported version
- **Important:** You pay extra cost only during the extended period (Mar 2025 - Mar 2027)

**Key insight:** Extended channel does NOT auto-upgrade minor versions during normal operations — you control when minor upgrades happen, but patches are still auto-applied.

### Legacy "No Channel" Cluster (1 cluster)
**What happens at EoS:**
- **Automatic force-upgrade** to 1.31, same as Regular channel
- No special protection from being on "No channel"
- EoS enforcement applies equally to all cluster types

## Preparation Options

### Option 1: Proactive Manual Upgrade (Recommended)
**Timeline:** Complete by February 2025 (before EoS enforcement)

**Benefits:**
- You control timing and sequencing
- Validate each cluster individually
- Apply lessons learned between clusters
- Avoid potential issues during mass EoS enforcement

**Upgrade sequence:**
1. Extended channel clusters first (lowest risk, you're already paying for extended support)
2. Regular channel dev/staging clusters
3. Regular channel production clusters
4. Legacy "No channel" cluster last (after migrating to a release channel)

### Option 2: Migrate Legacy Cluster to Extended Channel
**For the "No channel" cluster:**
```bash
# Migrate to Extended channel for maximum flexibility
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

**Benefits:**
- Gains 24-month support window
- Gets access to better maintenance exclusion controls
- Avoids March 2025 EoS enforcement
- Aligns with your other Extended clusters

### Option 3: Use Maintenance Exclusions to Control Timing
**For clusters that must defer:**
```bash
# Apply "no upgrades" exclusion before EoS enforcement begins
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "defer-eos-upgrade" \
  --add-maintenance-exclusion-start-time "2025-02-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-03-02T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

**Limitations:**
- Maximum 30 days deferral per exclusion
- Can chain up to 3 exclusions, but accumulates security debt
- Only delays the inevitable — doesn't prevent EoS upgrade

## Recommended Action Plan

### Immediate Actions (Next 30 days)
1. **Audit deprecated API usage** across all clusters:
   ```bash
   kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
   ```
2. **Check GKE deprecation insights** in console for each cluster
3. **Migrate the "No channel" cluster** to Extended channel
4. **Review 1.30→1.31 breaking changes** in GKE release notes

### Phase 1: Extended Channel Clusters (January 2025)
- Start with these since you have longest support window
- Use as validation for upgrade process
- Apply lessons learned to Regular channel clusters

### Phase 2: Regular Channel Clusters (February 2025)
- Dev/staging first, production last
- Complete before March 2025 EoS enforcement
- Monitor for any workload compatibility issues

### Emergency Preparation
If you can't upgrade before EoS enforcement:
1. **Apply maintenance exclusions** to defer by 30 days
2. **Scale down non-critical workloads** to reduce blast radius
3. **Take application backups** before forced upgrade
4. **Have incident response team available** during enforcement window

## Version Compatibility Notes

**1.30→1.31 key changes to validate:**
- Check admission webhook compatibility
- Verify HPA/VPA behavior (scaling algorithms may change)
- Test service mesh control plane compatibility (Istio/ASM)
- Validate GPU driver versions if using accelerated nodes

**Commands for validation:**
```bash
# Check control plane upgrade readiness
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Verify no deprecated API usage
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=LOCATION \
  --project=PROJECT_ID \
  --filter="category.category:RELIABILITY"
```

## Cost Implications

- **Extended channel clusters:** Extra cost applies March 2025 - March 2027 only
- **Migrating "No channel" to Extended:** No immediate cost, starts billing in March 2025
- **Staying on Regular:** No additional Extended support costs

**Bottom line:** You have roughly 60 days to either upgrade proactively or prepare for automatic EoS enforcement. The Extended channel clusters give you breathing room, but the Regular and "No channel" clusters need immediate attention.
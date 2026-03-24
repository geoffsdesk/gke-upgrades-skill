# GKE 1.30 End of Support Impact Analysis

## EoS Timeline for 1.30

**GKE 1.30 End of Support:** February 28, 2025 (confirmed)
**Extended Support End:** February 28, 2027 (for Extended channel clusters)

## Impact by Cluster Configuration

### Regular Channel Clusters (3 clusters)
**What happens at EoS:**
- **Control plane:** Auto-upgraded to 1.31 (next supported minor version)
- **Node pools:** Auto-upgraded to 1.31 following cluster-level maintenance policies
- **Timing:** Upgrades happen within your maintenance windows, respecting any active maintenance exclusions
- **No escape:** Cannot avoid this upgrade once 1.30 hits EoS on Feb 28, 2025

### Extended Channel Clusters (2 clusters) 
**What happens at EoS:**
- **Through Feb 28, 2027:** Continue receiving security patches, NO forced minor upgrades
- **Minor upgrades:** Must be initiated manually - Extended channel does NOT auto-upgrade minor versions (except at end of extended support)
- **At end of extended support (Feb 2027):** Force-upgraded to next supported minor
- **Cost:** Additional charges apply during extended support period (Feb 2025 - Feb 2027)

### Legacy "No Channel" Cluster (1 cluster)
**What happens at EoS:**
- **Control plane:** Force-upgraded to 1.31 immediately at EoS
- **Node pools:** Force-upgraded even with auto-upgrade disabled - this is systematic enforcement
- **Limited protection:** Only 30-day "no upgrades" exclusion can delay (but accumulates security debt)

## Preparation Options by Priority

### Immediate Actions (Next 30 Days)

**1. Migrate the "No channel" cluster to Extended channel**
```bash
# This gives you maximum control and delays EoS enforcement until 2027
gcloud container clusters update LEGACY_CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

**Why Extended over Regular/Stable:**
- Extended channel provides up to 24 months support vs 14 months
- Manual control over minor upgrades (no auto-upgrade except at end of extended support)
- Best migration path for customers wanting maximum flexibility around EoS enforcement

**2. Configure maintenance exclusions for controlled timing**

For maximum upgrade control (recommended for production):
```bash
# "No minor or node upgrades" - allows CP security patches only
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

For temporary freeze during critical periods:
```bash
# "No upgrades" - blocks everything for up to 30 days
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "eos-prep" \
  --add-maintenance-exclusion-start "2025-01-15T00:00:00Z" \
  --add-maintenance-exclusion-end "2025-02-14T00:00:00Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

### Medium-term Strategy (Next 60 Days)

**3. Plan manual upgrades ahead of EoS enforcement**

Best practice: Upgrade manually in January 2025, before the February EoS deadline:

```bash
# Control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.31.X-gke.XXXX

# Then node pools (can skip-level upgrade 1.30→1.31)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.X-gke.XXXX
```

**4. Validate 1.31 compatibility now**

Critical pre-upgrade checks:
```bash
# Check for deprecated APIs (most common upgrade failure)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Check GKE deprecation insights
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=LOCATION \
  --project=PROJECT_ID
```

**5. Set up EoS monitoring**

```bash
# Enable scheduled upgrade notifications (72h advance warning)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --send-scheduled-upgrade-notifications
```

Monitor via Cloud Logging:
```
resource.type="gke_cluster" 
protoPayload.metadata.operationType=~"(UPDATE_CLUSTER|UPGRADE_MASTER)"
```

## Recommended Strategy by Cluster Type

### Production Clusters → Extended Channel
- Migrate to Extended channel for maximum control
- Use "no minor or node upgrades" exclusion for patch-only auto-upgrades
- Plan manual minor upgrades during maintenance windows
- Total cost: Extended support fees during Feb 2025-Feb 2027 period

### Dev/Test Clusters → Stay on Regular
- Let auto-upgrade handle EoS enforcement
- Configure maintenance windows for acceptable timing
- Use as validation pipeline for production upgrades

## Timeline Summary

| Date | Regular Channel | Extended Channel | Legacy "No Channel" |
|------|----------------|------------------|-------------------|
| **Now - Jan 2025** | Plan manual upgrade to 1.31 | Plan manual upgrade or accept Extended support cost | **Migrate to Extended immediately** |
| **Feb 28, 2025** | **Force-upgrade to 1.31** | Enters extended support, patches only | **Force-upgrade to 1.31** |
| **Feb 28, 2027** | N/A | **Force-upgrade if still on 1.30** | N/A |

## Cost Implications

**Extended Channel:** Additional fees apply only during extended support period (Feb 2025 - Feb 2027). No extra cost during standard support period (now through Feb 2025).

**Migration recommendation:** Move the "No channel" cluster to Extended channel now - this gives you the most flexibility and delays forced EoS enforcement by 2 years.

Would you like me to create specific upgrade runbooks for any of these clusters, or help you configure the maintenance exclusions for controlled upgrade timing?
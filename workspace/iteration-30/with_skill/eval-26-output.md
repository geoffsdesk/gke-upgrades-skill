## GKE 1.30 End of Support Impact Analysis

Here's exactly what will happen to each cluster type when GKE 1.30 reaches End of Support:

### Clusters on Regular Channel (3 clusters)
**What happens at EoS:**
- ✅ **Systematic force-upgrade to 1.31** (next supported minor version)
- ✅ **Both control plane AND node pools** upgraded automatically
- ✅ **No way to avoid** except temporary 30-day "no upgrades" exclusion

**Timeline:** 1.30 EoS is estimated for **late Q2 2025** based on the 14-month standard support period.

### Clusters on Extended Channel (2 clusters) 
**What happens at EoS:**
- ✅ **Extended support continues until ~Q2 2026** (24 months total)
- ✅ **No forced upgrade at standard EoS** — you get an additional ~12 months
- ✅ **Patches continue** throughout extended period at Regular channel timing
- ⚠️ **Additional cost applies** only during the extended support period (after standard EoS)
- ⚠️ **Force-upgrade at end of extended support** if still on 1.30

### Legacy "No Channel" Cluster (1 cluster)
**What happens at EoS:**
- ✅ **Systematic force-upgrade to 1.31** (same as Regular channel)
- ✅ **Both control plane AND node pools** upgraded automatically
- ⚠️ **Per-nodepool exclusions ignored** during EoS enforcement
- ⚠️ **Limited exclusion options** — only 30-day "no upgrades" type available

## Recommended Action Plan

### Immediate Actions (Next 30 Days)

**1. Migrate the "No Channel" cluster to Extended channel:**
```bash
# Check current version first
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion,releaseChannel.channel)"

# Migrate to Extended (best option for maximum EoS flexibility)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

**Why Extended over Regular?** Extended gives you the same 24-month support as your existing Extended clusters, plus better exclusion options than "No channel."

**2. Audit deprecated API usage across all clusters:**
```bash
# Check each cluster for deprecated APIs (most common upgrade failure cause)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Also check GKE deprecation insights
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=LOCATION \
  --project=PROJECT_ID \
  --filter="category.category:RELIABILITY"
```

### Strategy Options by Timeline

**Option A: Proactive Manual Upgrade (Recommended)**
- **When:** Q1 2025 (before EoS pressure)
- **Target:** GKE 1.31 (current latest minor)
- **Benefits:** Full control over timing, validation, and rollback options
- **Process:** Test 1.30→1.31 in staging, then production during planned maintenance windows

**Option B: Extended Support (Extended channel clusters only)**
- **When:** Let standard EoS pass, operate in extended support
- **Duration:** Until ~Q2 2026
- **Benefits:** Maximum time for planning and validation
- **Cost:** Additional charges apply during extended period
- **Process:** Plan upgrade for late 2025/early 2026

**Option C: Last-Minute Deferral (All clusters)**
- **When:** Just before EoS enforcement
- **Method:** Apply 30-day "no upgrades" exclusion
- **Limitation:** Can only defer 30 days maximum per exclusion
- **Risk:** Forced upgrade with accumulated technical debt

## Upgrade Planning Considerations

### Version Path Analysis
- **Current:** 1.30.x
- **Required next:** 1.31.x (control plane must upgrade sequentially)
- **Node pools:** Can skip-level upgrade 1.30→1.32 once control plane reaches 1.32

### Key Compatibility Checks
1. **Deprecated APIs:** 1.31 removed several beta APIs. Run deprecation scans now.
2. **Third-party operators:** Verify Istio, cert-manager, monitoring operators support 1.31
3. **Custom admission webhooks:** Test against 1.31 API changes
4. **GPU drivers:** If using GPU nodes, verify driver compatibility with 1.31 node images

### Workload-Specific Preparations
```bash
# Review PodDisruptionBudgets (will block upgrades if too restrictive)
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# Check for bare pods (won't reschedule during node upgrades)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# Verify StatefulSet backup procedures
kubectl get statefulsets -A
```

## Recommended Timeline

| Timeframe | Action |
|-----------|--------|
| **Now - Jan 2025** | Migrate "No channel" to Extended, audit deprecated APIs, test 1.31 in dev |
| **Q1 2025** | Manual upgrade Regular channel clusters (3) to 1.31 during maintenance windows |
| **Q2 2025** | Monitor EoS notifications, decide on Extended cluster strategy |
| **2025-2026** | Extended clusters: either upgrade proactively or operate in extended support |

## Configuration Commands for Each Scenario

**Set up maintenance exclusion for maximum control (all clusters):**
```bash
# "No minor or node upgrades" - allows CP patches, blocks minor+node versions
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Manual upgrade when ready:**
```bash
# Control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.31.LATEST

# Then node pools (can be done concurrently across pools)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.LATEST
```

**Monitor upgrade readiness:**
```bash
# Check auto-upgrade status and EoS dates
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION
```

## Key Takeaway

Your **Extended channel clusters give you the most flexibility** — they can safely operate through 2026 with continued patch support. The **Regular channel clusters need attention by Q1 2025** to avoid forced upgrades. The **"No channel" cluster should be migrated immediately** to Extended for better upgrade control options.

The systematic EoS enforcement is real and will happen — but you have good options to control the timing if you act proactively.
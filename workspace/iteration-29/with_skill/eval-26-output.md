# GKE 1.30 End of Support Impact Analysis

## What happens at EoS (systematic enforcement)

**All your clusters will be force-upgraded when 1.30 reaches End of Support, regardless of channel configuration.** GKE's EoS enforcement is systematic starting with 1.32+ versions, but 1.30 will also be subject to enforcement.

### Specific behavior by cluster type:

**Regular channel clusters (3 clusters):**
- **Control plane**: Force-upgraded to 1.31 (next supported minor)
- **Node pools**: Force-upgraded to 1.31 simultaneously
- **Timing**: Happens automatically when 1.30 reaches EoS
- **Override**: Only temporary via "no upgrades" exclusion (30 days max)

**Extended channel clusters (2 clusters):**
- **Control plane**: Force-upgraded to 1.31 when extended support ends (up to 24 months after standard EoS)
- **Node pools**: Follow control plane version
- **Timing**: Delayed until end of extended support period
- **Cost**: Additional charges apply during extended support period only

**Legacy "No channel" cluster (1 cluster):**
- **Control plane**: Force-upgraded to 1.31 at EoS
- **Node pools**: Force-upgraded even if auto-upgrade is disabled per-nodepool
- **Timing**: Same as Regular channel pace for EoS enforcement
- **Override**: Only via "no upgrades" exclusion (30 days max)

## Your preparation options

### Option 1: Controlled manual upgrade (recommended)

**Before EoS hits**, manually upgrade each cluster 1.30→1.31 with full control:

```bash
# Check current auto-upgrade targets first
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Control plane upgrade (do this first on all clusters)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.31.x-gke.xxxx

# Node pool upgrade (Standard clusters only - skip for Autopilot)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.xxxx
```

**Advantages:**
- You control timing and rollout sequence
- Can test in dev/staging first
- Can prepare workloads and resolve issues beforehand
- Can coordinate with maintenance windows

### Option 2: Configure auto-upgrade controls

Let auto-upgrades handle it but with timing/scope controls:

```bash
# Set maintenance windows for predictable timing
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-12-07T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Optional: Add "no minor or node upgrades" exclusion for maximum control
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

### Option 3: Defer with "no upgrades" exclusion

Temporarily block the EoS upgrade while you prepare:

```bash
# Maximum 30-day deferral
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "eos-preparation" \
  --add-maintenance-exclusion-start-time "2024-12-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-31T00:00:00Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

**⚠️ Warning:** This accumulates security debt - you'll miss patches for 30 days.

## Special considerations for your fleet

### Legacy "No channel" cluster migration

**Strongly recommend migrating off "No channel" before the EoS upgrade:**

```bash
# Check current version availability in target channel
gcloud container get-server-config --zone ZONE --format="yaml(channels)"

# Migrate to Regular channel (closest to legacy behavior)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular
```

**Benefits of migration:**
- Access to modern maintenance exclusion types ("no minor or node upgrades")
- Rollout sequencing capability for multi-cluster coordination
- Extended support option (move to Extended channel)
- Better upgrade control tools

### Extended channel leverage

Your Extended channel clusters have the **most flexibility**:
- Can defer EoS enforcement until end of extended support (up to 24 months)
- Manual control over minor version upgrades
- Still receive security patches automatically

**Consider moving other production clusters to Extended** for maximum control:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

## Pre-upgrade preparation checklist

```markdown
- [ ] **Check for deprecated API usage** (most common upgrade failure):
  - GKE deprecation insights in console
  - `kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated`
  
- [ ] **Review breaking changes** in [GKE 1.31 release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes#January_08_2024)

- [ ] **Test in staging**: Create a test 1.31 cluster and validate your workloads

- [ ] **PDB audit**: Ensure PDBs aren't overly restrictive
  - `kubectl get pdb -A -o wide`
  - Look for ALLOWED DISRUPTIONS = 0

- [ ] **Workload compatibility**:
  - Admission webhooks (cert-manager, etc.) support K8s 1.31
  - Service mesh control plane version compatibility
  - Any custom operators/controllers

- [ ] **Backup critical data** (stateful workloads)
```

## Recommended rollout sequence

1. **Week 1**: Upgrade Regular channel dev/staging clusters manually
2. **Week 2**: Validate applications, fix any issues found
3. **Week 3**: Upgrade Regular channel production clusters (manually or via maintenance window)
4. **Week 4**: Migrate and upgrade the "No channel" cluster
5. **Extended clusters**: Leverage extended support timeline or upgrade when convenient

## Timeline awareness

Check the [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) for 1.30 EoS dates. The Extended channel gives you breathing room, but don't wait until the last minute for Regular channel clusters.

**Key insight**: Manual upgrades bypass ALL maintenance controls (windows and exclusions), so you can upgrade immediately even with restrictive settings. The controls only affect auto-upgrades.

Would you like me to create specific upgrade runbooks for any of these clusters, or help you set up the maintenance exclusions for controlled timing?
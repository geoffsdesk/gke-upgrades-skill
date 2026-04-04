# GKE 1.30 End of Support Impact Analysis

## Current Status & EoS Timeline

**GKE 1.30 End of Support:** March 2025 (estimated)
**Your cluster inventory:**
- 3 clusters on Regular channel (1.30)
- 2 clusters on Extended channel (1.30) 
- 1 cluster on legacy "No channel" (1.30)

## What Happens at EoS (by cluster type)

### Regular Channel Clusters (3 clusters)
**What happens:** Systematic force-upgrade to 1.31 (next supported minor version)
- Control plane upgraded first, then all node pools
- No way to prevent this except temporary "no upgrades" exclusion (30-day max)
- Upgrade timing depends on maintenance windows if configured

**Timeline:** Force-upgrade begins at EoS date (March 2025) and completes within days/weeks depending on cluster size

### Extended Channel Clusters (2 clusters) 
**What happens:** **Nothing immediate** — Extended support continues until March 2026
- 1.30 gets **24 months total support** (standard 14 months + 10 months extended)
- Only patches are auto-applied during extended period
- No minor version force-upgrade until end of extended support (March 2026)
- Additional cost applies only during extended period (March 2025 - March 2026)

**Key insight:** Your Extended clusters have another full year before any forced upgrade

### Legacy "No Channel" Cluster (1 cluster)
**What happens:** Same systematic force-upgrade as Regular channel clusters
- Control plane and node pools upgraded to 1.31
- EoS enforcement is identical regardless of channel configuration
- Per-nodepool "no auto-upgrade" settings are **ignored** during EoS enforcement

**Important:** "No channel" provides no protection against EoS upgrades

## Your Preparation Options

### Option 1: Proactive Manual Upgrades (Recommended for Regular + No Channel)
**Timeline:** Upgrade during January-February 2025 (before EoS force-upgrade)

```bash
# Check available versions in your channels
gcloud container get-server-config --zone ZONE --format="yaml(channels)"

# Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.31.X-gke.Y

# Then upgrade node pools
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.X-gke.Y
```

**Advantages:** 
- You control timing and testing
- Can coordinate with maintenance windows
- Avoid potential issues during forced upgrade rush

### Option 2: Migrate No Channel → Extended (Legacy cluster only)
**For your 1 "No channel" cluster:**

```bash
# Migrate to Extended channel for maximum flexibility
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended

# Add "no minor or node upgrades" exclusion for maximum control
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Result:** Extends your 1.30 support until March 2026, matching your Extended clusters

### Option 3: Defer with Maintenance Exclusions (Short-term only)
**If you need to delay the forced upgrade:**

```bash
# Apply 30-day "no upgrades" exclusion before EoS
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "eos-deferral" \
  --add-maintenance-exclusion-start-time "2025-03-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-03-31T00:00:00Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

**Limitation:** Maximum 30 days deferral. Can chain up to 3 exclusions but accumulates security debt.

## Recommended Strategy by Cluster

### Regular Channel Clusters (3 clusters):
1. **Plan manual upgrades for January 2025**
2. Configure maintenance windows for predictable timing
3. Upgrade in sequence: dev → staging → prod with soak time between
4. Test 1.31 in staging first to identify deprecated API issues

### Extended Channel Clusters (2 clusters):
1. **No immediate action needed** — you have until March 2026
2. Plan 1.31 upgrade for late 2025 to stay current
3. Use the extra time to thoroughly test workload compatibility with 1.31

### No Channel Cluster (1 cluster):
1. **Priority: Migrate to Extended channel immediately**
2. This gives you the same 24-month timeline as your Extended clusters
3. Avoid staying on "No channel" — it lacks modern upgrade control features

## Migration Commands for No Channel Cluster

```bash
# Check current configuration
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(releaseChannel.channel)"

# Migrate to Extended channel
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended

# Add persistent minor/node exclusion for maximum control
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Verify configuration
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(releaseChannel.channel,maintenancePolicy)"
```

## Pre-Upgrade Checklist for 1.30 → 1.31

```markdown
- [ ] Check deprecated API usage: `kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated`
- [ ] Review GKE 1.31 release notes for breaking changes
- [ ] Verify third-party operators (cert-manager, Istio, etc.) support 1.31
- [ ] Configure PDBs to allow orderly drain during upgrade
- [ ] Plan maintenance windows for off-peak hours
- [ ] Back up stateful workload data before upgrade
- [ ] Test upgrade in dev/staging environment first
```

## Key Takeaways

1. **Extended clusters are protected** — no immediate action needed, plan for 2026
2. **Regular + No channel clusters will be force-upgraded** — proactive manual upgrade recommended
3. **Migrate the No channel cluster to Extended** — unified 24-month support across your fleet
4. **Plan upgrades 6-8 weeks before EoS** — avoid the forced upgrade rush and maintain control

Would you like me to create specific upgrade runbooks for your Regular channel clusters, or help you plan the migration strategy for your No channel cluster?
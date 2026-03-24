# GKE 1.30 End of Support Impact & Preparation Plan

Based on your cluster configuration, here's exactly what will happen to each cluster type when GKE 1.30 reaches End of Support, plus your preparation options.

## EoS Impact by Cluster Type

### Regular Channel Clusters (3 clusters)
**What happens at EoS:**
- **Control plane:** Auto-upgraded to 1.31 (next supported minor version)
- **Node pools:** Auto-upgraded to 1.31 following cluster-level policies
- **Timing:** Respects maintenance windows and exclusions
- **Rollback:** Not possible after auto-upgrade completes

### Extended Channel Clusters (2 clusters)  
**What happens at EoS:**
- **During standard support period (14 months):** Same behavior as Regular channel
- **During extended support period (months 15-24):** 
  - Minor version upgrades are NOT automated (except at end of extended support)
  - Only patches are auto-applied
  - You must manually trigger minor upgrades (1.30→1.31→1.32, etc.)
- **At end of extended support (24 months):** Force-upgraded to latest supported version
- **Cost:** Additional charges apply ONLY during the extended support period (months 15-24)

### Legacy "No Channel" Cluster (1 cluster)
**What happens at EoS:**
- **Control plane:** Force-upgraded to 1.31 systematically
- **Node pools:** Force-upgraded to 1.31 even if auto-upgrade is disabled
- **No granular control:** Only 30-day "no upgrades" exclusion available
- **Limited features:** Missing key upgrade control tools available on release channels

## Your Preparation Options

### Option 1: Proactive Manual Upgrades (Recommended)
**Timeline:** Before EoS enforcement begins

```bash
# Check current auto-upgrade targets
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION

# Manual control plane upgrade
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version 1.31.X-gke.XXXX

# Manual node pool upgrade (skip-level recommended: 1.30→1.31 in one jump)
gcloud container node-pools upgrade POOL_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.31.X-gke.XXXX
```

**Advantages:**
- Full control over timing and sequencing
- Can use two-step control plane upgrade for rollback safety (1.33+)
- Test target versions before auto-upgrade forces them
- Coordinate with application deployment schedules

### Option 2: Configure Auto-Upgrade Controls
**For Regular channel clusters:**

```bash
# Set maintenance window (off-peak hours)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --maintenance-window-start "2025-01-01T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Add "no minor or node upgrades" exclusion (allows CP patches only)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support \
  --add-maintenance-exclusion-name "controlled-upgrades"
```

**For Extended channel clusters:**
- No additional configuration needed — minor upgrades require manual trigger
- Continue receiving security patches automatically
- Plan manual upgrade cadence for minor versions

### Option 3: Migrate Legacy "No Channel" Cluster
**Strongly recommended** — migrate to Extended channel for maximum control:

```bash
# Migrate to Extended channel (closest to "No channel" behavior)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --release-channel extended

# Add granular exclusion (not available on "No channel")
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Benefits of migration:**
- Access to "no minor or node upgrades" exclusion
- Extended support option (up to 24 months)
- Better upgrade control tools
- Persistent exclusions that track EoS dates

### Option 4: Temporary EoS Deferral (Emergency Only)
**Use only if you cannot upgrade immediately:**

```bash
# Apply "no upgrades" exclusion (blocks everything for 30 days max)
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-scope no_upgrades \
  --add-maintenance-exclusion-start-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-end-time "$(date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-name "eos-deferral"
```

**⚠️ Warning:** This delays but doesn't prevent EoS enforcement. Use only to buy time while preparing proper upgrades.

## Pre-Upgrade Preparation Checklist

```markdown
Pre-1.30 EoS Upgrade Checklist
- [ ] Check deprecated API usage: GKE console → Insights → "Deprecations and Issues"
- [ ] Verify all admission webhooks support 1.31+ (cert-manager, service mesh, policy controllers)
- [ ] Review GKE 1.31 release notes for breaking changes
- [ ] Configure PDBs for stateful workloads (not overly restrictive)
- [ ] Back up StatefulSet data (application-level snapshots)
- [ ] Test 1.31 in dev/staging environment first
- [ ] Plan rollout sequence: dev → staging → production
- [ ] Set maintenance windows for production clusters
- [ ] Communicate upgrade timeline to stakeholders
```

## Recommended Strategy by Environment

**Development clusters:**
- Keep on Regular channel
- Allow auto-upgrades with maintenance windows
- Get new versions first for testing

**Staging clusters:** 
- Keep on Regular channel
- Use "no minor or node upgrades" exclusion
- Manually trigger after dev validation

**Production clusters:**
- Move to Extended channel if maximum control needed
- Use "no minor or node upgrades" exclusion
- Manually trigger after staging validation
- Longer support window reduces pressure

**Legacy "No channel" cluster:**
- **Migrate to Extended channel immediately** — you'll gain better control tools while maintaining similar upgrade behavior

## Timeline Recommendations

1. **Immediate (next 2 weeks):**
   - Migrate "No channel" cluster to Extended channel
   - Configure maintenance windows and exclusions for production clusters
   - Begin testing 1.31 in development

2. **Short term (next month):**
   - Upgrade development clusters to 1.31
   - Validate applications, operators, and workflows
   - Upgrade staging clusters after dev validation

3. **Before EoS enforcement:**
   - Upgrade production clusters manually with validated 1.31 version
   - Document lessons learned and update procedures

This approach gives you maximum control while avoiding forced upgrades and ensuring application compatibility.
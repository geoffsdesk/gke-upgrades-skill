# GKE Fleet Modernization Plan

You're facing a classic "inherited infrastructure" scenario. Here's a systematic approach to assess, prioritize, and modernize your GKE fleet using GKE's built-in tools.

## Phase 1: Assessment & Discovery

### Inventory your fleet

**Start with the GKE dashboard in Cloud Console:**
- Go to Kubernetes Engine → Clusters
- Enable the "Release Channel" and "Auto-upgrade" columns
- Export the list or take screenshots for documentation

**Get detailed cluster inventory:**
```bash
# List all clusters with key metadata
gcloud container clusters list \
  --format="table(name,location,currentMasterVersion,releaseChannel.channel:label=CHANNEL,status)"

# Detailed per-cluster assessment
for cluster in $(gcloud container clusters list --format="value(name,location)"); do
  name=$(echo $cluster | cut -d' ' -f1)
  zone=$(echo $cluster | cut -d' ' -f2)
  echo "=== $name ($zone) ==="
  gcloud container clusters describe $name --zone $zone \
    --format="table(currentMasterVersion,releaseChannel.channel,nodePools[].name,nodePools[].version,nodePools[].autoscaling.enabled)"
done
```

### Use GKE's deprecation insights

**Critical self-service tool:** The GKE deprecation insights dashboard shows API usage that will break in future versions.

1. Go to **Kubernetes Engine → Insights** in Cloud Console
2. Select **API deprecations** 
3. Review each cluster for deprecated API calls
4. Export findings — this determines your upgrade urgency

**Command-line alternative:**
```bash
# Check deprecated API usage per cluster
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
```

### Assess auto-upgrade status

```bash
# Check what auto-upgrades are planned
gcloud container clusters describe CLUSTER_NAME --zone ZONE \
  --format="yaml(releaseChannel,maintenancePolicy,autopilot.enabled)"
```

## Phase 2: Risk Assessment & Prioritization

### Cluster categorization matrix

Create a spreadsheet with these columns:

| Cluster | Environment | Channel | Current Version | Days Behind Latest | Deprecated APIs | Criticality | Action Priority |
|---------|-------------|---------|-----------------|-------------------|-----------------|-------------|----------------|
| prod-cluster-1 | Production | No channel | 1.26.5 | 180+ days | Yes (v1beta1) | Critical | **HIGH** |
| dev-cluster-2 | Development | Rapid | 1.31.1 | 14 days | No | Low | LOW |

**Days behind calculation:**
Check the [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) to see current channel versions vs. your cluster versions.

### Priority ranking

**HIGH priority (fix immediately):**
- Clusters approaching End of Support (EoS)
- Production workloads with deprecated API usage
- "No channel" clusters (they lack modern upgrade controls)
- Security-sensitive environments >90 days behind

**MEDIUM priority (fix within 2-4 weeks):**
- Staging environments with deprecated APIs
- Clusters >60 days behind current Stable channel
- Inconsistent channel strategy across environments

**LOW priority (fix during next maintenance cycle):**
- Dev/test clusters on appropriate channels
- Recent versions with no deprecated APIs
- Non-critical workloads

## Phase 3: Modernization Strategy

### Standard channel strategy (recommended)

**Multi-environment progression:**
- **Dev/Test:** Rapid channel (early access to features, faster feedback)
- **Staging:** Regular channel (production-like, good validation)  
- **Production:** Regular or Stable channel (proven stability)

**For compliance/conservative environments:**
- **All environments:** Stable channel
- **Long upgrade cycles:** Extended channel (24-month support, but minor upgrades aren't automated)

### Migration from legacy "No channel"

**Never recommend staying on "No channel"** — it lacks modern upgrade controls. Migrate to release channels first, then configure maintenance policies.

```bash
# Migrate to Regular channel (closest to legacy behavior)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular

# Alternative: Extended channel for maximum control
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended
```

### Maintenance policy standardization

**Apply consistent maintenance windows fleet-wide:**

```bash
# Production: Weekend maintenance (Saturday 2-6 AM UTC)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-end "2024-01-06T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Add "no minor or node upgrades" exclusion for maximum control
# (allows CP security patches, blocks disruptive changes)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "conservative-policy" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

**Dev/Staging: More aggressive windows (daily or multiple per week)**

## Phase 4: Execution Roadmap

### Week 1-2: Immediate fixes
- **Fix deprecated API usage** using the deprecation insights dashboard
- **Migrate all "No channel" clusters** to Regular channel  
- **Set maintenance windows** on production clusters
- **Document current state** and create the cluster inventory spreadsheet

### Week 3-4: Channel alignment
- **Standardize channel strategy** across environments
- **Apply maintenance exclusions** to production for controlled upgrades
- **Test upgrade process** on lowest-risk clusters first

### Week 5-8: Systematic upgrades
- **Dev/staging first:** Upgrade to recent versions within channel
- **Production upgrades:** Plan sequential minor version upgrades (don't skip)
- **Validate each environment** before proceeding to next tier

### Ongoing: Fleet management
- **Weekly health checks:** Review auto-upgrade status across fleet
- **Quarterly channel review:** Adjust strategy based on business needs
- **Proactive EoS planning:** Track upcoming End of Support dates

## Self-Service Tools & Monitoring

### GKE Console Dashboards

1. **Clusters Overview:** Shows release channels, versions, auto-upgrade status
2. **Insights → API Deprecations:** Critical for upgrade planning
3. **Insights → Security:** Shows security posture and recommendations
4. **Operations → Logs:** Upgrade notifications and errors

### Automation opportunities

```bash
# Create a fleet health check script
#!/bin/bash
echo "=== GKE Fleet Health Report ==="
echo "Generated: $(date)"
echo

for cluster in $(gcloud container clusters list --format="value(name,location)"); do
  name=$(echo $cluster | cut -d' ' -f1)
  zone=$(echo $cluster | cut -d' ' -f2)
  
  version=$(gcloud container clusters describe $name --zone $zone --format="value(currentMasterVersion)")
  channel=$(gcloud container clusters describe $name --zone $zone --format="value(releaseChannel.channel)")
  
  echo "$name ($zone): $version on ${channel:-'No channel'}"
done
```

### Monitoring & alerting

Set up Cloud Monitoring alerts for:
- Clusters approaching EoS (90 days warning)
- Failed upgrade operations
- Deprecated API usage spikes
- Node pool health issues

## Key Success Metrics

Track these metrics monthly:
- **% clusters on release channels** (target: 100%)
- **Average days behind current Stable** (target: <60 days)
- **% clusters with deprecated API usage** (target: 0%)
- **% clusters with maintenance windows configured** (target: 100%)
- **Failed upgrade rate** (target: <5%)

## Critical Don'ts

❌ **Don't disable auto-upgrades** — this defeats GKE's value proposition  
❌ **Don't skip minor versions on control plane** — do sequential upgrades (1.29→1.30→1.31)  
❌ **Don't ignore deprecation insights** — these become hard failures in future versions  
❌ **Don't upgrade production first** — always validate in dev/staging  
❌ **Don't forget PDBs** — they're the #1 cause of stuck upgrades  

## Need Help?

If you find clusters in truly bad states (very old versions, complex deprecated API usage, unusual configurations), consider engaging Google Cloud Professional Services for a fleet modernization engagement. They can provide customized automation and migration assistance.

The **GKE deprecation insights dashboard** is your most powerful self-service tool — start there to understand what will break and when.
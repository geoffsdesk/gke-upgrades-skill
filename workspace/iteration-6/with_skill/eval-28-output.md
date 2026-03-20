# GKE Upgrade Timing and Visibility Guide

Your VP needs predictable upgrade timelines for stakeholder communication. Here's how to gain visibility and control over GKE upgrade timing.

## Understanding GKE upgrade timing

**Key insight:** GKE auto-upgrades don't happen at random. They follow a structured rollout with multiple factors affecting timing:

### Release cadence
- **GKE releases:** ~1 per week (patches + minors combined)
- **New Kubernetes minors:** Appear in Rapid channel within ~2 weeks of upstream release
- **Progressive rollout:** Each release rolls out across all regions over 4-5 business days

### What determines WHEN your clusters upgrade

1. **Release channel** determines which versions you get and roughly when
2. **Maintenance windows** control the allowed time slots
3. **Maintenance exclusions** can block upgrades entirely
4. **Disruption intervals** prevent back-to-back upgrades
5. **Progressive rollout** means later regions get upgrades later in the week

## Immediate actions for predictability

### 1. Check current auto-upgrade status

```bash
# See what version your cluster will upgrade to next
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="yaml(releaseChannel,autopilot.workloadPolicyConfig)"

# Check maintenance windows and exclusions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="yaml(maintenancePolicy)"
```

This shows your **auto-upgrade target version** — the version GKE will automatically upgrade to during the next maintenance window.

### 2. Set maintenance windows immediately

Configure recurring windows aligned with your change management process:

```bash
# Example: Saturday 2-6 AM UTC weekly
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T02:00:00Z" \
  --maintenance-window-end "2024-01-06T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Critical:** Auto-upgrades only happen during maintenance windows. Manual upgrades bypass them.

### 3. Enable upgrade notifications

GKE provides 72-hour advance notice via Cloud Logging:

```bash
# Create notification policy (adjust notification channels as needed)
gcloud logging sinks create gke-upgrade-alerts \
  bigquery.googleapis.com/projects/PROJECT_ID/datasets/gke_logs \
  --log-filter='resource.type="gke_cluster" AND protoPayload.methodName="google.container.v1.ClusterManager.UpdateCluster" AND protoPayload.authenticationInfo.principalEmail="service-PROJECT_NUMBER@container-engine-robot.iam.gserviceaccount.com"'
```

Set up Cloud Monitoring alerts on these logs to notify your team.

## Controlling upgrade timing

### Maintenance exclusion strategy (recommended approach)

For maximum control, use **"No minor or node upgrades"** exclusions:

```bash
# Block disruptive upgrades while allowing security patches
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "q1-planning-freeze" \
  --add-maintenance-exclusion-start-time "2024-01-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-03-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

**Why this approach:** Allows control plane security patches while blocking the disruptive changes (minor versions, node restarts). You can chain these exclusions up to each version's End of Support date.

### Exclusion types comparison

| Exclusion Type | What it blocks | Max duration | Best for |
|---------------|---------------|-------------|----------|
| **"No upgrades"** | All upgrades (patches, minor, nodes) | 30 days | Code freezes, critical business periods |
| **"No minor or node upgrades"** ⭐ | Minor + node upgrades only | Up to version EoS | Maximum control while staying secure |
| **"No minor upgrades"** | Minor versions only | Up to version EoS | Conservative teams OK with node churn |

### Release channel strategy for multi-environment

Stagger channels across environments for natural upgrade sequencing:

- **Dev clusters:** Rapid channel (early feedback)
- **Staging clusters:** Regular channel (production validation)  
- **Production clusters:** Stable or Regular channel (proven stability)

This gives you 2-4 weeks between dev → staging → prod upgrades naturally.

## Upgrade visibility tools

### 1. GKE release schedule
**URL:** https://cloud.google.com/kubernetes-engine/docs/release-schedule

Shows "no earlier than" dates for each version in each channel. Upgrades won't happen before these dates but may happen later due to progressive rollout.

### 2. Auto-upgrade target tracking

```bash
# Check what version the cluster will auto-upgrade to
gcloud container clusters describe CLUSTER_NAME --zone ZONE \
  --format="table(name,currentMasterVersion,releaseChannel.channel)" && \
echo "Auto-upgrade target will be visible in cluster maintenance settings"
```

### 3. Progressive rollout tracking

Monitor when releases reach your region:

```bash
# Check available versions in your zone
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels)" | grep -A 10 "REGULAR\|STABLE"
```

### 4. Operations monitoring

Track upgrade operations in flight:

```bash
# See current/recent upgrade operations  
gcloud container operations list \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --filter="operationType:UPGRADE"
```

## Stakeholder communication template

Here's a template for your VP:

---

**GKE Upgrade Timeline - [Cluster Name]**

**Current Status:**
- Cluster version: `1.28.5-gke.1217000`
- Release channel: `Regular`
- Next auto-upgrade target: `1.29.1-gke.1234000` (estimated)

**Scheduled Windows:**
- Maintenance window: `Saturdays 2-6 AM UTC`
- Next possible upgrade: `January 20, 2024` (if target version available)

**Controls in Place:**
- 72-hour advance notifications enabled
- Maintenance exclusion active: `Jan 15 - Mar 31` (blocks disruptive upgrades during Q1 planning)
- Manual approval required for all major version changes

**Stakeholder Impact:**
- Control plane upgrades: No user-facing downtime
- Node pool upgrades: Workloads restart gracefully (< 30 seconds per pod)
- Emergency security patches: May occur outside normal windows (rare)

---

## Advanced: Rollout sequencing for large fleets

**Note:** Only recommend this for sophisticated platform teams managing 10+ clusters. For most customers, the simpler approaches above (maintenance windows + channel staggering) provide sufficient control.

If you have many clusters and need automated sequencing:

```bash
# Configure rollout sequencing with soak time
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel-config rollout-config.yaml
```

This allows defining upgrade order across clusters with configurable delays between groups.

## Emergency override capability

Even with all these controls, GKE can force upgrades in rare cases:

1. **Critical security vulnerabilities** (CVEs affecting Kubernetes API server)
2. **End of Support enforcement** (when versions reach EoL)

For these cases, the **"no upgrades"** exclusion (30-day max) can provide temporary protection while you plan emergency responses.

## Action items for your VP

**This week:**
- [ ] Configure maintenance windows on all production clusters
- [ ] Set up 72-hour upgrade notifications 
- [ ] Document current auto-upgrade targets for each cluster

**This month:**
- [ ] Apply maintenance exclusions for any known freeze periods
- [ ] Evaluate release channel strategy across environments
- [ ] Create upgrade timeline dashboard for leadership visibility

**Ongoing:**
- [ ] Monthly review of auto-upgrade targets
- [ ] Quarterly assessment of maintenance exclusion strategy
- [ ] Track GKE release schedule for version planning

This approach gives you maximum predictability while maintaining security through automated patching.
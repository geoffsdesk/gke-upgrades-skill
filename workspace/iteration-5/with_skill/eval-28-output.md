# GKE Upgrade Timing and Predictability Guide

Your VP needs to understand that GKE upgrade timing has both predictable elements (that you can control) and variable factors (that Google controls). Here's how to maximize predictability and visibility.

## What you can control

### 1. Maintenance windows
Set recurring maintenance windows to constrain when auto-upgrades can happen:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start 2024-01-20T02:00:00Z \
  --maintenance-window-end 2024-01-20T06:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Impact:** Auto-upgrades will ONLY happen during these windows. Manual upgrades bypass windows entirely.

### 2. Maintenance exclusions (the strongest control lever)

**"No minor or node upgrades" exclusion** — this is your best tool for predictable timing:
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "Q4-freeze" \
  --add-maintenance-exclusion-start-time 2024-10-01T00:00:00Z \
  --add-maintenance-exclusion-end-time 2024-12-31T23:59:59Z \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

This blocks disruptive upgrades (minor versions + node pool changes) while still allowing control plane security patches. You can chain these exclusions right up to a version's End of Support date.

### 3. Release channel strategy
Match channels to your risk tolerance and predictability needs:

| Environment | Recommended Channel | Upgrade Timing |
|-------------|-------------------|----------------|
| **Dev/Test** | Rapid | New versions within ~2 weeks of upstream |
| **Staging** | Regular | After Rapid validation (~4-6 weeks) |
| **Production** | Stable or Extended | Most conservative timing |

**Extended channel** (versions 1.27+) gives you up to 24 months of support vs. 14 months for other channels — maximum flexibility for planning.

### 4. Manual upgrade control
Take full control by disabling auto-upgrades with permanent exclusions:
```bash
# Block auto-upgrades indefinitely (up to EoS)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "manual-only" \
  --add-maintenance-exclusion-start-time $(date -Iseconds) \
  --add-maintenance-exclusion-end-time 2025-12-31T23:59:59Z \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

Then upgrade manually during planned maintenance windows.

## What Google controls (variable factors)

### Progressive rollout timing
New GKE versions roll out across all regions over **4-5 business days**. The [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) shows "best case" dates — upgrades won't happen before these dates but may happen later.

**Your region might be early or late in the rollout.** There's no way to predict which.

### Internal factors that add delays
- **Holiday/event freezes:** Google pauses rollouts during Black Friday/Cyber Monday, major holidays
- **Technical pauses:** If issues are discovered during rollout, Google may pause until fixed
- **Disruption intervals:** GKE enforces gaps between upgrades on the same cluster (configurable, max 90 days)

## Visibility tools GKE provides

### 1. Check your cluster's auto-upgrade target
```bash
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(nodePools[].management.autoUpgrade,releaseChannel.channel)"
```

### 2. GKE release schedule (public)
- **URL:** https://cloud.google.com/kubernetes-engine/docs/release-schedule
- **What it shows:** When versions become available in each channel
- **Limitation:** Shows availability, not when YOUR cluster will upgrade

### 3. Scheduled upgrade notifications (opt-in)
Enable 72-hour advance notifications via Cloud Logging:
```bash
# This sends logs 72h before auto-upgrade starts
gcloud logging sinks create gke-upgrade-notifications \
  bigquery.googleapis.com/projects/PROJECT_ID/datasets/DATASET_ID \
  --log-filter='resource.type="gke_cluster" AND severity>=WARNING'
```

### 4. Version availability API
Check what's available right now in your region:
```bash
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels)"
```

### 5. Deprecation insights dashboard
**Location:** GKE console → cluster → Security → Insights
**Shows:** Deprecated API usage that could block upgrades

## Stakeholder communication strategy

### For predictable timelines, recommend this approach:

1. **Use "no minor or node upgrades" exclusions** as your primary control mechanism
2. **Set maintenance windows** to define acceptable upgrade hours  
3. **Monitor the release schedule** for new version availability
4. **Plan manual upgrades** during scheduled maintenance slots

### Monthly planning cycle:
```
Week 1: Review GKE release schedule for new versions
Week 2: Test new versions in dev/staging clusters  
Week 3: Plan production upgrade during next maintenance window
Week 4: Execute upgrade, validate, communicate completion
```

### Sample timeline you can give your VP:

> **Control plane upgrades:** During our Saturday 2-6 AM maintenance window, typically within 2-4 weeks of a new version reaching the Stable channel. We'll have 72-hour advance notice.
> 
> **Node pool upgrades:** Controlled manually during the same maintenance windows, after control plane validation. We can defer these indefinitely using maintenance exclusions.
> 
> **Emergency upgrades:** Only if our current version reaches End of Support and we haven't upgraded proactively.

## Multi-cluster orchestration

For fleets of clusters, use **rollout sequencing** to control the order and timing:
```bash
# Configure dev → staging → prod progression with soak time
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --enable-rollout-sequencing \
  --rollout-sequencing-cluster-order "dev-cluster,staging-cluster,prod-cluster" \
  --rollout-sequencing-soak-duration "72h"
```

## Bottom line for your VP

**Most predictable approach:**
- Use Extended release channel for maximum flexibility (24-month support windows)
- Apply "no minor or node upgrades" maintenance exclusions to prevent surprise auto-upgrades
- Plan manual upgrades quarterly during scheduled maintenance windows
- Enable 72-hour upgrade notifications for any auto-upgrades that do occur

**This gives you control over WHEN upgrades happen, while the WHAT (which version) follows Google's release schedule with 4-6 week predictability.**

The tradeoff is operational overhead — your team manages upgrade timing rather than letting Google handle it automatically. But for stakeholder communication and business planning, this approach maximizes predictability.
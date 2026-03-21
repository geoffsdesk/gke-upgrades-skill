# GKE Fleet Health Assessment & Remediation Plan

You've inherited a classic "GKE sprawl" situation. Here's a systematic approach to assess, prioritize, and remediate your fleet using GKE's self-service tools.

## Phase 1: Assessment & Discovery

### Fleet inventory with GKE Enterprise (recommended)

If you have GKE Enterprise, use the **Fleet Overview dashboard** for instant visibility:

```bash
# Enable GKE Enterprise fleet management
gcloud container fleet create
gcloud container fleet memberships register CLUSTER_NAME \
  --gke-cluster=ZONE/CLUSTER_NAME
```

The Fleet Overview provides:
- Version compliance across all clusters
- Security posture and policy violations  
- Upgrade readiness assessment
- Resource utilization trends
- Multi-cluster workload topology

This is the fastest way to get fleet-wide visibility without writing scripts.

### Self-service assessment tools

**1. GKE Deprecation Insights Dashboard**
- Console → GKE → Insights tab
- Shows deprecated API usage across your fleet
- Critical for identifying upgrade blockers

**2. Cluster upgrade readiness API**
```bash
# Check each cluster's auto-upgrade status and EoS timeline
for cluster in $(gcloud container clusters list --format="value(name,zone)"); do
  echo "=== $cluster ==="
  gcloud container clusters get-upgrade-info $cluster --format="table(
    autoUpgradeStatus,
    endOfStandardSupportTimestamp,
    minorTargetVersion,
    patchTargetVersion
  )"
done
```

**3. Fleet-wide version inventory**
```bash
# Generate fleet version matrix
gcloud container clusters list --format="table(
  name,
  zone,
  currentMasterVersion:label=CP_VERSION,
  releaseChannel.channel:label=CHANNEL,
  status:label=STATUS
)" > fleet-inventory.csv
```

**4. Node pool assessment**
```bash
# Detailed per-cluster breakdown
for cluster_zone in $(gcloud container clusters list --format="value(name,zone)"); do
  cluster=$(echo $cluster_zone | cut -d' ' -f1)
  zone=$(echo $cluster_zone | cut -d' ' -f2)
  
  echo "=== $cluster ($zone) ==="
  gcloud container node-pools list --cluster=$cluster --zone=$zone \
    --format="table(name,version,autoscaling.enabled,management.autoUpgrade)"
done
```

### Risk assessment framework

Categorize clusters by risk level:

**CRITICAL (fix immediately):**
- Versions approaching End of Support (<60 days)
- "No channel" clusters on unsupported versions
- Clusters with deprecated API usage
- Production clusters with auto-upgrade disabled

**HIGH (next 30 days):**
- Inconsistent versions within the same environment (dev/staging/prod)
- GPU clusters without proper maintenance exclusions
- Multi-cluster applications with version drift

**MEDIUM (next quarter):**
- "No channel" clusters on supported versions
- Missing maintenance windows
- Suboptimal node pool configuration

## Phase 2: Standardization Strategy

### Target architecture (recommended)

**Environment-based channel strategy:**
- **Dev environments:** Regular or Rapid channel
- **Staging:** Regular channel  
- **Production:** Regular or Stable channel

**Key principle:** Keep all environments in a rollout sequence on the same channel to enable progressive deployment. If you need environment-based timing differences, use maintenance windows and exclusions rather than different channels.

**Maintenance exclusion strategy:**
- Production clusters: `"no minor or node upgrades"` exclusion with maintenance windows
- This allows security patches but gives you control over disruptive changes
- Remove exclusions during planned maintenance windows to allow upgrades

### Migration priority matrix

```
Priority 1: EoS clusters → migrate to Extended channel (immediate support extension)
Priority 2: "No channel" prod → migrate to Regular/Stable + exclusions
Priority 3: Version drift → standardize within environments  
Priority 4: Optimize settings → maintenance windows, surge configs
```

## Phase 3: Remediation Runbook

### Emergency EoS mitigation

For clusters approaching End of Support:

```bash
# Option A: Quick EoS extension (versions 1.27+)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel extended

# Option B: Temporary freeze (up to 30 days)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "emergency-freeze" \
  --add-maintenance-exclusion-start-time "$(date -Iseconds)" \
  --add-maintenance-exclusion-end-time "$(date -d '+30 days' -Iseconds)" \
  --add-maintenance-exclusion-scope no_upgrades
```

### "No channel" migration plan

**Step 1: Assessment**
```bash
# List all "No channel" clusters
gcloud container clusters list \
  --filter="releaseChannel.channel:* = NULL" \
  --format="table(name,zone,currentMasterVersion)"
```

**Step 2: Migration with safety**
```bash
# Add temporary freeze first (prevents auto-upgrade during migration)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "migration-freeze" \
  --add-maintenance-exclusion-start-time "$(date -Iseconds)" \
  --add-maintenance-exclusion-end-time "$(date -d '+7 days' -Iseconds)" \
  --add-maintenance-exclusion-scope no_upgrades

# Migrate to Regular channel (closest to legacy behavior)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular

# Configure maintenance window
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-12-21T02:00:00Z" \
  --maintenance-window-end "2024-12-21T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Add persistent exclusion for production
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "prod-control" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

### Fleet standardization script

```bash
#!/bin/bash
# fleet-standardize.sh

CLUSTERS_FILE="fleet-inventory.csv"  # From assessment phase

while IFS=, read -r cluster zone current_version channel status; do
  if [[ "$channel" == "NULL" ]]; then
    echo "Migrating $cluster from No channel to Regular..."
    
    # Add safety freeze
    gcloud container clusters update "$cluster" \
      --zone "$zone" \
      --add-maintenance-exclusion-name "migration-$(date +%s)" \
      --add-maintenance-exclusion-start-time "$(date -Iseconds)" \
      --add-maintenance-exclusion-end-time "$(date -d '+7 days' -Iseconds)" \
      --add-maintenance-exclusion-scope no_upgrades
    
    # Migrate to channel
    gcloud container clusters update "$cluster" \
      --zone "$zone" \
      --release-channel regular
      
    # Add maintenance window (customize per environment)
    if [[ "$cluster" == *"prod"* ]]; then
      # Production: Saturday 2-6am
      gcloud container clusters update "$cluster" \
        --zone "$zone" \
        --maintenance-window-start "2024-12-21T02:00:00Z" \
        --maintenance-window-end "2024-12-21T06:00:00Z" \
        --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA" \
        --add-maintenance-exclusion-name "prod-control" \
        --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
        --add-maintenance-exclusion-until-end-of-support
    fi
  fi
done < "$CLUSTERS_FILE"
```

## Phase 4: Ongoing Fleet Management

### Monitoring and alerting

**Set up GKE fleet monitoring:**
```bash
# Enable GKE monitoring insights
gcloud services enable container.googleapis.com
gcloud services enable monitoring.googleapis.com

# Create alert policy for EoS approaching
# (Use Cloud Monitoring console or Terraform)
```

**Weekly fleet health check:**
```bash
#!/bin/bash
# weekly-fleet-check.sh

echo "=== GKE Fleet Health Report $(date) ==="

echo "Clusters approaching EoS (next 60 days):"
gcloud container clusters list --format="table(
  name,
  zone, 
  currentMasterVersion,
  releaseChannel.channel
)" --filter="currentMasterVersion < 1.XX"  # Update XX based on current EoS

echo "Clusters with deprecated APIs:"
# Check deprecation insights dashboard or API

echo "Failed auto-upgrades (last 7 days):"
gcloud logging read 'resource.type="gke_cluster" AND 
  jsonPayload.message:"upgrade" AND 
  severity="ERROR"' \
  --since=7d --format="table(timestamp,resource.labels.cluster_name)"
```

### Progressive upgrade strategy

**Environment rollout sequence:**
1. **Dev clusters** (Regular channel, no exclusions) → auto-upgrade first
2. **Staging clusters** (Regular channel, 1-week soak) → manual verification
3. **Production clusters** (Regular/Stable channel, controlled via exclusions) → planned maintenance windows

**Rollout sequencing for large fleets:**
```bash
# Configure rollout sequencing (all clusters must be on same channel)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular \
  --rollout-sequencing-group production \
  --rollout-sequencing-stage 2 \
  --rollout-sequencing-soak-duration 48h
```

### Self-service governance

**Establish fleet policies using Policy Controller:**
```yaml
# Example: Require all clusters on release channels
apiVersion: templates.gatekeeper.sh/v1beta1
kind: ConstraintTemplate
metadata:
  name: gkerequirereleaschannel
spec:
  crd:
    spec:
      names:
        kind: GkeRequireReleaseChannel
  targets:
    - target: admission.k8s.gatekeeper.sh
      rego: |
        package gkerequirereleaschannel
        violation[{"msg": msg}] {
          input.review.object.spec.releaseChannel.channel == ""
          msg := "GKE clusters must use a release channel"
        }
```

**Monthly fleet review checklist:**
- [ ] All clusters on supported versions
- [ ] No "No channel" clusters remaining  
- [ ] Maintenance windows configured for all production clusters
- [ ] Deprecated API usage trending down
- [ ] Auto-upgrade failures investigated and resolved
- [ ] Version consistency within environments maintained

## Key Success Metrics

Track these metrics to measure fleet health improvement:

- **Version compliance:** % clusters on supported versions
- **Channel adoption:** % clusters migrated off "No channel"  
- **Upgrade success rate:** % auto-upgrades completing without intervention
- **Mean time to patch:** Days between patch availability and deployment
- **Security posture:** Deprecated API usage elimination

The goal is a self-managing fleet where upgrades happen automatically within your defined maintenance windows, with exceptions only for planned testing or emergency freezes. GKE's auto-upgrade model should handle 90%+ of your version management once properly configured.
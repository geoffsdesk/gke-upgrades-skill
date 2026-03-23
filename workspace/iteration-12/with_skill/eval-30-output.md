# GKE Fleet Modernization Plan

You're facing a classic "inherited technical debt" scenario. Here's a systematic approach to get your fleet into a healthy, well-managed state using GKE's self-service tools.

## Phase 1: Assessment & Discovery

### Fleet inventory with GKE's built-in tools

```bash
# Get complete fleet overview
gcloud container clusters list --format="table(
  name,
  location,
  currentMasterVersion,
  releaseChannel.channel:label=CHANNEL,
  status,
  nodeConfig.machineType,
  currentNodeCount
)"

# Check auto-upgrade status for each cluster
for cluster in $(gcloud container clusters list --format="value(name,location)"); do
  IFS=$'\t' read -r name location <<< "$cluster"
  echo "=== $name ($location) ==="
  gcloud container clusters get-upgrade-info "$name" --region="$location" 2>/dev/null || \
  gcloud container clusters get-upgrade-info "$name" --zone="$location"
done
```

### Use GKE's deprecation insights dashboard

Navigate to: **GKE Console → Cluster → Observability tab → Deprecation insights**

This shows:
- Deprecated API usage across your fleet
- Which workloads will break on upgrade
- Specific API versions to remediate
- Timeline pressure (how close versions are to EoS)

### Version risk assessment

```bash
# Check which clusters are approaching EoS
gcloud container clusters list --format="table(
  name,
  location,
  currentMasterVersion,
  releaseChannel.channel,
  autopilot.enabled
)" | while read -r name location version channel autopilot; do
  if [[ "$name" != "NAME" ]]; then
    echo "Cluster: $name | Version: $version | Channel: $channel"
    # Check if version is approaching EoS using the upgrade info API
  fi
done
```

### Workload assessment

```bash
# Find bare pods (highest risk)
kubectl get pods --all-namespaces -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# Check PDB coverage
kubectl get pdb --all-namespaces -o wide

# Find resource-unspecified pods (Autopilot blockers)
kubectl get pods --all-namespaces -o json | \
  jq -r '.items[] | select(.spec.containers[].resources.requests | not) | "\(.metadata.namespace)/\(.metadata.name)"'
```

## Phase 2: Prioritization Matrix

Rank clusters by upgrade urgency:

| Priority | Criteria | Action Timeline |
|----------|----------|----------------|
| **P0 (Emergency)** | EoS in <30 days, "No channel" with old versions | Immediate |
| **P1 (High)** | EoS in 30-90 days, deprecated API usage | 2-4 weeks |
| **P2 (Medium)** | Stable but suboptimal config (wrong channel, no maintenance windows) | 1-3 months |
| **P3 (Low)** | Healthy but could be optimized | Ongoing |

## Phase 3: Standardization Strategy

### Target architecture (recommended for most organizations)

```bash
# Standard target configuration per environment:
# - Dev: Regular channel (fast feedback on issues)
# - Staging: Regular channel (same as prod for testing)
# - Prod: Stable channel (maximum reliability)

# All clusters should have:
# - Maintenance windows configured
# - "No minor or node upgrades" exclusion (for maximum control)
# - Proper PDBs on critical workloads
# - Resource requests/limits on all containers
```

### Migration from "No channel" to release channels

For each "No channel" cluster:

```bash
# Check current state
gcloud container clusters describe CLUSTER_NAME --zone ZONE \
  --format="value(releaseChannel.channel,currentMasterVersion)"

# Migrate to Regular channel (closest to legacy behavior)
gcloud container clusters update CLUSTER_NAME --zone ZONE \
  --release-channel regular

# Or Extended channel if you need maximum EoS flexibility
gcloud container clusters update CLUSTER_NAME --zone ZONE \
  --release-channel extended

# Add maintenance exclusion for control
gcloud container clusters update CLUSTER_NAME --zone ZONE \
  --add-maintenance-exclusion-name "fleet-modernization" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-until-end-of-support
```

## Phase 4: Systematic Upgrade Plan

### Multi-cluster upgrade sequencing

```bash
# Group 1: Dev/test clusters (lowest risk)
# - Upgrade first to validate process
# - Use as canaries for production

# Group 2: Staging clusters
# - Mirror production configuration
# - 1-2 week soak time after dev

# Group 3: Production clusters
# - Stagger by criticality (least critical first)
# - 1-week gaps between clusters
```

### Upgrade runbook template

For each cluster group:

```bash
# 1. Pre-flight checks
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION
kubectl get pods -A | grep -v Running | grep -v Completed
kubectl get pdb -A -o wide

# 2. Set maintenance window (off-peak)
gcloud container clusters update CLUSTER_NAME --zone ZONE \
  --maintenance-window-start "2024-01-13T02:00:00Z" \
  --maintenance-window-end "2024-01-13T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# 3. Configure node pool upgrade strategy
gcloud container node-pools update DEFAULT_POOL --cluster CLUSTER_NAME --zone ZONE \
  --max-surge-upgrade 2 --max-unavailable-upgrade 0

# 4. Initiate upgrade (or wait for auto-upgrade in maintenance window)
gcloud container clusters upgrade CLUSTER_NAME --zone ZONE --master
# Then node pools...

# 5. Validate
kubectl get nodes
kubectl get pods -A | grep -v Running
```

## Phase 5: Automation & Governance

### Fleet-wide maintenance policies

```bash
# Apply consistent maintenance windows across fleet
for cluster in $(gcloud container clusters list --format="value(name,location)"); do
  IFS=$'\t' read -r name location <<< "$cluster"
  gcloud container clusters update "$name" --zone "$location" \
    --maintenance-window-start "2024-01-13T02:00:00Z" \
    --maintenance-window-end "2024-01-13T06:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
done
```

### Monitoring and alerting

Set up alerts for:
- Clusters approaching EoS (use Cloud Monitoring + upgrade info API)
- Deprecated API usage (GKE deprecation insights)
- Failed upgrades (Cloud Logging)
- Version drift across environments

### Policy enforcement

```bash
# Use Organization Policy to enforce:
# - Require release channel enrollment
# - Restrict "No channel" option
# - Mandate maintenance windows
# - Require Autopilot for new clusters (optional)
```

## GKE Self-Service Tools Summary

**Assessment:**
- `gcloud container clusters get-upgrade-info` - auto-upgrade status, EoS dates
- GKE deprecation insights dashboard - API compatibility
- `gcloud container get-server-config` - available versions per channel

**Planning:**
- GKE release schedule - upgrade timing predictability
- Upgrade assist common scenarios - best practice guidance
- Cloud Monitoring GKE dashboards - baseline metrics

**Execution:**
- Maintenance windows + exclusions - upgrade timing control
- Progressive rollout - automatic region-by-region deployment
- Rollout sequencing (advanced) - multi-cluster orchestration

**Monitoring:**
- Cloud Logging upgrade notifications - 72h advance notice (preview)
- Upgrade operation status - real-time progress tracking
- Deprecation insights - ongoing compatibility monitoring

## Quick Wins for Immediate Impact

1. **Enable deprecation insights** on all clusters - identifies breaking changes before they happen
2. **Migrate all "No channel" clusters** to Regular/Stable - unlocks powerful maintenance exclusion controls
3. **Set maintenance windows** fleet-wide - makes upgrades predictable
4. **Add "no minor or node upgrades" exclusions** - gives you control while allowing security patches
5. **Fix bare pods** - wrap in Deployments to enable automatic rescheduling

This systematic approach transforms your chaotic fleet into a well-managed, predictably-upgraded environment using GKE's built-in automation rather than fighting against it.
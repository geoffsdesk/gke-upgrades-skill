# GKE Maintenance Configuration for SOX Compliance

I'll help you configure maintenance windows and exclusions that align with SOX compliance requirements. This setup provides predictable upgrade timing while maintaining security through automated patching.

## Current Environment Assessment

**Assumptions** (please confirm/adjust):
- 3 GKE Standard clusters in a dev→staging→prod progression
- Weekend maintenance windows preferred (Saturday early morning)
- Quarterly code freezes: Q1 (Mar), Q2 (Jun), Q3 (Sep), Q4 (Dec)
- November audit period requires stability
- Need to maintain security patching during restrictions

## Recommended Configuration Strategy

### Release Channel Selection
```bash
# Recommended channel assignment for regulated environments:
# Dev cluster → Regular channel (for validation)
# Staging cluster → Regular channel (prod-like testing)  
# Prod cluster → Stable channel (maximum stability)

# Migrate from legacy "No channel" if needed:
gcloud container clusters update DEV-CLUSTER-NAME \
  --zone ZONE \
  --release-channel regular

gcloud container clusters update STAGING-CLUSTER-NAME \
  --zone ZONE \
  --release-channel regular

gcloud container clusters update PROD-CLUSTER-NAME \
  --zone ZONE \
  --release-channel stable
```

### Maintenance Windows (All Clusters)
```bash
# Set weekend maintenance window: Saturdays 2:00-6:00 AM EST
# Convert to UTC: Saturdays 07:00-11:00 AM UTC

# Dev cluster
gcloud container clusters update DEV-CLUSTER-NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T07:00:00Z" \
  --maintenance-window-end "2024-01-06T11:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Staging cluster  
gcloud container clusters update STAGING-CLUSTER-NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T07:00:00Z" \
  --maintenance-window-end "2024-01-06T11:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Production cluster
gcloud container clusters update PROD-CLUSTER-NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-06T07:00:00Z" \
  --maintenance-window-end "2024-01-06T11:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## Maintenance Exclusion Strategy

For SOX compliance, I recommend **"No minor or node upgrades"** exclusions. This approach:
- ✅ Allows critical security patches on control plane (maintains compliance)
- ✅ Blocks disruptive minor version and node pool upgrades
- ✅ Can be chained until version End of Support
- ✅ Provides maximum control for regulated environments

### Quarterly Code Freeze Exclusions

```bash
# Q1 Code Freeze (March 1-31, 2024)
gcloud container clusters update PROD-CLUSTER-NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "Q1-2024-code-freeze" \
  --add-maintenance-exclusion-start-time "2024-03-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-03-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Q2 Code Freeze (June 1-30, 2024)
gcloud container clusters update PROD-CLUSTER-NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "Q2-2024-code-freeze" \
  --add-maintenance-exclusion-start-time "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Q3 Code Freeze (September 1-30, 2024)
gcloud container clusters update PROD-CLUSTER-NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "Q3-2024-code-freeze" \
  --add-maintenance-exclusion-start-time "2024-09-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-09-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Q4 Code Freeze (December 1-31, 2024)
gcloud container clusters update PROD-CLUSTER-NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "Q4-2024-code-freeze" \
  --add-maintenance-exclusion-start-time "2024-12-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-12-31T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

### Annual Audit Exclusion (November)

```bash
# November 2024 - Complete audit stability
# Using "no_upgrades" for absolute stability during audit
gcloud container clusters update PROD-CLUSTER-NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "SOX-audit-2024" \
  --add-maintenance-exclusion-start-time "2024-11-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-11-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

### Apply Same Exclusions to Staging (Optional)
```bash
# Apply similar exclusions to staging if needed for audit consistency
# Use same commands as above, replacing PROD-CLUSTER-NAME with STAGING-CLUSTER-NAME
```

## Rollout Sequencing Configuration

Configure sequential upgrades with soak time between environments:

```bash
# This requires GKE Enterprise - contact Google Cloud Support to enable
# rollout sequencing for your fleet. Configuration example:

# Dev cluster: Stage 1 (immediate)  
# Staging cluster: Stage 2 (3 days after dev)
# Prod cluster: Stage 3 (7 days after staging)
```

## SOX Compliance Considerations

### Audit Trail
```bash
# Enable audit logging for all cluster changes
gcloud container clusters update CLUSTER-NAME \
  --zone ZONE \
  --enable-cloud-logging \
  --logging=SYSTEM,WORKLOAD,API_SERVER

# Set up log exports to BigQuery for long-term retention
gcloud logging sinks create gke-audit-sink \
  bigquery.googleapis.com/projects/PROJECT-ID/datasets/gke_audit_logs \
  --log-filter='resource.type="gke_cluster"'
```

### Change Control Integration
```bash
# Get 72-hour advance notifications (opt-in via Cloud Logging)
# Configure alerting on these log entries:
# logName="projects/PROJECT-ID/logs/container.googleapis.com%2Fcluster-upgrade-start"
```

### Documentation Requirements
- **Change tickets**: Reference maintenance exclusion names in your change management system
- **Risk assessment**: Document that control plane patches continue during exclusions
- **Rollback procedures**: Maintain documented rollback playbooks for each environment

## Monitoring & Alerting Setup

```bash
# Monitor exclusion status
gcloud container clusters describe CLUSTER-NAME \
  --zone ZONE \
  --format="value(maintenancePolicy.window,maintenancePolicy.exclusions)"

# Set up Cloud Monitoring alerts for:
# - Upgrade start notifications
# - Failed upgrade operations  
# - Clusters approaching End of Support
```

## Annual Maintenance Calendar Template

| Month | Dev | Staging | Prod | Notes |
|-------|-----|---------|------|-------|
| Jan | Auto-upgrade | Auto-upgrade | Auto-upgrade | Post-holidays |
| Feb | Auto-upgrade | Auto-upgrade | Auto-upgrade | |
| **Mar** | Auto-upgrade | Manual only | **FROZEN** | Q1 code freeze |
| Apr | Auto-upgrade | Auto-upgrade | Auto-upgrade | |
| May | Auto-upgrade | Auto-upgrade | Auto-upgrade | |
| **Jun** | Auto-upgrade | Manual only | **FROZEN** | Q2 code freeze |
| Jul | Auto-upgrade | Auto-upgrade | Auto-upgrade | |
| Aug | Auto-upgrade | Auto-upgrade | Auto-upgrade | |
| **Sep** | Auto-upgrade | Manual only | **FROZEN** | Q3 code freeze |
| Oct | Auto-upgrade | Auto-upgrade | Manual only | Pre-audit prep |
| **Nov** | Manual only | Manual only | **LOCKED** | SOX audit |
| **Dec** | Auto-upgrade | Manual only | **FROZEN** | Q4 code freeze |

## Next Steps

1. **Confirm cluster details**: Replace `CLUSTER-NAME` and `ZONE` placeholders with your actual values
2. **Adjust time zones**: Convert maintenance windows to your preferred timezone
3. **Test in dev first**: Apply configuration to dev cluster and verify behavior
4. **Set up monitoring**: Configure alerts for upgrade events and exclusion status
5. **Document procedures**: Update your SOX documentation with these maintenance policies
6. **Review quarterly**: Assess exclusion effectiveness and adjust as needed

This configuration ensures predictable upgrade behavior while maintaining the security posture required for SOX compliance. The "no minor or node upgrades" exclusions provide the stability you need while still allowing critical security patches on the control plane.
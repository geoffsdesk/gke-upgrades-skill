# GKE Maintenance Windows & Exclusions for SOX Compliance

Here's a comprehensive configuration for your regulated financial services environment with SOX compliance requirements.

## Configuration Strategy

**Recommended approach for maximum control:**
- **Weekend maintenance windows** for predictable timing
- **"No minor or node upgrades" exclusions** during normal operations (allows critical security patches)
- **"No upgrades" exclusions** for code freezes and audit periods
- **Regular or Stable release channel** for production stability

## Maintenance Window Configuration

Set recurring weekend windows for all three clusters:

```bash
# Configure Saturday 2-6 AM maintenance window (adjust timezone as needed)
# Cluster 1
gcloud container clusters update PROD-CLUSTER-1 \
  --zone us-central1-a \
  --maintenance-window-start 2024-01-06T02:00:00Z \
  --maintenance-window-end 2024-01-06T06:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Cluster 2  
gcloud container clusters update PROD-CLUSTER-2 \
  --zone us-central1-b \
  --maintenance-window-start 2024-01-06T02:00:00Z \
  --maintenance-window-end 2024-01-06T06:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Cluster 3
gcloud container clusters update PROD-CLUSTER-3 \
  --zone us-central1-c \
  --maintenance-window-start 2024-01-06T02:00:00Z \
  --maintenance-window-end 2024-01-06T06:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## Baseline Exclusion Strategy

For SOX compliance, I recommend **"No minor or node upgrades"** as your default exclusion scope. This allows critical security patches on the control plane while preventing disruptive changes:

```bash
# Set 6-month baseline exclusion (renewable before expiry)
# This blocks minor version upgrades and node pool upgrades but allows CP patches

# Cluster 1
gcloud container clusters update PROD-CLUSTER-1 \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "sox-baseline-protection" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Cluster 2
gcloud container clusters update PROD-CLUSTER-2 \
  --zone us-central1-b \
  --add-maintenance-exclusion-name "sox-baseline-protection" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Cluster 3
gcloud container clusters update PROD-CLUSTER-3 \
  --zone us-central1-c \
  --add-maintenance-exclusion-name "sox-baseline-protection" \
  --add-maintenance-exclusion-start-time "2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

## Quarterly Code Freeze Exclusions

Use **"No upgrades"** exclusions during code freezes (blocks everything including patches):

### Q1 2024 Code Freeze Example
```bash
# Add Q1 code freeze (adjust dates to your freeze periods)
for cluster in PROD-CLUSTER-1 PROD-CLUSTER-2 PROD-CLUSTER-3; do
  for zone in us-central1-a us-central1-b us-central1-c; do
    gcloud container clusters update $cluster \
      --zone $zone \
      --add-maintenance-exclusion-name "q1-2024-code-freeze" \
      --add-maintenance-exclusion-start-time "2024-03-15T00:00:00Z" \
      --add-maintenance-exclusion-end-time "2024-04-15T00:00:00Z" \
      --add-maintenance-exclusion-scope no_upgrades
    break  # Only run once per cluster
  done
done
```

### Template for Other Quarters
```bash
# Q2 2024 Code Freeze
--add-maintenance-exclusion-name "q2-2024-code-freeze" \
--add-maintenance-exclusion-start-time "2024-06-15T00:00:00Z" \
--add-maintenance-exclusion-end-time "2024-07-15T00:00:00Z" \
--add-maintenance-exclusion-scope no_upgrades

# Q3 2024 Code Freeze  
--add-maintenance-exclusion-name "q3-2024-code-freeze" \
--add-maintenance-exclusion-start-time "2024-09-15T00:00:00Z" \
--add-maintenance-exclusion-end-time "2024-10-15T00:00:00Z" \
--add-maintenance-exclusion-scope no_upgrades

# Q4 2024 Code Freeze
--add-maintenance-exclusion-name "q4-2024-code-freeze" \
--add-maintenance-exclusion-start-time "2024-12-15T00:00:00Z" \
--add-maintenance-exclusion-end-time "2025-01-15T00:00:00Z" \
--add-maintenance-exclusion-scope no_upgrades
```

## Annual November Audit Exclusion

```bash
# November 2024 audit period - no upgrades
for cluster in PROD-CLUSTER-1 PROD-CLUSTER-2 PROD-CLUSTER-3; do
  for zone in us-central1-a us-central1-b us-central1-c; do
    gcloud container clusters update $cluster \
      --zone $zone \
      --add-maintenance-exclusion-name "november-2024-audit" \
      --add-maintenance-exclusion-start-time "2024-11-01T00:00:00Z" \
      --add-maintenance-exclusion-end-time "2024-11-30T23:59:59Z" \
      --add-maintenance-exclusion-scope no_upgrades
    break  # Only run once per cluster
  done
done
```

## Release Channel Recommendation

For SOX compliance, use **Regular or Stable** release channel:

```bash
# Check current channel
gcloud container clusters describe PROD-CLUSTER-1 \
  --zone us-central1-a \
  --format="value(releaseChannel.channel)"

# Migrate to Stable channel (most conservative for regulated environments)
gcloud container clusters update PROD-CLUSTER-1 \
  --zone us-central1-a \
  --release-channel stable
```

## Exclusion Management Calendar

| Period | Exclusion Type | Duration | Purpose |
|--------|----------------|----------|---------|
| **Ongoing** | "No minor or node upgrades" | 6-month renewable | SOX baseline protection - allows security patches |
| **Q1 Freeze** | "No upgrades" | 30 days | Complete freeze during code freeze |
| **Q2 Freeze** | "No upgrades" | 30 days | Complete freeze during code freeze |
| **Q3 Freeze** | "No upgrades" | 30 days | Complete freeze during code freeze |
| **November** | "No upgrades" | 30 days | Audit period protection |
| **Q4 Freeze** | "No upgrades" | 30 days | Year-end freeze |

## Monitoring & Compliance

### Verify Configuration
```bash
# Check maintenance windows
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="yaml(maintenancePolicy)"

# List all exclusions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="yaml(maintenancePolicy.exclusions)"
```

### Scheduled Notifications
Enable 72-hour advance notifications for any auto-upgrades:
```bash
# This creates Cloud Logging entries 72h before scheduled upgrades
gcloud logging sinks create gke-upgrade-notifications \
  pubsub.googleapis.com/projects/PROJECT_ID/topics/gke-upgrades \
  --log-filter='resource.type="gke_cluster" AND protoPayload.methodName="google.container.v1.ClusterManager.UpdateCluster"'
```

## SOX Compliance Benefits

✅ **Change Control**: Upgrades only during approved weekend windows  
✅ **Documentation**: All exclusions are named and tracked with timestamps  
✅ **Security**: Control plane security patches still applied via "no minor or node upgrades"  
✅ **Audit Trail**: GKE operations logged to Cloud Audit Logs  
✅ **Freeze Periods**: Complete lockdown during sensitive business periods  
✅ **Predictability**: No surprise upgrades outside defined windows  

## Renewal Process

**Important**: Exclusions have maximum durations and need renewal:
- "No upgrades": 30 days maximum
- "No minor or node upgrades": Until version End of Support
- Plan to renew baseline exclusions every 6 months before expiry

This configuration gives you the maximum control available in GKE while maintaining security patch coverage during normal operations.
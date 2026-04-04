Here's the exact configuration for your GKE maintenance exclusions and upgrade policies:

## 1. Cluster Configuration with Maintenance Exclusions

```yaml
# cluster-config.yaml
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerCluster
metadata:
  name: your-cluster-name
  namespace: your-project-id
spec:
  location: us-central1-a
  
  # Maintenance policy with exclusions
  maintenancePolicy:
    # Define maintenance window (optional but recommended)
    dailyMaintenanceWindow:
      startTime: "02:00"  # 2 AM in cluster timezone
    
    # Maintenance exclusions
    maintenanceExclusions:
      # June code freeze (entire month)
      - name: "june-code-freeze"
        exclusionWindow:
          startTime: "2024-06-01T00:00:00Z"
          endTime: "2024-06-30T23:59:59Z"
        scopes:
          - "UPGRADES"
          - "NO_MINOR_UPGRADES"
          - "NO_MINOR_OR_NODE_UPGRADES"
      
      # Black Friday/Cyber Monday period
      - name: "black-friday-cyber-monday"
        exclusionWindow:
          startTime: "2024-11-20T00:00:00Z"
          endTime: "2024-12-05T23:59:59Z"
        scopes:
          - "UPGRADES"
          - "NO_MINOR_UPGRADES"
          - "NO_MINOR_OR_NODE_UPGRADES"
  
  # Release channel with manual minor upgrades
  releaseChannel:
    channel: "REGULAR"  # or "STABLE" for more conservative updates
  
  # Cluster-level version management
  minMasterVersion: "1.28.3-gke.1286000"  # Pin to specific version
  
  # Node pool configuration
  nodePool:
    - name: default-pool
      nodeConfig:
        machineType: e2-medium
        diskSizeGb: 100
      
      # Node management settings
      management:
        autoUpgrade: false  # Disable automatic minor version upgrades
        autoRepair: true    # Keep auto-repair enabled for stability
      
      # Version management for nodes
      version: "1.28.3-gke.1286000"  # Pin node version
```

## 2. Terraform Configuration

```hcl
# main.tf
resource "google_container_cluster" "primary" {
  name     = "your-cluster-name"
  location = "us-central1-a"

  # Maintenance policy
  maintenance_policy {
    daily_maintenance_window {
      start_time = "02:00"
    }

    # June code freeze
    maintenance_exclusion {
      exclusion_name = "june-code-freeze"
      start_time     = "2024-06-01T00:00:00Z"
      end_time       = "2024-06-30T23:59:59Z"
      exclusion_options {
        scope = "UPGRADES"
      }
    }

    # Black Friday/Cyber Monday
    maintenance_exclusion {
      exclusion_name = "black-friday-cyber-monday"
      start_time     = "2024-11-20T00:00:00Z"
      end_time       = "2024-12-05T23:59:59Z"
      exclusion_options {
        scope = "UPGRADES"
      }
    }
  }

  # Release channel
  release_channel {
    channel = "REGULAR"
  }

  # Pin master version to prevent automatic minor upgrades
  min_master_version = "1.28.3-gke.1286000"

  # Remove default node pool
  remove_default_node_pool = true
  initial_node_count       = 1
}

# Separate node pool with controlled upgrades
resource "google_container_node_pool" "primary_nodes" {
  name       = "primary-node-pool"
  location   = "us-central1-a"
  cluster    = google_container_cluster.primary.name
  node_count = 3

  # Pin node version
  version = "1.28.3-gke.1286000"

  node_config {
    machine_type = "e2-medium"
    disk_size_gb = 100

    oauth_scopes = [
      "https://www.googleapis.com/auth/logging.write",
      "https://www.googleapis.com/auth/monitoring",
    ]
  }

  management {
    auto_repair  = true
    auto_upgrade = false  # Disable automatic upgrades
  }

  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
    strategy        = "SURGE"
  }
}
```

## 3. gcloud Commands for Existing Clusters

```bash
# Add June code freeze exclusion
gcloud container clusters update your-cluster-name \
    --zone=us-central1-a \
    --add-maintenance-exclusion-name=june-code-freeze \
    --add-maintenance-exclusion-start=2024-06-01T00:00:00Z \
    --add-maintenance-exclusion-end=2024-06-30T23:59:59Z \
    --add-maintenance-exclusion-scope=UPGRADES

# Add Black Friday/Cyber Monday exclusion
gcloud container clusters update your-cluster-name \
    --zone=us-central1-a \
    --add-maintenance-exclusion-name=black-friday-cyber-monday \
    --add-maintenance-exclusion-start=2024-11-20T00:00:00Z \
    --add-maintenance-exclusion-end=2024-12-05T23:59:59Z \
    --add-maintenance-exclusion-scope=UPGRADES

# Disable auto-upgrade on existing node pools
gcloud container node-pools update default-pool \
    --cluster=your-cluster-name \
    --zone=us-central1-a \
    --no-enable-autoupgrade

# Set maintenance window
gcloud container clusters update your-cluster-name \
    --zone=us-central1-a \
    --maintenance-window-start=2024-01-01T02:00:00Z \
    --maintenance-window-end=2024-01-01T06:00:00Z \
    --maintenance-window-recurrence='FREQ=WEEKLY;BYDAY=SA'
```

## 4. Recurring Annual Script

```bash
#!/bin/bash
# update-maintenance-exclusions.sh

CLUSTER_NAME="your-cluster-name"
ZONE="us-central1-a"
CURRENT_YEAR=$(date +%Y)
NEXT_YEAR=$((CURRENT_YEAR + 1))

# Remove old exclusions
gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --remove-maintenance-exclusion-name=june-code-freeze \
    --quiet

gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --remove-maintenance-exclusion-name=black-friday-cyber-monday \
    --quiet

# Add new exclusions for next year
gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --add-maintenance-exclusion-name=june-code-freeze \
    --add-maintenance-exclusion-start=${NEXT_YEAR}-06-01T00:00:00Z \
    --add-maintenance-exclusion-end=${NEXT_YEAR}-06-30T23:59:59Z \
    --add-maintenance-exclusion-scope=UPGRADES

gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --add-maintenance-exclusion-name=black-friday-cyber-monday \
    --add-maintenance-exclusion-start=${NEXT_YEAR}-11-20T00:00:00Z \
    --add-maintenance-exclusion-end=${NEXT_YEAR}-12-05T23:59:59Z \
    --add-maintenance-exclusion-scope=UPGRADES

echo "Maintenance exclusions updated for year: $NEXT_YEAR"
```

## 5. Monitoring and Alerts

```yaml
# maintenance-alert-policy.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: gke-maintenance-alerts
spec:
  groups:
  - name: gke.maintenance
    rules:
    - alert: GKEMaintenanceExclusionExpiring
      expr: |
        (gke_cluster_maintenance_exclusion_end_time - time()) < 86400 * 7
      for: 0m
      labels:
        severity: warning
      annotations:
        summary: "GKE maintenance exclusion expiring soon"
        description: "Maintenance exclusion for cluster {{ $labels.cluster }} expires in less than 7 days"

    - alert: GKEPendingUpgrades
      expr: |
        gke_cluster_pending_upgrades > 0
      for: 5m
      labels:
        severity: info
      annotations:
        summary: "GKE cluster has pending upgrades"
        description: "Cluster {{ $labels.cluster }} has {{ $value }} pending upgrades"
```

## Key Points:

1. **Maintenance Exclusions**: Block all upgrades during June and Black Friday period
2. **Manual Upgrades**: `autoUpgrade: false` prevents automatic minor version upgrades
3. **Auto-Repair**: Kept enabled for node stability (doesn't affect versions)
4. **Version Pinning**: Explicit version specification prevents drift
5. **Release Channel**: Use REGULAR or STABLE based on your risk tolerance
6. **Annual Updates**: Script to refresh exclusion dates yearly

## Usage Instructions:

1. Update cluster names, zones, and versions in the configurations
2. Run the annual script as a cron job in December to update next year's exclusions
3. Monitor pending upgrades and plan manual upgrade windows
4. Test upgrades in staging environments first
5. Use `gcloud container clusters describe` to verify current exclusions

This configuration ensures no automatic minor version upgrades occur, with specific blackout periods for your critical business dates.
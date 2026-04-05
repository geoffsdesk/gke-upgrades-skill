Here's the exact configuration for your GKE maintenance exclusions and upgrade policies:

## 1. Cluster Configuration with Maintenance Policy

```yaml
# cluster-maintenance-config.yaml
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerCluster
metadata:
  name: your-cluster-name
  namespace: your-project-namespace
spec:
  location: us-central1-a
  releaseChannel:
    channel: REGULAR
  maintenancePolicy:
    dailyMaintenanceWindow:
      startTime: "03:00"  # 3 AM maintenance window
    maintenanceExclusions:
      quarterly-freeze:
        exclusionName: "quarterly-code-freeze"
        startTime: "2024-06-01T00:00:00Z"
        endTime: "2024-06-30T23:59:59Z"
        exclusionOptions:
          scope: "NO_UPGRADES"
      holiday-shopping:
        exclusionName: "black-friday-cyber-monday"
        startTime: "2024-11-15T00:00:00Z"
        endTime: "2024-12-05T23:59:59Z"
        exclusionOptions:
          scope: "NO_UPGRADES"
  # Prevent automatic minor version upgrades
  nodeConfig:
    machineType: e2-medium
  nodePool:
    - name: default-pool
      management:
        autoUpgrade: false  # Disable automatic upgrades
        autoRepair: true    # Keep auto-repair enabled
```

## 2. Terraform Configuration

```hcl
# main.tf
resource "google_container_cluster" "primary" {
  name     = "your-cluster-name"
  location = "us-central1-a"
  
  release_channel {
    channel = "REGULAR"
  }

  maintenance_policy {
    daily_maintenance_window {
      start_time = "03:00"
    }

    maintenance_exclusion {
      exclusion_name = "quarterly-code-freeze-2024"
      start_time     = "2024-06-01T00:00:00Z"
      end_time       = "2024-06-30T23:59:59Z"
      
      exclusion_options {
        scope = "NO_UPGRADES"
      }
    }

    maintenance_exclusion {
      exclusion_name = "black-friday-cyber-monday-2024"
      start_time     = "2024-11-15T00:00:00Z"
      end_time       = "2024-12-05T23:59:59Z"
      
      exclusion_options {
        scope = "NO_UPGRADES"
      }
    }
  }

  # Default node pool with controlled upgrades
  remove_default_node_pool = true
  initial_node_count       = 1
}

resource "google_container_node_pool" "primary_nodes" {
  name       = "primary-node-pool"
  location   = "us-central1-a"
  cluster    = google_container_cluster.primary.name
  node_count = 1

  management {
    auto_repair  = true
    auto_upgrade = false  # Disable automatic minor version upgrades
  }

  node_config {
    machine_type = "e2-medium"
    
    oauth_scopes = [
      "https://www.googleapis.com/auth/logging.write",
      "https://www.googleapis.com/auth/monitoring",
    ]
  }

  upgrade_settings {
    strategy        = "SURGE"
    max_surge       = 1
    max_unavailable = 0
  }
}
```

## 3. gcloud CLI Commands

```bash
# Create maintenance exclusions
gcloud container clusters update YOUR_CLUSTER_NAME \
    --zone=us-central1-a \
    --add-maintenance-exclusion-name=quarterly-code-freeze-2024 \
    --add-maintenance-exclusion-start=2024-06-01T00:00:00Z \
    --add-maintenance-exclusion-end=2024-06-30T23:59:59Z \
    --add-maintenance-exclusion-scope=no-upgrades

gcloud container clusters update YOUR_CLUSTER_NAME \
    --zone=us-central1-a \
    --add-maintenance-exclusion-name=black-friday-cyber-monday-2024 \
    --add-maintenance-exclusion-start=2024-11-15T00:00:00Z \
    --add-maintenance-exclusion-end=2024-12-05T23:59:59Z \
    --add-maintenance-exclusion-scope=no-upgrades

# Disable auto-upgrade for existing node pools
gcloud container node-pools update default-pool \
    --cluster=YOUR_CLUSTER_NAME \
    --zone=us-central1-a \
    --no-enable-autoupgrade

# Set maintenance window
gcloud container clusters update YOUR_CLUSTER_NAME \
    --zone=us-central1-a \
    --maintenance-window-start=2024-01-01T03:00:00Z \
    --maintenance-window-end=2024-01-01T07:00:00Z \
    --maintenance-window-recurrence="FREQ=DAILY"
```

## 4. Annual Recurring Script

```bash
#!/bin/bash
# update-maintenance-exclusions.sh
# Run this script annually to update exclusion dates

CLUSTER_NAME="your-cluster-name"
ZONE="us-central1-a"
CURRENT_YEAR=$(date +%Y)
NEXT_YEAR=$((CURRENT_YEAR + 1))

# Remove old exclusions
gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --remove-maintenance-exclusion-name=quarterly-code-freeze-$CURRENT_YEAR \
    --remove-maintenance-exclusion-name=black-friday-cyber-monday-$CURRENT_YEAR

# Add new exclusions for next year
gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --add-maintenance-exclusion-name=quarterly-code-freeze-$NEXT_YEAR \
    --add-maintenance-exclusion-start=${NEXT_YEAR}-06-01T00:00:00Z \
    --add-maintenance-exclusion-end=${NEXT_YEAR}-06-30T23:59:59Z \
    --add-maintenance-exclusion-scope=no-upgrades

gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --add-maintenance-exclusion-name=black-friday-cyber-monday-$NEXT_YEAR \
    --add-maintenance-exclusion-start=${NEXT_YEAR}-11-15T00:00:00Z \
    --add-maintenance-exclusion-end=${NEXT_YEAR}-12-05T23:59:59Z \
    --add-maintenance-exclusion-scope=no-upgrades
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
        (gke_maintenance_exclusion_end_time - time()) < 604800  # 7 days
      for: 1h
      labels:
        severity: warning
      annotations:
        summary: "GKE maintenance exclusion expiring soon"
        description: "Maintenance exclusion {{ $labels.exclusion_name }} expires in less than 7 days"
```

## Key Configuration Points:

1. **Maintenance Exclusions**: 
   - June: Full month code freeze
   - November 15 - December 5: Holiday shopping period
   - Scope: `NO_UPGRADES` prevents all automatic upgrades

2. **Node Pool Settings**:
   - `auto_upgrade = false`: Prevents automatic minor version upgrades
   - `auto_repair = true`: Keeps node auto-repair enabled for stability

3. **Upgrade Control**:
   - All upgrades require manual approval
   - Use `gcloud container clusters upgrade` when ready
   - Monitor available upgrades with `gcloud container get-server-config`

4. **Annual Maintenance**:
   - Update exclusion dates yearly using the provided script
   - Monitor exclusions with `gcloud container clusters describe`

This configuration ensures complete control over when maintenance and upgrades occur while protecting your critical business periods.
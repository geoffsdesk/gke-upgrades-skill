Here's the exact configuration for your GKE maintenance exclusions and policies:

## 1. Cluster Configuration with Maintenance Policy

```yaml
# cluster-maintenance-config.yaml
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerCluster
metadata:
  name: your-cluster-name
  namespace: your-project-namespace
spec:
  location: us-central1
  initialNodeCount: 1
  
  # Maintenance Policy Configuration
  maintenancePolicy:
    # Daily maintenance window (4-hour window during low traffic)
    dailyMaintenanceWindow:
      startTime: "02:00"  # 2 AM local time
    
    # Maintenance exclusions
    maintenanceExclusion:
      # Q2 Code Freeze - Entire June
      - exclusionName: "q2-code-freeze"
        startTime: "2024-06-01T00:00:00Z"
        endTime: "2024-06-30T23:59:59Z"
        exclusionOptions:
          scope: "NO_UPGRADES"
      
      # Black Friday/Cyber Monday Period
      - exclusionName: "black-friday-cyber-monday"
        startTime: "2024-11-25T00:00:00Z"  # Week before Black Friday
        endTime: "2024-12-03T23:59:59Z"    # Week after Cyber Monday
        exclusionOptions:
          scope: "NO_UPGRADES"
      
      # Repeat for 2025 and beyond
      - exclusionName: "q2-code-freeze-2025"
        startTime: "2025-06-01T00:00:00Z"
        endTime: "2025-06-30T23:59:59Z"
        exclusionOptions:
          scope: "NO_UPGRADES"
      
      - exclusionName: "black-friday-cyber-monday-2025"
        startTime: "2025-11-24T00:00:00Z"
        endTime: "2025-12-02T23:59:59Z"
        exclusionOptions:
          scope: "NO_UPGRADES"

  # Release Channel Configuration - Use RAPID or REGULAR, not STABLE
  # This gives you more control over when updates happen
  releaseChannel:
    channel: "REGULAR"  # Change to RAPID if you want faster access to new versions
```

## 2. Terraform Configuration

```hcl
# main.tf
resource "google_container_cluster" "primary" {
  name     = "your-cluster-name"
  location = "us-central1"
  
  # Remove default node pool
  remove_default_node_pool = true
  initial_node_count       = 1

  # Maintenance policy
  maintenance_policy {
    daily_maintenance_window {
      start_time = "02:00"
    }

    # Q2 Code Freeze - June
    maintenance_exclusion {
      exclusion_name = "q2-code-freeze-2024"
      start_time     = "2024-06-01T00:00:00Z"
      end_time       = "2024-06-30T23:59:59Z"
      
      exclusion_options {
        scope = "NO_UPGRADES"
      }
    }

    # Black Friday/Cyber Monday
    maintenance_exclusion {
      exclusion_name = "black-friday-cyber-monday-2024"
      start_time     = "2024-11-25T00:00:00Z"
      end_time       = "2024-12-03T23:59:59Z"
      
      exclusion_options {
        scope = "NO_UPGRADES"
      }
    }

    # 2025 exclusions
    maintenance_exclusion {
      exclusion_name = "q2-code-freeze-2025"
      start_time     = "2025-06-01T00:00:00Z"
      end_time       = "2025-06-30T23:59:59Z"
      
      exclusion_options {
        scope = "NO_UPGRADES"
      }
    }

    maintenance_exclusion {
      exclusion_name = "black-friday-cyber-monday-2025"
      start_time     = "2025-11-24T00:00:00Z"
      end_time       = "2025-12-02T23:59:59Z"
      
      exclusion_options {
        scope = "NO_UPGRADES"
      }
    }
  }

  # Release channel - use REGULAR for balance of stability and control
  release_channel {
    channel = "REGULAR"
  }

  # Disable automatic node upgrades and repairs for maximum control
  node_config {
    machine_type = "e2-medium"
  }
}

# Separate node pool with upgrade controls
resource "google_container_node_pool" "primary_nodes" {
  name       = "primary-node-pool"
  location   = "us-central1"
  cluster    = google_container_cluster.primary.name
  node_count = 3

  management {
    auto_repair  = true
    auto_upgrade = false  # Disable automatic upgrades for manual control
  }

  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
    strategy        = "SURGE"
  }

  node_config {
    machine_type = "e2-standard-2"
    
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]
  }
}
```

## 3. gcloud Commands for Existing Clusters

```bash
# Update existing cluster with maintenance exclusions

# Set daily maintenance window
gcloud container clusters update YOUR_CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --maintenance-window-start="02:00" \
    --maintenance-window-end="06:00"

# Add Q2 code freeze exclusion (June 2024)
gcloud container clusters update YOUR_CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --add-maintenance-exclusion-end="2024-06-30T23:59:59Z" \
    --add-maintenance-exclusion-name="q2-code-freeze-2024" \
    --add-maintenance-exclusion-scope="NO_UPGRADES" \
    --add-maintenance-exclusion-start="2024-06-01T00:00:00Z"

# Add Black Friday/Cyber Monday exclusion
gcloud container clusters update YOUR_CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --add-maintenance-exclusion-end="2024-12-03T23:59:59Z" \
    --add-maintenance-exclusion-name="black-friday-cyber-monday-2024" \
    --add-maintenance-exclusion-scope="NO_UPGRADES" \
    --add-maintenance-exclusion-start="2024-11-25T00:00:00Z"

# Disable automatic node upgrades for manual control
gcloud container node-pools update NODEPOOL_NAME \
    --cluster=YOUR_CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --no-enable-autoupgrade
```

## 4. Automation Script for Annual Exclusion Updates

```bash
#!/bin/bash
# update-maintenance-exclusions.sh

CLUSTER_NAME="your-cluster-name"
ZONE="us-central1"
CURRENT_YEAR=$(date +%Y)
NEXT_YEAR=$((CURRENT_YEAR + 1))

# Add next year's exclusions
echo "Adding maintenance exclusions for $NEXT_YEAR..."

# Q2 Code Freeze
gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --add-maintenance-exclusion-end="${NEXT_YEAR}-06-30T23:59:59Z" \
    --add-maintenance-exclusion-name="q2-code-freeze-${NEXT_YEAR}" \
    --add-maintenance-exclusion-scope="NO_UPGRADES" \
    --add-maintenance-exclusion-start="${NEXT_YEAR}-06-01T00:00:00Z"

# Black Friday/Cyber Monday (calculate dates dynamically)
BLACK_FRIDAY=$(python3 -c "
import datetime
year = $NEXT_YEAR
november_first = datetime.date(year, 11, 1)
first_thursday = november_first + datetime.timedelta(days=(3 - november_first.weekday()) % 7)
black_friday = first_thursday + datetime.timedelta(days=22)  # 4th Thursday + 1 day
exclusion_start = black_friday - datetime.timedelta(days=7)  # Week before
exclusion_end = black_friday + datetime.timedelta(days=9)    # Week after Cyber Monday
print(f'{exclusion_start}T00:00:00Z,{exclusion_end}T23:59:59Z')
")

START_DATE=$(echo $BLACK_FRIDAY | cut -d',' -f1)
END_DATE=$(echo $BLACK_FRIDAY | cut -d',' -f2)

gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --add-maintenance-exclusion-end="$END_DATE" \
    --add-maintenance-exclusion-name="black-friday-cyber-monday-${NEXT_YEAR}" \
    --add-maintenance-exclusion-scope="NO_UPGRADES" \
    --add-maintenance-exclusion-start="$START_DATE"

echo "Maintenance exclusions added for $NEXT_YEAR"
```

## 5. Manual Upgrade Process

```bash
# Check available versions
gcloud container get-server-config --zone=YOUR_ZONE

# Upgrade master/control plane (do this first)
gcloud container clusters upgrade YOUR_CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --master \
    --cluster-version=VERSION_NUMBER

# Upgrade specific node pool (after master upgrade)
gcloud container clusters upgrade YOUR_CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --node-pool=NODEPOOL_NAME \
    --cluster-version=VERSION_NUMBER
```

## 6. Monitoring and Alerting

```yaml
# Create a Cloud Monitoring alert for pending upgrades
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: gke-maintenance-alerts
spec:
  groups:
  - name: gke.maintenance
    rules:
    - alert: GKEUpgradeAvailable
      expr: |
        gke_cluster_upgrade_available == 1
      for: 24h
      labels:
        severity: warning
      annotations:
        summary: "GKE cluster upgrade available"
        description: "Cluster {{ $labels.cluster_name }} has an upgrade available. Review and schedule manual upgrade."
```

## Key Points:

1. **Exclusion Scope**: `NO_UPGRADES` blocks both node and master upgrades
2. **Time Zones**: All times are in UTC - adjust for your local timezone
3. **Annual Updates**: You'll need to add new exclusions each year (use the automation script)
4. **Manual Control**: Disabled auto-upgrades on node pools for complete control
5. **Release Channel**: Using `REGULAR` channel gives you control while still getting security updates

Run the automation script annually to add next year's exclusions, and always test upgrades in a staging environment first!
Here's the exact configuration to set up maintenance exclusions and policies for your GKE clusters:

## 1. Terraform Configuration

```hcl
# maintenance.tf
resource "google_container_cluster" "primary" {
  name     = "your-cluster-name"
  location = "us-central1-a"
  
  # Disable automatic upgrades - requires explicit approval
  node_config {
    # Node configuration here
  }

  # Maintenance policy configuration
  maintenance_policy {
    # Set maintenance window to off-peak hours
    daily_maintenance_window {
      start_time = "03:00"  # 3 AM in cluster's timezone
    }

    # Quarterly code freeze exclusion (June)
    maintenance_exclusion {
      exclusion_name = "june-code-freeze"
      start_time     = "2024-06-01T00:00:00Z"
      end_time       = "2024-06-30T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    # Black Friday/Cyber Monday exclusion (November)
    maintenance_exclusion {
      exclusion_name = "black-friday-cyber-monday"
      start_time     = "2024-11-15T00:00:00Z"  # Start before BF week
      end_time       = "2024-12-05T23:59:59Z"  # End after CM week
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }
  }

  # Disable automatic node upgrades - manual control only
  node_pool {
    name       = "default-pool"
    node_count = 3

    management {
      auto_upgrade = false  # Disable automatic upgrades
      auto_repair  = true   # Keep auto-repair enabled for stability
    }
  }

  # Release channel configuration for controlled upgrades
  release_channel {
    channel = "STABLE"  # Use STABLE channel, avoid RAPID
  }
}
```

## 2. gcloud CLI Configuration

```bash
#!/bin/bash
# maintenance-config.sh

CLUSTER_NAME="your-cluster-name"
ZONE="us-central1-a"
PROJECT_ID="your-project-id"

# Set maintenance window
gcloud container clusters update $CLUSTER_NAME \
  --zone=$ZONE \
  --maintenance-window-start="2024-01-01T03:00:00Z" \
  --maintenance-window-end="2024-01-01T07:00:00Z" \
  --maintenance-window-recurrence="FREQ=DAILY"

# Add June code freeze exclusion
gcloud container clusters update $CLUSTER_NAME \
  --zone=$ZONE \
  --add-maintenance-exclusion-name="june-code-freeze-2024" \
  --add-maintenance-exclusion-start="2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end="2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope="ALL_UPGRADES"

# Add Black Friday/Cyber Monday exclusion
gcloud container clusters update $CLUSTER_NAME \
  --zone=$ZONE \
  --add-maintenance-exclusion-name="holiday-shopping-2024" \
  --add-maintenance-exclusion-start="2024-11-15T00:00:00Z" \
  --add-maintenance-exclusion-end="2024-12-05T23:59:59Z" \
  --add-maintenance-exclusion-scope="ALL_UPGRADES"

# Disable automatic node upgrades
gcloud container node-pools update default-pool \
  --cluster=$CLUSTER_NAME \
  --zone=$ZONE \
  --no-enable-autoupgrade
```

## 3. YAML Configuration (for existing clusters)

```yaml
# maintenance-policy.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: maintenance-schedule
  namespace: kube-system
data:
  policy.yaml: |
    maintenancePolicy:
      window:
        dailyMaintenanceWindow:
          startTime: "03:00"
          duration: "4h"
      maintenanceExclusions:
        june-code-freeze-2024:
          startTime: "2024-06-01T00:00:00Z"
          endTime: "2024-06-30T23:59:59Z"
          scope: "ALL_UPGRADES"
        holiday-shopping-2024:
          startTime: "2024-11-15T00:00:00Z"
          endTime: "2024-12-05T23:59:59Z"
          scope: "ALL_UPGRADES"
```

## 4. Annual Maintenance Script

```bash
#!/bin/bash
# annual-maintenance-update.sh
# Run this script annually to update exclusion dates

CURRENT_YEAR=$(date +%Y)
NEXT_YEAR=$((CURRENT_YEAR + 1))

# Function to update maintenance exclusions
update_exclusions() {
  local cluster=$1
  local zone=$2
  
  # Remove old exclusions
  gcloud container clusters update $cluster \
    --zone=$zone \
    --remove-maintenance-exclusion-name="june-code-freeze-$CURRENT_YEAR" \
    --remove-maintenance-exclusion-name="holiday-shopping-$CURRENT_YEAR"
  
  # Add new year exclusions
  # June code freeze
  gcloud container clusters update $cluster \
    --zone=$zone \
    --add-maintenance-exclusion-name="june-code-freeze-$NEXT_YEAR" \
    --add-maintenance-exclusion-start="${NEXT_YEAR}-06-01T00:00:00Z" \
    --add-maintenance-exclusion-end="${NEXT_YEAR}-06-30T23:59:59Z" \
    --add-maintenance-exclusion-scope="ALL_UPGRADES"
  
  # Black Friday/Cyber Monday
  gcloud container clusters update $cluster \
    --zone=$zone \
    --add-maintenance-exclusion-name="holiday-shopping-$NEXT_YEAR" \
    --add-maintenance-exclusion-start="${NEXT_YEAR}-11-15T00:00:00Z" \
    --add-maintenance-exclusion-end="${NEXT_YEAR}-12-05T23:59:59Z" \
    --add-maintenance-exclusion-scope="ALL_UPGRADES"
}

# Update all clusters
CLUSTERS=("prod-cluster" "staging-cluster")
ZONES=("us-central1-a" "us-west1-b")

for i in "${!CLUSTERS[@]}"; do
  update_exclusions "${CLUSTERS[$i]}" "${ZONES[$i]}"
done
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
  - name: gke-maintenance
    rules:
    - alert: GKEMaintenanceScheduled
      expr: increase(gke_maintenance_events_total[1h]) > 0
      for: 0m
      labels:
        severity: warning
      annotations:
        summary: "GKE maintenance scheduled"
        description: "Maintenance has been scheduled for cluster {{ $labels.cluster_name }}"
    
    - alert: GKEUpgradeAvailable
      expr: gke_upgrade_available == 1
      for: 24h
      labels:
        severity: info
      annotations:
        summary: "GKE upgrade available"
        description: "A new version is available for cluster {{ $labels.cluster_name }}"
```

## 6. Manual Upgrade Process

```bash
#!/bin/bash
# manual-upgrade.sh
# Use this for controlled upgrades outside exclusion periods

CLUSTER_NAME="your-cluster-name"
ZONE="us-central1-a"

# Check available versions
echo "Available master versions:"
gcloud container get-server-config --zone=$ZONE

# Upgrade master (control plane)
read -p "Enter target master version: " MASTER_VERSION
gcloud container clusters upgrade $CLUSTER_NAME \
  --zone=$ZONE \
  --master \
  --cluster-version=$MASTER_VERSION

# Upgrade node pools (after master upgrade)
echo "Available node versions:"
gcloud container get-server-config --zone=$ZONE

read -p "Enter target node version: " NODE_VERSION
gcloud container clusters upgrade $CLUSTER_NAME \
  --zone=$ZONE \
  --node-pool=default-pool \
  --cluster-version=$NODE_VERSION
```

## Key Points:

1. **Maintenance Exclusions**: Blocks ALL upgrades during June and November 15-December 5
2. **Manual Control**: Auto-upgrades disabled, requiring explicit approval
3. **Maintenance Window**: Set to 3 AM-7 AM for minimal business impact
4. **Stable Channel**: Avoids bleeding-edge releases
5. **Auto-repair**: Kept enabled for node health while blocking upgrades

Remember to:
- Update exclusion dates annually
- Test upgrades in staging first
- Monitor for security patches during exclusion periods
- Set up alerts for available upgrades
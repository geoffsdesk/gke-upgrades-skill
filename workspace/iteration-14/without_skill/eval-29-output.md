I'll help you set up maintenance exclusions and policies for your GKE clusters to handle your specific requirements. Here's the complete configuration:

## 1. Terraform Configuration

```hcl
# maintenance-policy.tf
resource "google_container_cluster" "primary" {
  name     = "your-cluster-name"
  location = "us-central1"
  
  # Disable automatic upgrades for minor versions
  release_channel {
    channel = "REGULAR"  # or "RAPID", "STABLE" - but we'll override below
  }

  # Maintenance policy configuration
  maintenance_policy {
    # Daily maintenance window (required)
    daily_maintenance_window {
      start_time = "03:00"  # 3 AM in cluster's timezone
    }

    # Maintenance exclusions
    maintenance_exclusion {
      exclusion_name = "quarterly-code-freeze-june"
      start_time     = "2024-06-01T00:00:00Z"
      end_time       = "2024-07-01T00:00:00Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    maintenance_exclusion {
      exclusion_name = "black-friday-cyber-monday"
      start_time     = "2024-11-20T00:00:00Z"
      end_time       = "2024-12-05T00:00:00Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    # Recurring exclusions using recurrence rule (RRULE)
    maintenance_exclusion {
      exclusion_name = "quarterly-code-freeze-june-recurring"
      start_time     = "2024-06-01T00:00:00Z"
      end_time       = "2024-07-01T00:00:00Z"
      recurrence     = "FREQ=YEARLY;BYMONTH=6"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    maintenance_exclusion {
      exclusion_name = "black-friday-period-recurring"
      start_time     = "2024-11-20T00:00:00Z"
      end_time       = "2024-12-05T00:00:00Z"
      recurrence     = "FREQ=YEARLY;BYMONTH=11"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }
  }

  # Node pool configuration with explicit upgrade control
  node_pool {
    name       = "default-pool"
    node_count = 3

    management {
      auto_repair  = true
      auto_upgrade = false  # Disable automatic minor version upgrades
    }

    upgrade_settings {
      strategy      = "SURGE"
      max_surge     = 1
      max_unavailable = 0
    }

    node_config {
      machine_type = "e2-medium"
      disk_size_gb = 100
      disk_type    = "pd-standard"

      oauth_scopes = [
        "https://www.googleapis.com/auth/cloud-platform"
      ]
    }
  }

  # Disable automatic node upgrades at cluster level
  node_config {
    # This applies to default node pool if not specified in node_pool block
  }

  # Network policy (optional but recommended)
  network_policy {
    enabled = true
  }

  # Workload Identity (recommended)
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }
}
```

## 2. gcloud CLI Commands

```bash
# Create maintenance exclusions for existing clusters

# June code freeze (one-time)
gcloud container clusters update YOUR_CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --add-maintenance-exclusion-name=june-code-freeze-2024 \
    --add-maintenance-exclusion-start=2024-06-01T00:00:00Z \
    --add-maintenance-exclusion-end=2024-07-01T00:00:00Z \
    --add-maintenance-exclusion-scope=all-upgrades

# Black Friday period (one-time)
gcloud container clusters update YOUR_CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --add-maintenance-exclusion-name=black-friday-2024 \
    --add-maintenance-exclusion-start=2024-11-20T00:00:00Z \
    --add-maintenance-exclusion-end=2024-12-05T00:00:00Z \
    --add-maintenance-exclusion-scope=all-upgrades

# Set maintenance window
gcloud container clusters update YOUR_CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --maintenance-window-start=2024-01-01T03:00:00Z \
    --maintenance-window-end=2024-01-01T07:00:00Z \
    --maintenance-window-recurrence="FREQ=DAILY"

# Disable auto-upgrade for node pools
gcloud container node-pools update default-pool \
    --cluster=YOUR_CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --no-enable-autoupgrade
```

## 3. YAML Configuration (for GitOps)

```yaml
# cluster-maintenance-policy.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: maintenance-policy-config
  namespace: kube-system
data:
  policy.yaml: |
    maintenancePolicy:
      dailyMaintenanceWindow:
        startTime: "03:00"
      maintenanceExclusions:
        - exclusionName: "june-code-freeze"
          startTime: "2024-06-01T00:00:00Z"
          endTime: "2024-07-01T00:00:00Z"
          recurrence: "FREQ=YEARLY;BYMONTH=6"
          exclusionOptions:
            scope: "ALL_UPGRADES"
        - exclusionName: "black-friday-period"
          startTime: "2024-11-20T00:00:00Z"
          endTime: "2024-12-05T00:00:00Z"
          recurrence: "FREQ=YEARLY;BYMONTH=11"
          exclusionOptions:
            scope: "ALL_UPGRADES"
```

## 4. Management Script

```bash
#!/bin/bash
# maintenance-manager.sh

PROJECT_ID="your-project-id"
CLUSTER_NAME="your-cluster-name"
ZONE="your-zone"

# Function to add yearly recurring exclusions
add_maintenance_exclusions() {
    local year=$1
    
    echo "Adding maintenance exclusions for $year..."
    
    # June code freeze
    gcloud container clusters update $CLUSTER_NAME \
        --project=$PROJECT_ID \
        --zone=$ZONE \
        --add-maintenance-exclusion-name="june-code-freeze-$year" \
        --add-maintenance-exclusion-start="${year}-06-01T00:00:00Z" \
        --add-maintenance-exclusion-end="${year}-07-01T00:00:00Z" \
        --add-maintenance-exclusion-scope=all-upgrades
    
    # Black Friday period
    gcloud container clusters update $CLUSTER_NAME \
        --project=$PROJECT_ID \
        --zone=$ZONE \
        --add-maintenance-exclusion-name="black-friday-$year" \
        --add-maintenance-exclusion-start="${year}-11-20T00:00:00Z" \
        --add-maintenance-exclusion-end="${year}-12-05T00:00:00Z" \
        --add-maintenance-exclusion-scope=all-upgrades
}

# Function to check current maintenance exclusions
check_exclusions() {
    echo "Current maintenance exclusions:"
    gcloud container clusters describe $CLUSTER_NAME \
        --project=$PROJECT_ID \
        --zone=$ZONE \
        --format="value(maintenancePolicy.maintenanceExclusions[].exclusionName,maintenancePolicy.maintenanceExclusions[].startTime,maintenancePolicy.maintenanceExclusions[].endTime)"
}

# Function to manually trigger upgrade (when ready)
manual_upgrade() {
    local target_version=$1
    echo "Initiating manual upgrade to $target_version..."
    
    # Upgrade master first
    gcloud container clusters upgrade $CLUSTER_NAME \
        --project=$PROJECT_ID \
        --zone=$ZONE \
        --master \
        --cluster-version=$target_version
    
    # Then upgrade nodes
    gcloud container clusters upgrade $CLUSTER_NAME \
        --project=$PROJECT_ID \
        --zone=$ZONE \
        --node-pool=default-pool
}

# Main script logic
case "$1" in
    "add-exclusions")
        add_maintenance_exclusions $2
        ;;
    "check")
        check_exclusions
        ;;
    "upgrade")
        manual_upgrade $2
        ;;
    *)
        echo "Usage: $0 {add-exclusions YEAR|check|upgrade VERSION}"
        exit 1
        ;;
esac
```

## 5. Monitoring and Alerting

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
    - alert: GKEUpgradeAvailable
      expr: |
        gke_cluster_upgrade_available == 1
      for: 24h
      labels:
        severity: info
      annotations:
        summary: "GKE cluster upgrade available"
        description: "Cluster {{ $labels.cluster_name }} has an upgrade available. Manual intervention required."
    
    - alert: MaintenanceExclusionExpiring
      expr: |
        (gke_maintenance_exclusion_end_time - time()) < 86400 * 7
      labels:
        severity: warning
      annotations:
        summary: "Maintenance exclusion expiring soon"
        description: "Maintenance exclusion {{ $labels.exclusion_name }} expires in less than 7 days."
```

## Key Configuration Points:

1. **Maintenance Windows**: Set to 3 AM daily (adjust timezone as needed)
2. **June Exclusions**: June 1-30 (full month for quarterly freeze)
3. **November Exclusions**: Nov 20 - Dec 5 (covers Black Friday/Cyber Monday plus buffer)
4. **Auto-upgrade Disabled**: `auto_upgrade = false` on node pools
5. **Scope**: `ALL_UPGRADES` prevents both node and control plane upgrades
6. **Recurring**: Uses RRULE format for yearly recurrence

## Usage:

1. Apply the Terraform configuration or use gcloud commands
2. Run the management script to add exclusions for upcoming years
3. Monitor for available upgrades using the alerting rules
4. Manually trigger upgrades when appropriate using the script

This configuration ensures you have full control over when upgrades happen while protecting your critical business periods.
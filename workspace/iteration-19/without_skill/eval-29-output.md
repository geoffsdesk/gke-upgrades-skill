Here's the exact configuration for your GKE maintenance exclusions to handle your quarterly freeze, Black Friday period, and automatic upgrade restrictions:

## Complete GKE Cluster Configuration

```yaml
# terraform/gke-cluster.tf
resource "google_container_cluster" "primary" {
  name     = "production-cluster"
  location = "us-central1"
  
  # Remove default node pool
  remove_default_node_pool = true
  initial_node_count       = 1

  # Maintenance policy with exclusions
  maintenance_policy {
    # Maintenance window (outside business hours)
    daily_maintenance_window {
      start_time = "03:00"  # 3 AM in cluster timezone
    }

    # Quarterly code freeze in June
    maintenance_exclusion {
      exclusion_name = "quarterly-code-freeze-june"
      start_time     = "2024-06-01T00:00:00Z"
      end_time       = "2024-06-30T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    # Black Friday/Cyber Monday exclusion
    maintenance_exclusion {
      exclusion_name = "black-friday-cyber-monday"
      start_time     = "2024-11-20T00:00:00Z"
      end_time       = "2024-12-03T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    # 2025 exclusions (add these annually)
    maintenance_exclusion {
      exclusion_name = "quarterly-code-freeze-june-2025"
      start_time     = "2025-06-01T00:00:00Z"
      end_time       = "2025-06-30T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    maintenance_exclusion {
      exclusion_name = "black-friday-cyber-monday-2025"
      start_time     = "2025-11-20T00:00:00Z"
      end_time       = "2025-12-03T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }
  }

  # Disable automatic minor version upgrades
  release_channel {
    channel = "REGULAR"  # or "STABLE" for even more conservative updates
  }

  # Explicit version pinning to prevent auto-upgrades
  min_master_version = "1.28.3-gke.1286000"  # Update this when you want to upgrade
  node_version      = "1.28.3-gke.1286000"   # Keep nodes in sync

  # Enable maintenance notifications
  notification_config {
    pubsub {
      enabled = true
      topic   = google_pubsub_topic.gke_maintenance.id
    }
  }

  # Network configuration
  network    = "default"
  subnetwork = "default"

  # Enable necessary features
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  # IP allocation for pods and services
  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }
}

# Node pool with same maintenance restrictions
resource "google_container_node_pool" "primary_nodes" {
  name       = "primary-node-pool"
  location   = "us-central1"
  cluster    = google_container_cluster.primary.name
  node_count = 1

  # Specify exact node version to prevent auto-upgrades
  version = "1.28.3-gke.1286000"

  # Auto-upgrade disabled for manual control
  management {
    auto_repair  = true
    auto_upgrade = false  # Disable automatic upgrades
  }

  node_config {
    preemptible  = false
    machine_type = "e2-medium"

    service_account = google_service_account.gke_nodes.email
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]

    labels = {
      environment = "production"
    }

    tags = ["gke-node", "production"]
  }

  # Upgrade settings
  upgrade_settings {
    strategy         = "SURGE"
    max_surge        = 1
    max_unavailable  = 0
  }
}
```

## Notification Setup for Maintenance Events

```yaml
# terraform/maintenance-notifications.tf

# Pub/Sub topic for maintenance notifications
resource "google_pubsub_topic" "gke_maintenance" {
  name = "gke-maintenance-notifications"
}

# Subscription for maintenance alerts
resource "google_pubsub_subscription" "gke_maintenance_sub" {
  name  = "gke-maintenance-subscription"
  topic = google_pubsub_topic.gke_maintenance.name

  # Message retention
  message_retention_duration = "604800s"  # 7 days

  # Push to webhook or use pull for processing
  push_config {
    push_endpoint = "https://your-webhook-endpoint.com/gke-maintenance"
  }
}

# Service account for GKE nodes
resource "google_service_account" "gke_nodes" {
  account_id   = "gke-nodes-sa"
  display_name = "GKE Nodes Service Account"
}

# IAM bindings for the service account
resource "google_project_iam_member" "gke_nodes_logging" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

resource "google_project_iam_member" "gke_nodes_monitoring" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}
```

## Manual Upgrade Script

```bash
#!/bin/bash
# scripts/upgrade-gke.sh

set -e

CLUSTER_NAME="production-cluster"
ZONE="us-central1"
PROJECT_ID="your-project-id"

# Function to upgrade cluster
upgrade_cluster() {
    local new_version=$1
    
    echo "Starting GKE cluster upgrade to version: $new_version"
    
    # Upgrade master first
    echo "Upgrading master..."
    gcloud container clusters upgrade $CLUSTER_NAME \
        --zone=$ZONE \
        --project=$PROJECT_ID \
        --master \
        --cluster-version=$new_version \
        --quiet
    
    # Wait for master upgrade to complete
    echo "Waiting for master upgrade to complete..."
    while true; do
        status=$(gcloud container clusters describe $CLUSTER_NAME \
                --zone=$ZONE \
                --project=$PROJECT_ID \
                --format="value(status)")
        
        if [ "$status" = "RUNNING" ]; then
            echo "Master upgrade completed"
            break
        fi
        
        echo "Master status: $status, waiting..."
        sleep 30
    done
    
    # Upgrade node pools
    echo "Upgrading node pools..."
    gcloud container clusters upgrade $CLUSTER_NAME \
        --zone=$ZONE \
        --project=$PROJECT_ID \
        --node-pool=primary-node-pool \
        --cluster-version=$new_version \
        --quiet
    
    echo "Cluster upgrade completed successfully!"
}

# Check current version
echo "Current cluster version:"
gcloud container clusters describe $CLUSTER_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --format="value(currentMasterVersion)"

# Upgrade to specified version
if [ $# -eq 0 ]; then
    echo "Usage: $0 <new-version>"
    echo "Example: $0 1.28.5-gke.1300000"
    exit 1
fi

NEW_VERSION=$1
upgrade_cluster $NEW_VERSION
```

## Monitoring and Alerting

```yaml
# terraform/monitoring.tf

# Alert policy for maintenance windows
resource "google_monitoring_alert_policy" "gke_maintenance_alert" {
  display_name = "GKE Maintenance Window Alert"
  combiner     = "OR"

  conditions {
    display_name = "GKE Maintenance Event"
    
    condition_matched_log {
      filter = <<-EOT
        resource.type="gke_cluster"
        protoPayload.methodName="google.container.v1.ClusterManager.UpdateCluster"
        OR protoPayload.methodName="google.container.v1.ClusterManager.UpdateNodePool"
      EOT
      
      label_extractors = {
        "cluster_name" = "EXTRACT(resource.labels.cluster_name)"
        "location"     = "EXTRACT(resource.labels.location)"
      }
    }
  }

  notification_channels = [
    google_monitoring_notification_channel.email.name,
    google_monitoring_notification_channel.slack.name
  ]

  alert_strategy {
    notification_rate_limit {
      period = "300s"
    }
    auto_close = "1800s"
  }
}

# Email notification channel
resource "google_monitoring_notification_channel" "email" {
  display_name = "Email Notification"
  type         = "email"
  
  labels = {
    email_address = "devops-team@yourcompany.com"
  }
}

# Slack notification channel (configure webhook in Slack first)
resource "google_monitoring_notification_channel" "slack" {
  display_name = "Slack Notification"
  type         = "slack"
  
  labels = {
    channel_name = "#infrastructure-alerts"
    url          = "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK"
  }
}
```

## Annual Maintenance Schedule Script

```bash
#!/bin/bash
# scripts/update-maintenance-exclusions.sh

# Update maintenance exclusions for the next year
CURRENT_YEAR=$(date +%Y)
NEXT_YEAR=$((CURRENT_YEAR + 1))

echo "Updating maintenance exclusions for year: $NEXT_YEAR"

# Update Terraform variables or apply new exclusions
cat > terraform/maintenance-exclusions-${NEXT_YEAR}.tf << EOF
# Maintenance exclusions for ${NEXT_YEAR}
resource "google_container_cluster" "primary" {
  # ... existing configuration ...
  
  maintenance_policy {
    daily_maintenance_window {
      start_time = "03:00"
    }
    
    maintenance_exclusion {
      exclusion_name = "quarterly-code-freeze-june-${NEXT_YEAR}"
      start_time     = "${NEXT_YEAR}-06-01T00:00:00Z"
      end_time       = "${NEXT_YEAR}-06-30T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    maintenance_exclusion {
      exclusion_name = "black-friday-cyber-monday-${NEXT_YEAR}"
      start_time     = "${NEXT_YEAR}-11-20T00:00:00Z"
      end_time       = "${NEXT_YEAR}-12-03T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }
  }
}
EOF

echo "Maintenance exclusions updated for $NEXT_YEAR"
echo "Run 'terraform plan' and 'terraform apply' to update the cluster"
```

## Key Configuration Points:

1. **Maintenance Exclusions**: Complete blocks for June (quarterly freeze) and November/December (Black Friday period)
2. **Auto-upgrade Prevention**: `auto_upgrade = false` on node pools and explicit version pinning
3. **Release Channel**: Set to `REGULAR` or `STABLE` for controlled updates
4. **Manual Control**: Upgrade script for explicit version management
5. **Monitoring**: Full alerting setup for maintenance events
6. **Annual Updates**: Script to generate next year's exclusions

**Important Notes:**
- Update the `min_master_version` and `node_version` when you want to upgrade
- Add new yearly exclusions annually using the provided script
- Test upgrades in staging environments first
- Monitor the notification channels during maintenance windows

This configuration gives you complete control over when and how your GKE clusters are upgraded while protecting your critical business periods.
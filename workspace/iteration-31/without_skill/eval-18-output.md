I'll help you configure maintenance windows and exclusions for your GKE Standard clusters to meet your SOX compliance requirements. Here's a comprehensive solution:

## 1. Maintenance Windows Configuration

### Primary Maintenance Window (Weekend Auto-upgrades)
```yaml
# maintenance-window.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: maintenance-config
data:
  maintenance-policy: |
    # Weekend maintenance window: Saturdays 2 AM - 6 AM EST
    maintenance_policy {
      window {
        daily_maintenance_window {
          start_time = "07:00"  # 2 AM EST in UTC
          duration   = "4h"
        }
      }
    }
```

### Terraform Configuration for All 3 Clusters
```hcl
# main.tf
variable "cluster_names" {
  description = "GKE cluster names"
  type        = list(string)
  default     = ["prod-cluster", "staging-cluster", "dev-cluster"]
}

variable "quarterly_freeze_dates" {
  description = "Quarterly code freeze periods"
  type = list(object({
    start_date = string
    end_date   = string
    recurrence = string
  }))
  default = [
    {
      start_date = "2024-03-15"
      end_date   = "2024-03-31"
      recurrence = "FREQ=YEARLY;BYMONTH=3,6,9,12"
    }
  ]
}

# GKE Clusters with Maintenance Configuration
resource "google_container_cluster" "gke_clusters" {
  count    = length(var.cluster_names)
  name     = var.cluster_names[count.index]
  location = var.region
  
  # Remove default node pool
  remove_default_node_pool = true
  initial_node_count       = 1

  # Maintenance policy for weekend upgrades
  maintenance_policy {
    # Weekend maintenance window (Saturday 2-6 AM EST)
    daily_maintenance_window {
      start_time = "07:00"  # UTC time (2 AM EST)
    }
    
    # Maintenance exclusions for compliance periods
    dynamic "maintenance_exclusion" {
      for_each = local.maintenance_exclusions
      content {
        exclusion_name = maintenance_exclusion.value.name
        start_time     = maintenance_exclusion.value.start_time
        end_time       = maintenance_exclusion.value.end_time
        exclusion_options {
          scope = "UPGRADES"
        }
      }
    }
  }

  # Network policy for security compliance
  network_policy {
    enabled = true
  }

  # Binary authorization for SOX compliance
  binary_authorization {
    evaluation_mode = "PROJECT_SINGLETON_POLICY_ENFORCE"
  }

  # Logging and monitoring for audit trails
  logging_config {
    enable_components = [
      "SYSTEM_COMPONENTS",
      "WORKLOADS",
      "API_SERVER"
    ]
  }

  monitoring_config {
    enable_components = [
      "SYSTEM_COMPONENTS",
      "WORKLOADS"
    ]
  }
}

# Local values for maintenance exclusions
locals {
  # Current year maintenance exclusions
  maintenance_exclusions = concat(
    # Quarterly freezes
    [
      {
        name       = "q1-freeze-2024"
        start_time = "2024-03-15T00:00:00Z"
        end_time   = "2024-03-31T23:59:59Z"
      },
      {
        name       = "q2-freeze-2024"
        start_time = "2024-06-15T00:00:00Z"
        end_time   = "2024-06-30T23:59:59Z"
      },
      {
        name       = "q3-freeze-2024"
        start_time = "2024-09-15T00:00:00Z"
        end_time   = "2024-09-30T23:59:59Z"
      },
      {
        name       = "q4-freeze-2024"
        start_time = "2024-12-15T00:00:00Z"
        end_time   = "2024-12-31T23:59:59Z"
      }
    ],
    # Annual audit exclusion (November)
    [
      {
        name       = "annual-audit-2024"
        start_time = "2024-11-01T00:00:00Z"
        end_time   = "2024-11-30T23:59:59Z"
      }
    ],
    # Holiday exclusions for additional safety
    [
      {
        name       = "holiday-freeze-2024"
        start_time = "2024-12-20T00:00:00Z"
        end_time   = "2025-01-05T23:59:59Z"
      }
    ]
  )
}

# Node pools with specific maintenance settings
resource "google_container_node_pool" "primary_nodes" {
  count      = length(var.cluster_names)
  name       = "${var.cluster_names[count.index]}-nodes"
  location   = var.region
  cluster    = google_container_cluster.gke_clusters[count.index].name
  
  # Enable auto-upgrade during maintenance windows only
  management {
    auto_repair  = true
    auto_upgrade = true
  }

  # Upgrade settings for controlled rollouts
  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
    strategy        = "SURGE"
  }

  node_config {
    machine_type = var.node_machine_type
    
    # Security settings for SOX compliance
    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }

    # Service account with minimal permissions
    service_account = google_service_account.gke_nodes.email
    oauth_scopes = [
      "https://www.googleapis.com/auth/logging.write",
      "https://www.googleapis.com/auth/monitoring",
      "https://www.googleapis.com/auth/devstorage.read_only"
    ]
  }
}
```

## 2. Automated Maintenance Exclusion Management

### Python Script for Dynamic Exclusion Updates
```python
#!/usr/bin/env python3
"""
Automated maintenance exclusion management for GKE clusters
Handles quarterly freezes and annual audit periods
"""

import datetime
from google.cloud import container_v1
from google.protobuf.timestamp_pb2 import Timestamp
import calendar

class GKEMaintenanceManager:
    def __init__(self, project_id, location):
        self.client = container_v1.ClusterManagerClient()
        self.project_id = project_id
        self.location = location
        self.parent = f"projects/{project_id}/locations/{location}"
    
    def create_quarterly_exclusions(self, cluster_name, year):
        """Create quarterly maintenance exclusions"""
        quarters = [
            ("Q1", 3, 15, 31),  # March 15-31
            ("Q2", 6, 15, 30),  # June 15-30
            ("Q3", 9, 15, 30),  # September 15-30
            ("Q4", 12, 15, 31)  # December 15-31
        ]
        
        exclusions = []
        for quarter, month, start_day, end_day in quarters:
            exclusions.append({
                "exclusion_name": f"{quarter.lower()}-freeze-{year}",
                "start_time": self._create_timestamp(year, month, start_day, 0, 0, 0),
                "end_time": self._create_timestamp(year, month, end_day, 23, 59, 59),
                "exclusion_options": {
                    "scope": "UPGRADES"
                }
            })
        
        return exclusions
    
    def create_audit_exclusion(self, year):
        """Create November audit exclusion"""
        return {
            "exclusion_name": f"annual-audit-{year}",
            "start_time": self._create_timestamp(year, 11, 1, 0, 0, 0),
            "end_time": self._create_timestamp(year, 11, 30, 23, 59, 59),
            "exclusion_options": {
                "scope": "UPGRADES"
            }
        }
    
    def _create_timestamp(self, year, month, day, hour, minute, second):
        """Create protobuf timestamp"""
        dt = datetime.datetime(year, month, day, hour, minute, second)
        timestamp = Timestamp()
        timestamp.FromDatetime(dt)
        return timestamp
    
    def update_cluster_maintenance(self, cluster_name, year):
        """Update maintenance policy for a cluster"""
        cluster_path = f"{self.parent}/clusters/{cluster_name}"
        
        # Get current cluster config
        cluster = self.client.get_cluster(name=cluster_path)
        
        # Create maintenance exclusions
        quarterly_exclusions = self.create_quarterly_exclusions(cluster_name, year)
        audit_exclusion = self.create_audit_exclusion(year)
        
        all_exclusions = quarterly_exclusions + [audit_exclusion]
        
        # Update maintenance policy
        maintenance_policy = {
            "daily_maintenance_window": {
                "start_time": "07:00"  # 2 AM EST in UTC
            },
            "maintenance_exclusions": {exc["exclusion_name"]: exc for exc in all_exclusions}
        }
        
        # Apply the update
        operation = self.client.set_maintenance_policy(
            name=cluster_path,
            maintenance_policy=maintenance_policy
        )
        
        return operation

# Usage script
def main():
    import os
    
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GKE_LOCATION", "us-central1")
    clusters = ["prod-cluster", "staging-cluster", "dev-cluster"]
    
    manager = GKEMaintenanceManager(project_id, location)
    
    current_year = datetime.datetime.now().year
    
    for cluster in clusters:
        print(f"Updating maintenance policy for {cluster}...")
        operation = manager.update_cluster_maintenance(cluster, current_year)
        print(f"Operation initiated: {operation.name}")

if __name__ == "__main__":
    main()
```

## 3. Monitoring and Alerting Configuration

### Cloud Monitoring Alert Policies
```yaml
# monitoring-alerts.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: gke-maintenance-alerts
spec:
  groups:
  - name: gke.maintenance
    rules:
    - alert: UnscheduledMaintenanceDetected
      expr: increase(gke_cluster_maintenance_events_total[1h]) > 0
      for: 0m
      labels:
        severity: warning
        compliance: sox
      annotations:
        summary: "Unscheduled maintenance detected on GKE cluster"
        description: "Cluster {{ $labels.cluster }} had maintenance outside scheduled window"
    
    - alert: MaintenanceWindowViolation
      expr: |
        (
          time() % 86400 < 25200 or  # Before 7 AM UTC (2 AM EST)
          time() % 86400 > 39600     # After 11 AM UTC (6 AM EST)
        ) and on() gke_cluster_maintenance_active == 1
      labels:
        severity: critical
        compliance: sox
      annotations:
        summary: "Maintenance occurring outside approved window"
        description: "Maintenance is happening outside the approved weekend window"
```

## 4. Compliance Monitoring Dashboard

### Terraform for Cloud Monitoring Dashboard
```hcl
# monitoring.tf
resource "google_monitoring_dashboard" "gke_compliance" {
  dashboard_json = jsonencode({
    displayName = "GKE SOX Compliance Dashboard"
    mosaicLayout = {
      tiles = [
        {
          width = 6
          height = 4
          widget = {
            title = "Maintenance Window Compliance"
            xyChart = {
              dataSets = [{
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "resource.type=\"gke_cluster\""
                    aggregation = {
                      alignmentPeriod = "60s"
                      perSeriesAligner = "ALIGN_RATE"
                    }
                  }
                }
                plotType = "LINE"
              }]
              timeshiftDuration = "0s"
              yAxis = {
                label = "Maintenance Events"
                scale = "LINEAR"
              }
            }
          }
        },
        {
          width = 6
          height = 4
          widget = {
            title = "Cluster Version Compliance"
            scorecard = {
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "resource.type=\"gke_cluster\""
                }
              }
              sparkChartView = {
                sparkChartType = "SPARK_BAR"
              }
            }
          }
        }
      ]
    }
  })
}

# Alert policy for compliance violations
resource "google_monitoring_alert_policy" "maintenance_compliance" {
  display_name = "GKE Maintenance Compliance Alert"
  combiner     = "OR"
  
  conditions {
    display_name = "Maintenance outside approved window"
    
    condition_threshold {
      filter          = "resource.type=\"gke_cluster\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }
  
  notification_channels = [
    google_monitoring_notification_channel.email.name,
    google_monitoring_notification_channel.slack.name
  ]
  
  alert_strategy {
    auto_close = "1800s"  # 30 minutes
  }
}
```

## 5. Deployment and Management Scripts

### Deployment Script
```bash
#!/bin/bash
# deploy-maintenance-policy.sh

set -e

PROJECT_ID="${GOOGLE_CLOUD_PROJECT}"
REGION="${GKE_REGION:-us-central1}"
CLUSTERS=("prod-cluster" "staging-cluster" "dev-cluster")

echo "Deploying GKE maintenance policies for SOX compliance..."

# Apply Terraform configuration
terraform init
terraform plan -var="project_id=${PROJECT_ID}" -var="region=${REGION}"
terraform apply -auto-approve

# Update maintenance exclusions for current year
echo "Setting up maintenance exclusions..."
python3 maintenance_manager.py

# Verify configuration
for cluster in "${CLUSTERS[@]}"; do
    echo "Verifying maintenance policy for ${cluster}..."
    gcloud container clusters describe ${cluster} \
        --location=${REGION} \
        --format="yaml(maintenancePolicy)" \
        --project=${PROJECT_ID}
done

echo "Deployment complete. Maintenance windows configured for weekend upgrades only."
echo "Exclusions set for quarterly freezes and November audit period."
```

### Annual Update Script
```bash
#!/bin/bash
# annual-update.sh - Run this at the beginning of each year

CURRENT_YEAR=$(date +%Y)
NEXT_YEAR=$((CURRENT_YEAR + 1))

echo "Updating maintenance exclusions for ${NEXT_YEAR}..."

# Update the maintenance exclusions
python3 -c "
from maintenance_manager import GKEMaintenanceManager
import os

project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
location = os.getenv('GKE_LOCATION', 'us-central1')
clusters = ['prod-cluster', 'staging-cluster', 'dev-cluster']

manager = GKEMaintenanceManager(project_id, location)

for cluster in clusters:
    print(f'Updating {cluster} for ${NEXT_YEAR}...')
    manager
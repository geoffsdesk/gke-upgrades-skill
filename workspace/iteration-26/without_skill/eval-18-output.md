I'll help you configure maintenance windows and exclusions for your GKE clusters to meet SOX compliance requirements. Here's a comprehensive setup:

## 1. Terraform Configuration for Maintenance Windows

```hcl
# variables.tf
variable "clusters" {
  description = "List of cluster configurations"
  type = map(object({
    name               = string
    location          = string
    node_locations    = list(string)
    initial_node_count = number
  }))
  default = {
    prod = {
      name               = "prod-cluster"
      location          = "us-central1-a"
      node_locations    = ["us-central1-b", "us-central1-c"]
      initial_node_count = 1
    }
    staging = {
      name               = "staging-cluster"
      location          = "us-central1-a"
      node_locations    = ["us-central1-b"]
      initial_node_count = 1
    }
    dev = {
      name               = "dev-cluster"
      location          = "us-central1-a"
      node_locations    = []
      initial_node_count = 1
    }
  }
}

# Current year for dynamic exclusion windows
locals {
  current_year = formatdate("YYYY", timestamp())
  next_year    = tostring(tonumber(local.current_year) + 1)
  
  # Define quarterly code freeze periods
  quarterly_freezes = [
    {
      name       = "Q1-freeze-${local.current_year}"
      start_time = "${local.current_year}-03-15T00:00:00Z"
      end_time   = "${local.current_year}-03-31T23:59:59Z"
      scope      = "NO_UPGRADES"
    },
    {
      name       = "Q2-freeze-${local.current_year}"
      start_time = "${local.current_year}-06-15T00:00:00Z"
      end_time   = "${local.current_year}-06-30T23:59:59Z"
      scope      = "NO_UPGRADES"
    },
    {
      name       = "Q3-freeze-${local.current_year}"
      start_time = "${local.current_year}-09-15T00:00:00Z"
      end_time   = "${local.current_year}-09-30T23:59:59Z"
      scope      = "NO_UPGRADES"
    },
    {
      name       = "Q4-freeze-${local.current_year}"
      start_time = "${local.current_year}-12-15T00:00:00Z"
      end_time   = "${local.current_year}-12-31T23:59:59Z"
      scope      = "NO_UPGRADES"
    }
  ]
  
  # Annual audit exclusion (entire November)
  annual_audit = {
    name       = "annual-audit-${local.current_year}"
    start_time = "${local.current_year}-11-01T00:00:00Z"
    end_time   = "${local.current_year}-11-30T23:59:59Z"
    scope      = "NO_UPGRADES"
  }
}

# main.tf
resource "google_container_cluster" "clusters" {
  for_each = var.clusters
  
  name               = each.value.name
  location           = each.value.location
  node_locations     = each.value.node_locations
  initial_node_count = each.value.initial_node_count
  
  # Remove default node pool
  remove_default_node_pool = true
  
  # Network configuration
  network    = "default"
  subnetwork = "default"
  
  # Enable maintenance policy
  maintenance_policy {
    # Weekend-only maintenance window (Saturday 2 AM - 6 AM UTC)
    daily_maintenance_window {
      start_time = "02:00"  # 2 AM UTC
    }
    
    # Recurring maintenance window for weekends only
    recurring_window {
      start_time = "2024-01-06T02:00:00Z"  # First Saturday of 2024
      end_time   = "2024-01-06T06:00:00Z"  # 4-hour window
      recurrence = "FREQ=WEEKLY;BYDAY=SA"  # Every Saturday
    }
    
    # Quarterly code freeze exclusions
    dynamic "maintenance_exclusion" {
      for_each = local.quarterly_freezes
      content {
        exclusion_name = maintenance_exclusion.value.name
        start_time     = maintenance_exclusion.value.start_time
        end_time       = maintenance_exclusion.value.end_time
        exclusion_options {
          scope = maintenance_exclusion.value.scope
        }
      }
    }
    
    # Annual audit exclusion
    maintenance_exclusion {
      exclusion_name = local.annual_audit.name
      start_time     = local.annual_audit.start_time
      end_time       = local.annual_audit.end_time
      exclusion_options {
        scope = local.annual_audit.scope
      }
    }
  }
  
  # Cluster-level configurations for SOX compliance
  master_auth {
    client_certificate_config {
      issue_client_certificate = false
    }
  }
  
  # Enable network policy for security
  network_policy {
    enabled  = true
    provider = "CALICO"
  }
  
  addons_config {
    network_policy_config {
      disabled = false
    }
    
    # Enable audit logging for compliance
    gce_persistent_disk_csi_driver_config {
      enabled = true
    }
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
  
  # Binary authorization for SOX compliance
  binary_authorization {
    evaluation_mode = "PROJECT_SINGLETON_POLICY_ENFORCE"
  }
  
  lifecycle {
    ignore_changes = [
      maintenance_policy[0].maintenance_exclusion
    ]
  }
}

# Managed node pools with maintenance windows
resource "google_container_node_pool" "primary_nodes" {
  for_each   = var.clusters
  name       = "${each.value.name}-node-pool"
  location   = each.value.location
  cluster    = google_container_cluster.clusters[each.key].name
  node_count = each.value.initial_node_count
  
  management {
    auto_repair  = true
    auto_upgrade = true
  }
  
  upgrade_settings {
    strategy        = "SURGE"
    max_surge       = 1
    max_unavailable = 0
  }
  
  node_config {
    preemptible  = each.key == "dev" ? true : false
    machine_type = each.key == "prod" ? "e2-standard-4" : "e2-standard-2"
    
    # Security configurations for SOX compliance
    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }
    
    oauth_scopes = [
      "https://www.googleapis.com/auth/logging.write",
      "https://www.googleapis.com/auth/monitoring",
      "https://www.googleapis.com/auth/devstorage.read_only"
    ]
    
    labels = {
      environment = each.key
      compliance  = "sox"
    }
    
    tags = ["gke-node", "${each.key}-env"]
  }
}
```

## 2. gcloud Commands for Manual Configuration

```bash
#!/bin/bash
# configure-maintenance.sh

# Variables
PROJECT_ID="your-project-id"
CLUSTERS=("prod-cluster" "staging-cluster" "dev-cluster")
LOCATION="us-central1-a"
CURRENT_YEAR=$(date +%Y)

# Function to configure maintenance window for a cluster
configure_maintenance() {
    local cluster_name=$1
    echo "Configuring maintenance window for $cluster_name..."
    
    # Set recurring maintenance window (Saturdays 2-6 AM UTC)
    gcloud container clusters update $cluster_name \
        --location=$LOCATION \
        --maintenance-window-start="2024-01-06T02:00:00Z" \
        --maintenance-window-end="2024-01-06T06:00:00Z" \
        --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SA" \
        --project=$PROJECT_ID
}

# Function to add quarterly exclusions
add_quarterly_exclusions() {
    local cluster_name=$1
    echo "Adding quarterly exclusions for $cluster_name..."
    
    # Q1 Freeze (March 15-31)
    gcloud container clusters update $cluster_name \
        --location=$LOCATION \
        --add-maintenance-exclusion-name="q1-freeze-$CURRENT_YEAR" \
        --add-maintenance-exclusion-start="${CURRENT_YEAR}-03-15T00:00:00Z" \
        --add-maintenance-exclusion-end="${CURRENT_YEAR}-03-31T23:59:59Z" \
        --add-maintenance-exclusion-scope="NO_UPGRADES" \
        --project=$PROJECT_ID
    
    # Q2 Freeze (June 15-30)
    gcloud container clusters update $cluster_name \
        --location=$LOCATION \
        --add-maintenance-exclusion-name="q2-freeze-$CURRENT_YEAR" \
        --add-maintenance-exclusion-start="${CURRENT_YEAR}-06-15T00:00:00Z" \
        --add-maintenance-exclusion-end="${CURRENT_YEAR}-06-30T23:59:59Z" \
        --add-maintenance-exclusion-scope="NO_UPGRADES" \
        --project=$PROJECT_ID
    
    # Q3 Freeze (September 15-30)
    gcloud container clusters update $cluster_name \
        --location=$LOCATION \
        --add-maintenance-exclusion-name="q3-freeze-$CURRENT_YEAR" \
        --add-maintenance-exclusion-start="${CURRENT_YEAR}-09-15T00:00:00Z" \
        --add-maintenance-exclusion-end="${CURRENT_YEAR}-09-30T23:59:59Z" \
        --add-maintenance-exclusion-scope="NO_UPGRADES" \
        --project=$PROJECT_ID
    
    # Q4 Freeze (December 15-31)
    gcloud container clusters update $cluster_name \
        --location=$LOCATION \
        --add-maintenance-exclusion-name="q4-freeze-$CURRENT_YEAR" \
        --add-maintenance-exclusion-start="${CURRENT_YEAR}-12-15T00:00:00Z" \
        --add-maintenance-exclusion-end="${CURRENT_YEAR}-12-31T23:59:59Z" \
        --add-maintenance-exclusion-scope="NO_UPGRADES" \
        --project=$PROJECT_ID
    
    # Annual Audit (November 1-30)
    gcloud container clusters update $cluster_name \
        --location=$LOCATION \
        --add-maintenance-exclusion-name="annual-audit-$CURRENT_YEAR" \
        --add-maintenance-exclusion-start="${CURRENT_YEAR}-11-01T00:00:00Z" \
        --add-maintenance-exclusion-end="${CURRENT_YEAR}-11-30T23:59:59Z" \
        --add-maintenance-exclusion-scope="NO_UPGRADES" \
        --project=$PROJECT_ID
}

# Configure all clusters
for cluster in "${CLUSTERS[@]}"; do
    configure_maintenance $cluster
    add_quarterly_exclusions $cluster
    echo "Configuration complete for $cluster"
    echo "---"
done

echo "All clusters configured successfully!"
```

## 3. Monitoring and Alerting Configuration

```yaml
# monitoring-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: maintenance-alerts
  namespace: kube-system
data:
  alert-policy.json: |
    {
      "displayName": "GKE Maintenance Window Violations",
      "conditions": [
        {
          "displayName": "Unexpected cluster upgrade",
          "conditionThreshold": {
            "filter": "resource.type=\"gke_cluster\" AND protoPayload.methodName=\"google.container.v1.ClusterManager.UpdateCluster\"",
            "comparison": "COMPARISON_GREATER_THAN",
            "thresholdValue": 0,
            "duration": "60s"
          }
        }
      ],
      "alertStrategy": {
        "autoClose": "1800s"
      },
      "notificationChannels": ["projects/PROJECT_ID/notificationChannels/CHANNEL_ID"]
    }
```

## 4. Annual Maintenance Calendar Script

```python
# maintenance_calendar.py
#!/usr/bin/env python3

import datetime
import json
from typing import List, Dict

class MaintenanceCalendar:
    def __init__(self, year: int):
        self.year = year
        
    def get_quarterly_freezes(self) -> List[Dict]:
        """Generate quarterly code freeze periods"""
        freezes = []
        quarters = [
            {"name": "Q1", "start": (3, 15), "end": (3, 31)},
            {"name": "Q2", "start": (6, 15), "end": (6, 30)},
            {"name": "Q3", "start": (9, 15), "end": (9, 30)},
            {"name": "Q4", "start": (12, 15), "end": (12, 31)}
        ]
        
        for quarter in quarters:
            start_date = datetime.datetime(self.year, quarter["start"][0], quarter["start"][1])
            end_date = datetime.datetime(self.year, quarter["end"][0], quarter["end"][1], 23, 59, 59)
            
            freezes.append({
                "name": f"{quarter['name']}-freeze-{self.year}",
                "start_time": start_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end_time": end_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "scope": "NO_UPGRADES",
                "description": f"{quarter['name']} quarterly code freeze"
            })
            
        return freezes
    
    def get_annual_audit(self) -> Dict:
        """Generate annual audit exclusion for November"""
        start_date = datetime.datetime(self.year, 11, 1)
        end_date = datetime.datetime(self.year, 11, 30, 23, 59, 59)
        
        return {
            "name": f"annual-audit-{self.year}",
            "start_time": start_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end_time": end_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "scope": "NO_UPGRADES",
            "description": "Annual SOX compliance audit period"
        }
    
    def get_weekend_maintenance_windows(self) -> List[Dict]:
        """Generate weekend maintenance windows for the year"""
        windows = []
        # Start with first Saturday of the year
        current_date = datetime.datetime(self.year, 1, 1)
        
        # Find first Saturday
        while current_date.weekday() != 5:  # 5 = Saturday
            current_date += datetime.timedelta(days=1)
        
        # Generate weekly Saturday windows
        while current_date.year == self.year:
            start_time = current_date.replace(hour=2, minute=0, second=0)  # 2 AM
            end_time = current_date.replace(hour=6, minute=0, second=0)    #
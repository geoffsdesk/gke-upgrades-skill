I'll help you configure maintenance windows and exclusions for your GKE Standard clusters to meet your SOX compliance requirements. Here's a comprehensive setup:

## 1. Terraform Configuration for Maintenance Windows

```hcl
# variables.tf
variable "cluster_configs" {
  description = "Configuration for GKE clusters"
  type = map(object({
    name     = string
    location = string
    region   = string
  }))
  default = {
    prod = {
      name     = "prod-cluster"
      location = "us-central1-a"
      region   = "us-central1"
    }
    staging = {
      name     = "staging-cluster"
      location = "us-central1-b"
      region   = "us-central1"
    }
    dev = {
      name     = "dev-cluster"
      location = "us-central1-c"
      region   = "us-central1"
    }
  }
}

variable "quarterly_freeze_dates" {
  description = "Quarterly code freeze periods"
  type = list(object({
    start_date = string
    end_date   = string
  }))
  default = [
    {
      start_date = "2024-03-15"
      end_date   = "2024-03-31"
    },
    {
      start_date = "2024-06-15"
      end_date   = "2024-06-30"
    },
    {
      start_date = "2024-09-15"
      end_date   = "2024-09-30"
    },
    {
      start_date = "2024-12-15"
      end_date   = "2024-12-31"
    }
  ]
}
```

```hcl
# main.tf
resource "google_container_cluster" "clusters" {
  for_each = var.cluster_configs
  
  name     = each.value.name
  location = each.value.location
  
  # Remove default node pool
  remove_default_node_pool = true
  initial_node_count       = 1
  
  # Maintenance policy with weekend-only windows
  maintenance_policy {
    # Daily maintenance window on weekends only
    daily_maintenance_window {
      start_time = "03:00"  # 3 AM local time
    }
    
    # Maintenance exclusions
    dynamic "maintenance_exclusion" {
      for_each = var.quarterly_freeze_dates
      content {
        exclusion_name = "quarterly-freeze-${formatdate("YYYY-MM", maintenance_exclusion.value.start_date)}"
        start_time     = "${maintenance_exclusion.value.start_date}T00:00:00Z"
        end_time       = "${maintenance_exclusion.value.end_date}T23:59:59Z"
        
        exclusion_options {
          scope = "UPGRADES"
        }
      }
    }
    
    # Annual audit exclusion (November)
    maintenance_exclusion {
      exclusion_name = "annual-audit-november"
      start_time     = "2024-11-01T00:00:00Z"
      end_time       = "2024-11-30T23:59:59Z"
      
      exclusion_options {
        scope = "UPGRADES"
      }
    }
    
    # Holiday exclusions
    maintenance_exclusion {
      exclusion_name = "holiday-thanksgiving"
      start_time     = "2024-11-28T00:00:00Z"
      end_time       = "2024-12-02T23:59:59Z"
      
      exclusion_options {
        scope = "UPGRADES"
      }
    }
    
    maintenance_exclusion {
      exclusion_name = "holiday-christmas-newyear"
      start_time     = "2024-12-20T00:00:00Z"
      end_time       = "2025-01-02T23:59:59Z"
      
      exclusion_options {
        scope = "UPGRADES"
      }
    }
  }
  
  # Release channel for controlled upgrades
  release_channel {
    channel = each.key == "prod" ? "STABLE" : "REGULAR"
  }
  
  # Enable workload identity for security
  workload_identity_config {
    workload_pool = "${data.google_project.current.project_id}.svc.id.goog"
  }
  
  # Network policy for security
  network_policy {
    enabled = true
  }
  
  # Enable private cluster
  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block = "172.16.${each.key == "prod" ? "0" : each.key == "staging" ? "1" : "2"}.0/28"
  }
  
  # IP allocation policy
  ip_allocation_policy {
    cluster_secondary_range_name  = "${each.value.name}-pods"
    services_secondary_range_name = "${each.value.name}-services"
  }
  
  # Enable binary authorization
  enable_binary_authorization = each.key == "prod" ? true : false
  
  # Logging and monitoring
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

# Node pools with weekend-only maintenance
resource "google_container_node_pool" "primary_nodes" {
  for_each = var.cluster_configs
  
  name       = "${each.value.name}-nodes"
  location   = each.value.location
  cluster    = google_container_cluster.clusters[each.key].name
  
  # Node configuration
  node_config {
    preemptible  = false
    machine_type = each.key == "prod" ? "e2-standard-4" : "e2-standard-2"
    
    service_account = google_service_account.gke_nodes[each.key].email
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]
    
    # Security settings
    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }
    
    workload_metadata_config {
      mode = "GKE_METADATA"
    }
  }
  
  # Auto-scaling
  autoscaling {
    min_node_count = each.key == "prod" ? 2 : 1
    max_node_count = each.key == "prod" ? 10 : 5
  }
  
  # Auto-upgrade and auto-repair
  management {
    auto_repair  = true
    auto_upgrade = true
  }
  
  # Upgrade settings
  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
  }
}

# Service accounts for nodes
resource "google_service_account" "gke_nodes" {
  for_each = var.cluster_configs
  
  account_id   = "${each.value.name}-nodes"
  display_name = "GKE ${each.value.name} Node Service Account"
}

# IAM bindings for service accounts
resource "google_project_iam_member" "gke_node_service_account" {
  for_each = var.cluster_configs
  
  project = data.google_project.current.project_id
  role    = "roles/container.nodeServiceAccount"
  member  = "serviceAccount:${google_service_account.gke_nodes[each.key].email}"
}

data "google_project" "current" {}
```

## 2. Advanced Maintenance Window Script

```bash
#!/bin/bash
# maintenance-window-manager.sh

PROJECT_ID="your-project-id"
CLUSTERS=("prod-cluster" "staging-cluster" "dev-cluster")
LOCATIONS=("us-central1-a" "us-central1-b" "us-central1-c")

# Function to set weekend-only maintenance window
set_weekend_maintenance() {
    local cluster_name=$1
    local location=$2
    
    echo "Setting weekend maintenance window for $cluster_name..."
    
    # Create maintenance policy JSON
    cat > maintenance-policy.json <<EOF
{
  "window": {
    "dailyMaintenanceWindow": {
      "startTime": "03:00"
    }
  },
  "resourceVersion": "$(gcloud container clusters describe $cluster_name --location=$location --format='value(resourceVersion)')"
}
EOF
    
    gcloud container clusters update $cluster_name \
        --location=$location \
        --maintenance-window-start="03:00" \
        --maintenance-window-end="06:00" \
        --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SA,SU"
}

# Function to add maintenance exclusions
add_maintenance_exclusions() {
    local cluster_name=$1
    local location=$2
    
    echo "Adding maintenance exclusions for $cluster_name..."
    
    # Quarterly freezes for 2024
    declare -a freeze_periods=(
        "Q1-2024:2024-03-15T00:00:00Z:2024-03-31T23:59:59Z"
        "Q2-2024:2024-06-15T00:00:00Z:2024-06-30T23:59:59Z"
        "Q3-2024:2024-09-15T00:00:00Z:2024-09-30T23:59:59Z"
        "Q4-2024:2024-12-15T00:00:00Z:2024-12-31T23:59:59Z"
    )
    
    for period in "${freeze_periods[@]}"; do
        IFS=':' read -r name start_time end_time <<< "$period"
        
        gcloud container clusters update $cluster_name \
            --location=$location \
            --add-maintenance-exclusion-name="freeze-$name" \
            --add-maintenance-exclusion-start="$start_time" \
            --add-maintenance-exclusion-end="$end_time" \
            --add-maintenance-exclusion-scope="UPGRADES"
    done
    
    # November audit exclusion
    gcloud container clusters update $cluster_name \
        --location=$location \
        --add-maintenance-exclusion-name="annual-audit-nov-2024" \
        --add-maintenance-exclusion-start="2024-11-01T00:00:00Z" \
        --add-maintenance-exclusion-end="2024-11-30T23:59:59Z" \
        --add-maintenance-exclusion-scope="UPGRADES"
}

# Apply to all clusters
for i in "${!CLUSTERS[@]}"; do
    cluster_name="${CLUSTERS[$i]}"
    location="${LOCATIONS[$i]}"
    
    echo "Configuring maintenance for $cluster_name in $location..."
    set_weekend_maintenance "$cluster_name" "$location"
    add_maintenance_exclusions "$cluster_name" "$location"
done

echo "Maintenance windows configured for all clusters."
```

## 3. Kubernetes Maintenance Policy CRD

```yaml
# maintenance-policy.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: maintenance-schedule
  namespace: kube-system
data:
  policy.yaml: |
    maintenanceWindows:
      - name: "weekend-maintenance"
        schedule: "0 3 * * 6,0"  # 3 AM on weekends
        duration: "3h"
        timezone: "America/New_York"
      
    exclusions:
      - name: "quarterly-freeze-q1"
        start: "2024-03-15T00:00:00Z"
        end: "2024-03-31T23:59:59Z"
        reason: "Q1 code freeze"
        
      - name: "quarterly-freeze-q2"
        start: "2024-06-15T00:00:00Z"
        end: "2024-06-30T23:59:59Z"
        reason: "Q2 code freeze"
        
      - name: "quarterly-freeze-q3"
        start: "2024-09-15T00:00:00Z"
        end: "2024-09-30T23:59:59Z"
        reason: "Q3 code freeze"
        
      - name: "quarterly-freeze-q4"
        start: "2024-12-15T00:00:00Z"
        end: "2024-12-31T23:59:59Z"
        reason: "Q4 code freeze"
        
      - name: "annual-audit"
        start: "2024-11-01T00:00:00Z"
        end: "2024-11-30T23:59:59Z"
        reason: "Annual SOX audit"
        
      - name: "holiday-blackout"
        start: "2024-11-28T00:00:00Z"
        end: "2025-01-02T23:59:59Z"
        reason: "Holiday blackout period"
```

## 4. Monitoring and Alerting for Maintenance

```yaml
# monitoring-rules.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: gke-maintenance-monitoring
  namespace: monitoring
spec:
  groups:
  - name: gke.maintenance
    rules:
    - alert: MaintenanceWindowViolation
      expr: |
        (
          hour() < 3 or hour() > 6 or
          (day_of_week() != 0 and day_of_week() != 6)
        ) and on() kube_node_info{kubelet_version!~".*"} != on() kube_node_info{kubelet_version!~".*"} offset 1h
      for: 0m
      labels:
        severity: critical
        compliance: sox
      annotations:
        summary: "GKE maintenance occurred outside approved window"
        description: "Node {{ $labels.node }} was updated outside the approved weekend maintenance window"
        
    - alert: MaintenanceExclusionActive
      expr: |
        (
          (month() == 3 and day() >= 15) or
          (month() == 6 and day() >= 15) or  
          (month() == 9 and day() >= 15) or
          (month() == 11) or
          (month() == 12 and day() >= 15)
        )
      for: 0m
      labels:
        severity: warning
        compliance: sox
      annotations:
        summary: "Maintenance exclusion period active"
        description: "Cluster maintenance is currently blocked due to compliance exclusion period"

    - alert: PendingNodeUpgrades
      expr: |
        count by (cluster) (
          kube_node_info{kubelet_version!="v1.27.3-gke.100"}
        ) > 0
      for: 1h
      labels:
        severity: info
      annotations:
        summary: "Pending node upgrades detected"
        description: "{{ $value }} nodes in cluster {{ $labels.cluster }} have pending upgrades"
```

## 5. Compliance Reporting Script

```python
#!/usr/bin/env python3
# compliance-report.py

import json
import subprocess
from datetime import datetime, timedelta
import pandas as pd

class GKEComplianceReporter:
    def __init__(self, project_id, clusters):
        self.project_id = project_id
        self.clusters = clusters
        
    def get_maintenance_events(self, cluster_name, location, days_back=30):
        """Get maintenance events from Cloud Logging"""
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days_back)
        
        filter_query = f'''
        resource.type="gke_cluster"
        resource.labels.cluster_name="{cluster_name}"
        resource.labels.location="{location}"
        protoPay
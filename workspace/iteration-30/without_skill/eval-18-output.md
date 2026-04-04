I'll help you configure maintenance windows and exclusions for your GKE clusters to meet SOX compliance requirements. Here's a comprehensive solution:

## 1. Terraform Configuration

```hcl
# terraform/maintenance_windows.tf

# Variables for maintenance configuration
variable "clusters" {
  description = "List of cluster configurations"
  type = list(object({
    name     = string
    location = string
    zone     = string
  }))
  default = [
    {
      name     = "prod-cluster-1"
      location = "us-central1"
      zone     = "us-central1-a"
    },
    {
      name     = "prod-cluster-2"
      location = "us-east1"
      zone     = "us-east1-b"
    },
    {
      name     = "prod-cluster-3"
      location = "us-west1"
      zone     = "us-west1-c"
    }
  ]
}

# Current year for dynamic exclusion dates
locals {
  current_year = formatdate("YYYY", timestamp())
  next_year    = tostring(tonumber(local.current_year) + 1)
  
  # Quarterly code freeze periods (adjust dates as needed)
  quarterly_freezes = [
    # Q1 freeze - typically end of March
    {
      start_time = "${local.current_year}-03-25T00:00:00Z"
      end_time   = "${local.current_year}-04-05T23:59:59Z"
      scope      = "NO_UPGRADES"
    },
    # Q2 freeze - typically end of June
    {
      start_time = "${local.current_year}-06-25T00:00:00Z"
      end_time   = "${local.current_year}-07-05T23:59:59Z"
      scope      = "NO_UPGRADES"
    },
    # Q3 freeze - typically end of September
    {
      start_time = "${local.current_year}-09-25T00:00:00Z"
      end_time   = "${local.current_year}-10-05T23:59:59Z"
      scope      = "NO_UPGRADES"
    },
    # Q4 freeze - typically end of December
    {
      start_time = "${local.current_year}-12-20T00:00:00Z"
      end_time   = "${local.next_year}-01-05T23:59:59Z"
      scope      = "NO_UPGRADES"
    },
    # Annual audit period - November
    {
      start_time = "${local.current_year}-11-01T00:00:00Z"
      end_time   = "${local.current_year}-11-30T23:59:59Z"
      scope      = "NO_UPGRADES"
    }
  ]
}

# Configure maintenance windows for each cluster
resource "google_container_cluster" "clusters" {
  count    = length(var.clusters)
  name     = var.clusters[count.index].name
  location = var.clusters[count.index].location

  # Maintenance policy - weekends only (Saturday 2 AM UTC)
  maintenance_policy {
    recurring_window {
      start_time = "2023-01-07T02:00:00Z" # Saturday
      end_time   = "2023-01-07T06:00:00Z" # 4-hour window
      recurrence = "FREQ=WEEKLY;BYDAY=SA"
    }

    # Maintenance exclusions for compliance periods
    dynamic "maintenance_exclusion" {
      for_each = local.quarterly_freezes
      content {
        exclusion_name = "freeze-${formatdate("YYYY-MM-DD", maintenance_exclusion.value.start_time)}"
        start_time     = maintenance_exclusion.value.start_time
        end_time       = maintenance_exclusion.value.end_time
        exclusion_options {
          scope = maintenance_exclusion.value.scope
        }
      }
    }
  }

  # Other cluster configuration...
  initial_node_count = 1
  
  node_config {
    machine_type = "e2-medium"
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]
  }
}
```

## 2. Advanced Maintenance Configuration with Node Pool Considerations

```hcl
# terraform/advanced_maintenance.tf

resource "google_container_node_pool" "primary_nodes" {
  count      = length(var.clusters)
  name       = "${var.clusters[count.index].name}-primary-pool"
  location   = var.clusters[count.index].location
  cluster    = google_container_cluster.clusters[count.index].name
  node_count = 2

  # Node upgrade strategy
  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
    strategy        = "SURGE"
    
    # Blue-green upgrade for critical workloads
    blue_green_settings {
      standard_rollout_policy {
        batch_percentage    = 0.2  # 20% at a time
        batch_node_count    = 1
        batch_soak_duration = "300s" # 5 minutes between batches
      }
      node_pool_soak_duration = "1800s" # 30 minutes final soak
    }
  }

  # Management settings
  management {
    auto_repair  = true
    auto_upgrade = true
  }

  node_config {
    preemptible  = false
    machine_type = "e2-standard-2"

    metadata = {
      disable-legacy-endpoints = "true"
      compliance-env          = "sox"
      maintenance-window      = "weekend-only"
    }

    labels = {
      environment = "production"
      compliance  = "sox"
    }

    oauth_scopes = [
      "https://www.googleapis.com/auth/logging.write",
      "https://www.googleapis.com/auth/monitoring",
      "https://www.googleapis.com/auth/cloud-platform"
    ]
  }
}
```

## 3. Automated Exclusion Management Script

```bash
#!/bin/bash
# scripts/update-maintenance-exclusions.sh

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-your-project-id}"
CLUSTERS=("prod-cluster-1:us-central1" "prod-cluster-2:us-east1" "prod-cluster-3:us-west1")

# Function to add maintenance exclusion
add_exclusion() {
    local cluster_name=$1
    local cluster_location=$2
    local exclusion_name=$3
    local start_time=$4
    local end_time=$5
    local scope=${6:-"NO_UPGRADES"}

    echo "Adding exclusion '$exclusion_name' to cluster $cluster_name"
    
    gcloud container clusters update "$cluster_name" \
        --location="$cluster_location" \
        --project="$PROJECT_ID" \
        --add-maintenance-exclusion-name="$exclusion_name" \
        --add-maintenance-exclusion-start="$start_time" \
        --add-maintenance-exclusion-end="$end_time" \
        --add-maintenance-exclusion-scope="$scope" \
        --quiet

    echo "✓ Exclusion added successfully"
}

# Function to remove expired exclusions
remove_expired_exclusions() {
    local cluster_name=$1
    local cluster_location=$2
    
    echo "Checking for expired exclusions in cluster $cluster_name"
    
    # Get current exclusions
    local exclusions=$(gcloud container clusters describe "$cluster_name" \
        --location="$cluster_location" \
        --project="$PROJECT_ID" \
        --format="value(maintenancePolicy.window.maintenanceExclusions[].name)" 2>/dev/null || echo "")
    
    if [[ -n "$exclusions" ]]; then
        while IFS= read -r exclusion; do
            if [[ -n "$exclusion" ]]; then
                echo "Removing expired exclusion: $exclusion"
                gcloud container clusters update "$cluster_name" \
                    --location="$cluster_location" \
                    --project="$PROJECT_ID" \
                    --remove-maintenance-exclusion-name="$exclusion" \
                    --quiet
            fi
        done <<< "$exclusions"
    fi
}

# Main execution
main() {
    local action=${1:-"add"}
    local current_year=$(date +%Y)
    local next_year=$((current_year + 1))
    
    case $action in
        "add-quarterly")
            for cluster_info in "${CLUSTERS[@]}"; do
                IFS=':' read -r cluster_name cluster_location <<< "$cluster_info"
                
                # Q1 Freeze
                add_exclusion "$cluster_name" "$cluster_location" \
                    "q1-freeze-$current_year" \
                    "${current_year}-03-25T00:00:00Z" \
                    "${current_year}-04-05T23:59:59Z"
                
                # Q2 Freeze
                add_exclusion "$cluster_name" "$cluster_location" \
                    "q2-freeze-$current_year" \
                    "${current_year}-06-25T00:00:00Z" \
                    "${current_year}-07-05T23:59:59Z"
                
                # Q3 Freeze
                add_exclusion "$cluster_name" "$cluster_location" \
                    "q3-freeze-$current_year" \
                    "${current_year}-09-25T00:00:00Z" \
                    "${current_year}-10-05T23:59:59Z"
                
                # Q4 Freeze
                add_exclusion "$cluster_name" "$cluster_location" \
                    "q4-freeze-$current_year" \
                    "${current_year}-12-20T00:00:00Z" \
                    "${next_year}-01-05T23:59:59Z"
                
                # Annual audit
                add_exclusion "$cluster_name" "$cluster_location" \
                    "annual-audit-$current_year" \
                    "${current_year}-11-01T00:00:00Z" \
                    "${current_year}-11-30T23:59:59Z"
            done
            ;;
            
        "add-emergency")
            local start_date=$2
            local end_date=$3
            local reason=$4
            
            if [[ -z "$start_date" || -z "$end_date" || -z "$reason" ]]; then
                echo "Usage: $0 add-emergency START_DATE END_DATE REASON"
                echo "Example: $0 add-emergency 2024-01-15T00:00:00Z 2024-01-20T23:59:59Z 'Critical-incident-response'"
                exit 1
            fi
            
            for cluster_info in "${CLUSTERS[@]}"; do
                IFS=':' read -r cluster_name cluster_location <<< "$cluster_info"
                add_exclusion "$cluster_name" "$cluster_location" \
                    "emergency-$(date +%Y%m%d)-$reason" \
                    "$start_date" \
                    "$end_date"
            done
            ;;
            
        "cleanup")
            for cluster_info in "${CLUSTERS[@]}"; do
                IFS=':' read -r cluster_name cluster_location <<< "$cluster_info"
                remove_expired_exclusions "$cluster_name" "$cluster_location"
            done
            ;;
            
        "status")
            for cluster_info in "${CLUSTERS[@]}"; do
                IFS=':' read -r cluster_name cluster_location <<< "$cluster_info"
                echo "=== Cluster: $cluster_name ==="
                gcloud container clusters describe "$cluster_name" \
                    --location="$cluster_location" \
                    --project="$PROJECT_ID" \
                    --format="table(
                        maintenancePolicy.window.recurringWindow.window.startTime:label='MAINTENANCE_START',
                        maintenancePolicy.window.recurringWindow.window.endTime:label='MAINTENANCE_END',
                        maintenancePolicy.window.recurringWindow.recurrence:label='RECURRENCE'
                    )" 2>/dev/null || echo "No maintenance window configured"
                
                echo "Active Exclusions:"
                gcloud container clusters describe "$cluster_name" \
                    --location="$cluster_location" \
                    --project="$PROJECT_ID" \
                    --format="table(
                        maintenancePolicy.window.maintenanceExclusions[].name:label='NAME',
                        maintenancePolicy.window.maintenanceExclusions[].startTime:label='START',
                        maintenancePolicy.window.maintenanceExclusions[].endTime:label='END'
                    )" 2>/dev/null || echo "No active exclusions"
                echo
            done
            ;;
            
        *)
            echo "Usage: $0 {add-quarterly|add-emergency|cleanup|status}"
            echo "  add-quarterly: Add all quarterly and annual exclusions"
            echo "  add-emergency START END REASON: Add emergency exclusion"
            echo "  cleanup: Remove expired exclusions"
            echo "  status: Show current maintenance windows and exclusions"
            exit 1
            ;;
    esac
}

main "$@"
```

## 4. Compliance Monitoring and Alerting

```yaml
# monitoring/maintenance-alerts.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: maintenance-monitoring
  namespace: monitoring
data:
  alert-rules.yaml: |
    groups:
    - name: gke-maintenance-compliance
      rules:
      - alert: UnauthorizedMaintenanceActivity
        expr: |
          increase(gke_cluster_maintenance_events_total[5m]) > 0
          unless on(cluster_name) 
          (
            (hour() >= 2 and hour() <= 6) and (day_of_week() == 6)
          )
        for: 0m
        labels:
          severity: critical
          compliance: sox
        annotations:
          summary: "GKE maintenance occurred outside approved window"
          description: "Cluster {{ $labels.cluster_name }} had maintenance activity outside the approved weekend window"
          
      - alert: MaintenanceExclusionExpiring
        expr: |
          (gke_maintenance_exclusion_end_time - time()) < (7 * 24 * 3600)
        labels:
          severity: warning
          compliance: sox
        annotations:
          summary: "Maintenance exclusion expiring soon"
          description: "Maintenance exclusion {{ $labels.exclusion_name }} expires in less than 7 days"

      - alert: MissedMaintenanceWindow
        expr: |
          (time() - gke_last_maintenance_time) > (14 * 24 * 3600)
        labels:
          severity: warning
        annotations:
          summary: "Cluster has not had maintenance in 14 days"
          description: "Cluster {{ $labels.cluster_name }} may have pending updates"
```

## 5. Compliance Reporting Script

```python
#!/usr/bin/env python3
# scripts/compliance_report.py

import json
import subprocess
from datetime import datetime, timedelta
import argparse
from typing import List, Dict, Any

class GKEComplianceReporter:
    def __init__(self, project_id: str, clusters: List[Dict[str, str]]):
        self.project_id = project_id
        self.clusters = clusters
    
    def get_cluster_maintenance_info(self, cluster_name: str, location: str) -> Dict[str, Any]:
        """Get maintenance window and exclusion information for a cluster"""
        cmd = [
            'gcloud', 'container', 'clusters', 'describe', cluster_name,
            '--location', location,
            '--project', self.project_id,
            '--format', 'json'
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            print(f"
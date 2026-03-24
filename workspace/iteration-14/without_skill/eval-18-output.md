I'll help you configure maintenance windows and exclusions for your GKE Standard clusters to meet SOX compliance requirements. Here's a comprehensive setup:

## 1. Terraform Configuration for Maintenance Windows

```hcl
# variables.tf
variable "clusters" {
  description = "GKE cluster configurations"
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

# Current year for dynamic exclusions
locals {
  current_year = formatdate("YYYY", timestamp())
  next_year    = tostring(tonumber(local.current_year) + 1)
}

# main.tf
resource "google_container_cluster" "clusters" {
  for_each = var.clusters
  
  name     = each.value.name
  location = each.value.location
  
  # Remove default node pool
  remove_default_node_pool = true
  initial_node_count       = 1
  
  # Maintenance policy for SOX compliance
  maintenance_policy {
    # Weekend-only maintenance window (Saturday 2 AM - 6 AM UTC)
    daily_maintenance_window {
      start_time = "02:00"
    }
    
    # Recurring maintenance window for weekends only
    recurring_window {
      start_time = "${local.current_year}-01-01T02:00:00Z"
      end_time   = "${local.current_year}-01-01T06:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SA"
    }
    
    # Annual audit exclusion (November)
    maintenance_exclusion {
      exclusion_name = "annual-audit-${local.current_year}"
      start_time     = "${local.current_year}-11-01T00:00:00Z"
      end_time       = "${local.current_year}-12-01T00:00:00Z"
      exclusion_options {
        scope = "NO_UPGRADES"
      }
    }
    
    # Q1 Code Freeze (January 15 - February 15)
    maintenance_exclusion {
      exclusion_name = "q1-code-freeze-${local.current_year}"
      start_time     = "${local.current_year}-01-15T00:00:00Z"
      end_time       = "${local.current_year}-02-15T23:59:59Z"
      exclusion_options {
        scope = "NO_UPGRADES"
      }
    }
    
    # Q2 Code Freeze (April 15 - May 15)
    maintenance_exclusion {
      exclusion_name = "q2-code-freeze-${local.current_year}"
      start_time     = "${local.current_year}-04-15T00:00:00Z"
      end_time       = "${local.current_year}-05-15T23:59:59Z"
      exclusion_options {
        scope = "NO_UPGRADES"
      }
    }
    
    # Q3 Code Freeze (July 15 - August 15)
    maintenance_exclusion {
      exclusion_name = "q3-code-freeze-${local.current_year}"
      start_time     = "${local.current_year}-07-15T00:00:00Z"
      end_time       = "${local.current_year}-08-15T23:59:59Z"
      exclusion_options {
        scope = "NO_UPGRADES"
      }
    }
    
    # Q4 Code Freeze (October 15 - November 15)
    maintenance_exclusion {
      exclusion_name = "q4-code-freeze-${local.current_year}"
      start_time     = "${local.current_year}-10-15T00:00:00Z"
      end_time       = "${local.current_year}-11-15T23:59:59Z"
      exclusion_options {
        scope = "NO_UPGRADES"
      }
    }
  }
  
  # Release channel for controlled updates
  release_channel {
    channel = "REGULAR"  # Use STABLE for more conservative updates
  }
  
  # Enable auto-upgrade and auto-repair
  cluster_autoscaling {
    enabled = false  # Disable if you want manual control
  }
}

# Node pools with maintenance configuration
resource "google_container_node_pool" "primary_nodes" {
  for_each = var.clusters
  
  name       = "${each.value.name}-nodes"
  location   = each.value.location
  cluster    = google_container_cluster.clusters[each.key].name
  node_count = 2
  
  # Auto-upgrade and auto-repair settings
  management {
    auto_repair  = true
    auto_upgrade = true
  }
  
  # Upgrade settings
  upgrade_settings {
    max_surge       = 1
    max_unavailable = 1
    
    # Blue-green upgrade strategy for minimal disruption
    strategy = "SURGE"
  }
  
  node_config {
    preemptible  = false
    machine_type = "e2-medium"
    
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]
    
    labels = {
      environment = each.key
      compliance  = "sox"
    }
    
    tags = ["gke-node", "${each.value.name}-node"]
  }
}
```

## 2. Advanced Maintenance Policy Configuration

```hcl
# advanced-maintenance.tf
resource "google_container_cluster" "prod_cluster_advanced" {
  name     = "prod-cluster-advanced"
  location = "us-central1"
  
  # Advanced maintenance policy
  maintenance_policy {
    # Multiple recurring windows for different types of maintenance
    recurring_window {
      start_time = "${local.current_year}-01-01T02:00:00Z"
      end_time   = "${local.current_year}-01-01T04:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SA"  # Saturdays 2-4 AM
    }
    
    # Emergency maintenance window (Sundays, smaller window)
    recurring_window {
      start_time = "${local.current_year}-01-02T01:00:00Z"
      end_time   = "${local.current_year}-01-02T02:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SU"  # Sundays 1-2 AM
    }
    
    # Year-end holiday exclusion
    maintenance_exclusion {
      exclusion_name = "year-end-freeze-${local.current_year}"
      start_time     = "${local.current_year}-12-20T00:00:00Z"
      end_time       = "${local.next_year}-01-05T00:00:00Z"
      exclusion_options {
        scope = "NO_UPGRADES"
      }
    }
    
    # SOX audit preparation exclusion
    maintenance_exclusion {
      exclusion_name = "sox-audit-prep-${local.current_year}"
      start_time     = "${local.current_year}-10-01T00:00:00Z"
      end_time       = "${local.current_year}-11-30T23:59:59Z"
      exclusion_options {
        scope = "NO_UPGRADES"
      }
    }
    
    # Memorial Day weekend
    maintenance_exclusion {
      exclusion_name = "memorial-day-${local.current_year}"
      start_time     = "${local.current_year}-05-25T00:00:00Z"
      end_time       = "${local.current_year}-05-31T23:59:59Z"
      exclusion_options {
        scope = "NO_MINOR_UPGRADES"
      }
    }
    
    # Labor Day weekend
    maintenance_exclusion {
      exclusion_name = "labor-day-${local.current_year}"
      start_time     = "${local.current_year}-09-01T00:00:00Z"
      end_time       = "${local.current_year}-09-07T23:59:59Z"
      exclusion_options {
        scope = "NO_MINOR_UPGRADES"
      }
    }
  }
  
  release_channel {
    channel = "STABLE"  # Most conservative for production
  }
  
  # Network policy for compliance
  network_policy {
    enabled = true
  }
  
  # Private cluster for security
  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block  = "10.0.0.0/28"
  }
  
  # Workload Identity for SOX compliance
  workload_identity_config {
    workload_pool = "${data.google_project.current.project_id}.svc.id.goog"
  }
}

data "google_project" "current" {}
```

## 3. Monitoring and Alerting for Maintenance Events

```yaml
# monitoring/maintenance-alerts.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: gke-maintenance-alerts
  namespace: monitoring
spec:
  groups:
  - name: gke.maintenance
    rules:
    - alert: GKEMaintenanceStarted
      expr: increase(gke_maintenance_events_total[5m]) > 0
      for: 0m
      labels:
        severity: info
        compliance: sox
      annotations:
        summary: "GKE maintenance event started"
        description: "Maintenance event started on cluster {{ $labels.cluster_name }}"
    
    - alert: GKEUpgradeAvailable
      expr: gke_upgrade_available == 1
      for: 15m
      labels:
        severity: warning
        compliance: sox
      annotations:
        summary: "GKE upgrade available outside maintenance window"
        description: "Cluster {{ $labels.cluster_name }} has upgrades available but maintenance window restrictions apply"
    
    - alert: GKEMaintenanceExclusionActive
      expr: gke_maintenance_exclusion_active == 1
      for: 0m
      labels:
        severity: info
        compliance: sox
      annotations:
        summary: "GKE maintenance exclusion active"
        description: "Maintenance exclusion {{ $labels.exclusion_name }} is active on cluster {{ $labels.cluster_name }}"
```

## 4. CLI Scripts for Management

```bash
#!/bin/bash
# scripts/manage-maintenance.sh

set -euo pipefail

CLUSTERS=("prod-cluster" "staging-cluster" "dev-cluster")
PROJECT_ID="your-project-id"
REGION="us-central1"

# Function to check current maintenance windows
check_maintenance_status() {
    echo "=== Current Maintenance Status ==="
    for cluster in "${CLUSTERS[@]}"; do
        echo "Cluster: $cluster"
        gcloud container clusters describe "$cluster" \
            --region="$REGION" \
            --project="$PROJECT_ID" \
            --format="table(maintenancePolicy.window.dailyMaintenanceWindow.startTime,maintenancePolicy.window.recurringWindow.window.startTime:label=RECURRING_START,maintenancePolicy.exclusions[].exclusionName:label=ACTIVE_EXCLUSIONS)"
        echo ""
    done
}

# Function to add emergency exclusion
add_emergency_exclusion() {
    local cluster_name="$1"
    local start_date="$2"
    local end_date="$3"
    local reason="$4"
    
    echo "Adding emergency exclusion to $cluster_name"
    gcloud container clusters update "$cluster_name" \
        --region="$REGION" \
        --project="$PROJECT_ID" \
        --add-maintenance-exclusion-name="emergency-$(date +%Y%m%d)" \
        --add-maintenance-exclusion-start="$start_date" \
        --add-maintenance-exclusion-end="$end_date" \
        --maintenance-exclusion-scope="NO_UPGRADES"
}

# Function to remove maintenance exclusion
remove_maintenance_exclusion() {
    local cluster_name="$1"
    local exclusion_name="$2"
    
    echo "Removing maintenance exclusion $exclusion_name from $cluster_name"
    gcloud container clusters update "$cluster_name" \
        --region="$REGION" \
        --project="$PROJECT_ID" \
        --remove-maintenance-exclusion-name="$exclusion_name"
}

# Function to update maintenance window
update_maintenance_window() {
    local cluster_name="$1"
    local start_time="$2"
    
    echo "Updating maintenance window for $cluster_name"
    gcloud container clusters update "$cluster_name" \
        --region="$REGION" \
        --project="$PROJECT_ID" \
        --maintenance-window-start="$start_time" \
        --maintenance-window-end="4h"
}

case "${1:-status}" in
    "status")
        check_maintenance_status
        ;;
    "emergency-exclusion")
        if [ $# -ne 5 ]; then
            echo "Usage: $0 emergency-exclusion <cluster> <start-date> <end-date> <reason>"
            exit 1
        fi
        add_emergency_exclusion "$2" "$3" "$4" "$5"
        ;;
    "remove-exclusion")
        if [ $# -ne 3 ]; then
            echo "Usage: $0 remove-exclusion <cluster> <exclusion-name>"
            exit 1
        fi
        remove_maintenance_exclusion "$2" "$3"
        ;;
    "update-window")
        if [ $# -ne 3 ]; then
            echo "Usage: $0 update-window <cluster> <start-time>"
            exit 1
        fi
        update_maintenance_window "$2" "$3"
        ;;
    *)
        echo "Usage: $0 {status|emergency-exclusion|remove-exclusion|update-window}"
        exit 1
        ;;
esac
```

## 5. Compliance Reporting Script

```python
#!/usr/bin/env python3
# scripts/compliance-report.py

import json
import subprocess
from datetime import datetime, timedelta
import csv

def get_cluster_info(project_id, region, cluster_name):
    """Get cluster maintenance configuration"""
    cmd = [
        'gcloud', 'container', 'clusters', 'describe', cluster_name,
        '--region', region,
        '--project', project_id,
        '--format', 'json'
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(result.stdout) if result.returncode == 0 else None

def generate_compliance_report(project_id, region, clusters):
    """Generate SOX compliance report"""
    report_data = []
    
    for cluster_name in clusters:
        cluster_info = get_cluster_info(project_id, region, cluster_name)
        if not cluster_info:
            continue
            
        maintenance_policy = cluster_info.get('maintenancePolicy', {})
        
        # Check maintenance windows
        daily_window = maintenance_policy.get('window', {}).get('dailyMaintenanceWindow', {})
        recurring_windows = maintenance_policy.get('window', {}).get('recurringWindow', [])
        exclusions = maintenance_policy.get('exclusions', [])
        
        report_entry = {
            'cluster_name': cluster_name,
            'region': region,
            'maintenance_start_time': daily_window.get('startTime', 'Not configured'),
            
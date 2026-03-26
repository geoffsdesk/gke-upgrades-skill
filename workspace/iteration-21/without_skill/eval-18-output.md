I'll help you configure maintenance windows and exclusions for your GKE clusters to meet SOX compliance requirements. Here's a comprehensive solution:

## 1. Terraform Configuration for Maintenance Windows

```hcl
# terraform/gke-maintenance.tf

resource "google_container_cluster" "compliant_cluster" {
  count    = 3
  name     = "prod-cluster-${count.index + 1}"
  location = var.cluster_locations[count.index]
  
  # Other cluster configuration...
  
  # Maintenance policy for weekend-only upgrades
  maintenance_policy {
    # Daily maintenance window (for minor maintenance)
    daily_maintenance_window {
      start_time = "02:00"  # 2 AM local time
    }
    
    # Recurring maintenance windows for major upgrades
    recurring_window {
      start_time = "2024-01-06T02:00:00Z"  # First Saturday of 2024
      end_time   = "2024-01-06T06:00:00Z"  # 4-hour window
      recurrence = "FREQ=WEEKLY;BYDAY=SA"  # Every Saturday
    }
    
    # Quarterly code freeze exclusions (Q1, Q2, Q3, Q4)
    maintenance_exclusion {
      exclusion_name = "q1-code-freeze"
      start_time     = "2024-03-15T00:00:00Z"
      end_time       = "2024-04-01T00:00:00Z"
      exclusion_scope = "UPGRADES"
    }
    
    maintenance_exclusion {
      exclusion_name = "q2-code-freeze"
      start_time     = "2024-06-15T00:00:00Z"
      end_time       = "2024-07-01T00:00:00Z"
      exclusion_scope = "UPGRADES"
    }
    
    maintenance_exclusion {
      exclusion_name = "q3-code-freeze"
      start_time     = "2024-09-15T00:00:00Z"
      end_time       = "2024-10-01T00:00:00Z"
      exclusion_scope = "UPGRADES"
    }
    
    maintenance_exclusion {
      exclusion_name = "q4-code-freeze"
      start_time     = "2024-12-15T00:00:00Z"
      end_time       = "2025-01-01T00:00:00Z"
      exclusion_scope = "UPGRADES"
    }
    
    # Annual audit exclusion (November)
    maintenance_exclusion {
      exclusion_name = "annual-audit-2024"
      start_time     = "2024-11-01T00:00:00Z"
      end_time       = "2024-11-30T23:59:59Z"
      exclusion_scope = "UPGRADES"
    }
    
    # Holiday exclusions
    maintenance_exclusion {
      exclusion_name = "holiday-freeze-2024"
      start_time     = "2024-12-20T00:00:00Z"
      end_time       = "2025-01-02T23:59:59Z"
      exclusion_scope = "UPGRADES"
    }
  }
  
  # Enable network policy for compliance
  network_policy {
    enabled = true
  }
  
  # Enable Workload Identity for security
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }
  
  # Enable audit logging for SOX compliance
  cluster_telemetry {
    type = "ENABLED"
  }
}

# Variables
variable "cluster_locations" {
  description = "Locations for the three clusters"
  type        = list(string)
  default     = ["us-central1-a", "us-east1-a", "us-west1-a"]
}

variable "project_id" {
  description = "GCP Project ID"
  type        = string
}
```

## 2. Advanced Maintenance Configuration Script

```bash
#!/bin/bash
# scripts/configure-maintenance-windows.sh

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-your-project-id}"
CLUSTERS=("prod-cluster-1" "prod-cluster-2" "prod-cluster-3")
LOCATIONS=("us-central1-a" "us-east1-a" "us-west1-a")

# Function to configure maintenance window for a cluster
configure_cluster_maintenance() {
    local cluster_name=$1
    local location=$2
    local current_year=$(date +%Y)
    local next_year=$((current_year + 1))
    
    echo "Configuring maintenance window for $cluster_name in $location"
    
    # Set recurring weekend maintenance window
    gcloud container clusters update "$cluster_name" \
        --location="$location" \
        --maintenance-window-start="2024-01-06T02:00:00Z" \
        --maintenance-window-end="2024-01-06T06:00:00Z" \
        --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SA" \
        --project="$PROJECT_ID"
    
    # Add quarterly maintenance exclusions
    add_quarterly_exclusions "$cluster_name" "$location" "$current_year"
    
    # Add annual audit exclusion
    add_audit_exclusion "$cluster_name" "$location" "$current_year"
    
    echo "✓ Maintenance configuration completed for $cluster_name"
}

# Function to add quarterly code freeze exclusions
add_quarterly_exclusions() {
    local cluster_name=$1
    local location=$2
    local year=$3
    
    local quarters=(
        "q1-code-freeze:${year}-03-15T00:00:00Z:${year}-04-01T00:00:00Z"
        "q2-code-freeze:${year}-06-15T00:00:00Z:${year}-07-01T00:00:00Z"
        "q3-code-freeze:${year}-09-15T00:00:00Z:${year}-10-01T00:00:00Z"
        "q4-code-freeze:${year}-12-15T00:00:00Z:$((year+1))-01-01T00:00:00Z"
    )
    
    for quarter in "${quarters[@]}"; do
        IFS=':' read -r name start_time end_time <<< "$quarter"
        
        gcloud container clusters update "$cluster_name" \
            --location="$location" \
            --add-maintenance-exclusion-name="$name" \
            --add-maintenance-exclusion-start="$start_time" \
            --add-maintenance-exclusion-end="$end_time" \
            --add-maintenance-exclusion-scope="UPGRADES" \
            --project="$PROJECT_ID"
            
        echo "  ✓ Added exclusion: $name"
    done
}

# Function to add annual audit exclusion
add_audit_exclusion() {
    local cluster_name=$1
    local location=$2
    local year=$3
    
    gcloud container clusters update "$cluster_name" \
        --location="$location" \
        --add-maintenance-exclusion-name="annual-audit-$year" \
        --add-maintenance-exclusion-start="${year}-11-01T00:00:00Z" \
        --add-maintenance-exclusion-end="${year}-11-30T23:59:59Z" \
        --add-maintenance-exclusion-scope="UPGRADES" \
        --project="$PROJECT_ID"
        
    echo "  ✓ Added annual audit exclusion for November $year"
}

# Main execution
main() {
    echo "Starting maintenance window configuration for SOX-compliant GKE clusters..."
    
    for i in "${!CLUSTERS[@]}"; do
        configure_cluster_maintenance "${CLUSTERS[$i]}" "${LOCATIONS[$i]}"
    done
    
    echo "All clusters configured successfully!"
}

# Run if executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
```

## 3. Kubernetes Manifest for Maintenance Monitoring

```yaml
# k8s/maintenance-monitoring.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: maintenance-config
  namespace: kube-system
data:
  maintenance-schedule.yaml: |
    quarterly_freezes:
      - name: "Q1 Code Freeze"
        start: "2024-03-15"
        end: "2024-04-01"
      - name: "Q2 Code Freeze"
        start: "2024-06-15"
        end: "2024-07-01"
      - name: "Q3 Code Freeze"
        start: "2024-09-15"
        end: "2024-10-01"
      - name: "Q4 Code Freeze"
        start: "2024-12-15"
        end: "2025-01-01"
    
    annual_audit:
      start: "2024-11-01"
      end: "2024-11-30"
    
    maintenance_window:
      day: "Saturday"
      start_time: "02:00 UTC"
      duration: "4 hours"

---
apiVersion: batch/v1
kind: CronJob
metadata:
  name: maintenance-compliance-check
  namespace: kube-system
spec:
  schedule: "0 8 * * MON"  # Every Monday at 8 AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: compliance-checker
            image: google/cloud-sdk:alpine
            command:
            - /bin/sh
            - -c
            - |
              # Check maintenance windows configuration
              gcloud container clusters describe $CLUSTER_NAME \
                --location=$CLUSTER_LOCATION \
                --project=$PROJECT_ID \
                --format="yaml(maintenancePolicy)" > /tmp/maintenance-policy.yaml
              
              echo "Current maintenance policy:"
              cat /tmp/maintenance-policy.yaml
              
              # Verify exclusions are in place
              echo "Checking maintenance exclusions..."
              grep -q "exclusionName.*code-freeze" /tmp/maintenance-policy.yaml && \
                echo "✓ Code freeze exclusions found" || \
                echo "⚠ Code freeze exclusions missing"
              
              grep -q "exclusionName.*audit" /tmp/maintenance-policy.yaml && \
                echo "✓ Audit exclusions found" || \
                echo "⚠ Audit exclusions missing"
            env:
            - name: CLUSTER_NAME
              value: "prod-cluster-1"  # Configure per cluster
            - name: CLUSTER_LOCATION
              value: "us-central1-a"
            - name: PROJECT_ID
              value: "your-project-id"
          restartPolicy: OnFailure
          serviceAccountName: maintenance-checker
```

## 4. Monitoring and Alerting Configuration

```yaml
# monitoring/maintenance-alerts.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: gke-maintenance-compliance
  namespace: monitoring
spec:
  groups:
  - name: gke.maintenance
    rules:
    - alert: MaintenanceWindowViolation
      expr: |
        (
          time() > on() kube_node_info{node=~"gke-.*"} and
          hour() < 2 or hour() > 6
        ) and on() day_of_week() != 6
      for: 5m
      labels:
        severity: critical
        compliance: sox
      annotations:
        summary: "GKE maintenance occurring outside approved window"
        description: "Maintenance activity detected outside the approved Saturday 2-6 AM window"
    
    - alert: MaintenanceDuringCodeFreeze
      expr: |
        (
          time() > on() (
            timestamp(label_replace(kube_configmap_info{configmap="maintenance-config"}, "freeze_start", "$1", "data_maintenance_schedule_yaml", ".*start: \"([^\"]+)\".*"))
          ) and
          time() < on() (
            timestamp(label_replace(kube_configmap_info{configmap="maintenance-config"}, "freeze_end", "$1", "data_maintenance_schedule_yaml", ".*end: \"([^\"]+)\".*"))
          )
        )
      for: 0m
      labels:
        severity: critical
        compliance: sox
      annotations:
        summary: "GKE maintenance during code freeze period"
        description: "Maintenance activity detected during quarterly code freeze"

---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: maintenance-checker
  namespace: kube-system
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: maintenance-checker
rules:
- apiGroups: [""]
  resources: ["configmaps", "nodes"]
  verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: maintenance-checker
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: maintenance-checker
subjects:
- kind: ServiceAccount
  name: maintenance-checker
  namespace: kube-system
```

## 5. Annual Maintenance Schedule Update Script

```python
#!/usr/bin/env python3
# scripts/update-annual-schedule.py

import json
import subprocess
import sys
from datetime import datetime, timedelta
import argparse

class MaintenanceScheduleUpdater:
    def __init__(self, project_id):
        self.project_id = project_id
        self.clusters = [
            {"name": "prod-cluster-1", "location": "us-central1-a"},
            {"name": "prod-cluster-2", "location": "us-east1-a"},
            {"name": "prod-cluster-3", "location": "us-west1-a"}
        ]
    
    def generate_quarterly_dates(self, year):
        """Generate quarterly code freeze dates."""
        return [
            {"name": f"q1-code-freeze-{year}", "start": f"{year}-03-15T00:00:00Z", "end": f"{year}-04-01T00:00:00Z"},
            {"name": f"q2-code-freeze-{year}", "start": f"{year}-06-15T00:00:00Z", "end": f"{year}-07-01T00:00:00Z"},
            {"name": f"q3-code-freeze-{year}", "start": f"{year}-09-15T00:00:00Z", "end": f"{year}-10-01T00:00:00Z"},
            {"name": f"q4-code-freeze-{year}", "start": f"{year}-12-15T00:00:00Z", "end": f"{year+1}-01-01T00:00:00Z"}
        ]
    
    def update_cluster_exclusions(self, cluster_name, location, year):
        """Update maintenance exclusions for a specific cluster."""
        print(f"Updating exclusions for {cluster_name}")
        
        # Remove old exclusions
        self.remove_old_exclusions(cluster_name, location, year - 1)
        
        # Add quarterly exclusions
        quarterly_dates = self.generate_quarterly_dates(year)
        for exclusion in quarterly_dates:
            self.add_exclusion(cluster_name, location, exclusion)
        
        # Add annual audit exclusion
        audit_exclusion = {
            "name": f"annual-audit-{year}",
            "start": f"{year}-11-01T00:00:00Z",
            "end": f"{year}-11-30T23:59:59Z"
        }
        self.add_exclusion(cluster_name, location, audit_exclusion)
        
        print(f"✓ Updated exclusions for {cluster_name}")
    
    def add_exclusion(self, cluster_name, location, exclusion):
        """Add a maintenance exclusion."""
        cmd =
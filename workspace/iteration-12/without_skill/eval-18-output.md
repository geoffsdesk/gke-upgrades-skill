I'll help you configure maintenance windows and exclusions for your GKE Standard clusters to meet SOX compliance requirements. Here's a comprehensive setup:

## 1. Maintenance Window Configuration

```yaml
# maintenance-window-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: gke-maintenance-config
  namespace: default
data:
  maintenance-policy: |
    # Weekend-only maintenance window
    # Saturday 2 AM - Sunday 6 AM UTC
    start-time: "2023-01-01T02:00:00Z"
    duration: "28h"  # 28 hours to cover full weekend window
    recurrence: "FREQ=WEEKLY;BYDAY=SA"
```

## 2. Terraform Configuration for All 3 Clusters

```hcl
# gke-maintenance.tf
variable "cluster_names" {
  description = "Names of the three GKE clusters"
  type        = list(string)
  default     = ["prod-cluster-1", "prod-cluster-2", "prod-cluster-3"]
}

variable "quarterly_freeze_dates" {
  description = "Quarterly code freeze periods"
  type = list(object({
    start_date = string
    end_date   = string
    quarter    = string
  }))
  default = [
    {
      start_date = "2024-03-15"
      end_date   = "2024-03-31"
      quarter    = "Q1"
    },
    {
      start_date = "2024-06-15"
      end_date   = "2024-06-30"
      quarter    = "Q2"
    },
    {
      start_date = "2024-09-15"
      end_date   = "2024-09-30"
      quarter    = "Q3"
    },
    {
      start_date = "2024-12-15"
      end_date   = "2024-12-31"
      quarter    = "Q4"
    }
  ]
}

# Generate maintenance exclusions
locals {
  # Annual audit exclusion (entire November)
  audit_exclusions = [
    {
      exclusion_name = "annual-sox-audit"
      start_time     = "${formatdate("YYYY", timestamp())}-11-01T00:00:00Z"
      end_time       = "${formatdate("YYYY", timestamp())}-11-30T23:59:59Z"
      exclusion_scope = "NO_UPGRADES"
    }
  ]
  
  # Quarterly freeze exclusions
  quarterly_exclusions = [
    for freeze in var.quarterly_freeze_dates : {
      exclusion_name  = "quarterly-freeze-${freeze.quarter}"
      start_time      = "${freeze.start_date}T00:00:00Z"
      end_time        = "${freeze.end_date}T23:59:59Z"
      exclusion_scope = "NO_UPGRADES"
    }
  ]
  
  # Holiday exclusions (add major holidays)
  holiday_exclusions = [
    {
      exclusion_name  = "christmas-freeze"
      start_time      = "${formatdate("YYYY", timestamp())}-12-23T00:00:00Z"
      end_time        = "${formatdate("YYYY", timestamp())}-01-02T23:59:59Z"
      exclusion_scope = "NO_UPGRADES"
    },
    {
      exclusion_name  = "thanksgiving-freeze"
      start_time      = "${formatdate("YYYY", timestamp())}-11-23T00:00:00Z"
      end_time        = "${formatdate("YYYY", timestamp())}-11-26T23:59:59Z"
      exclusion_scope = "NO_UPGRADES"
    }
  ]
  
  all_exclusions = concat(
    local.audit_exclusions,
    local.quarterly_exclusions,
    local.holiday_exclusions
  )
}

# Configure each cluster
resource "google_container_cluster" "clusters" {
  count    = length(var.cluster_names)
  name     = var.cluster_names[count.index]
  location = var.gke_zone

  # Enable maintenance policy
  maintenance_policy {
    # Weekend maintenance window (Saturday 2 AM UTC)
    daily_maintenance_window {
      start_time = "02:00"
    }
    
    # More granular control with recurring window
    recurring_window {
      start_time = "2024-01-06T02:00:00Z"  # First Saturday
      end_time   = "2024-01-07T06:00:00Z"  # Sunday 6 AM
      recurrence = "FREQ=WEEKLY;BYDAY=SA"
    }

    # Apply all maintenance exclusions
    dynamic "maintenance_exclusion" {
      for_each = local.all_exclusions
      content {
        exclusion_name = maintenance_exclusion.value.exclusion_name
        start_time     = maintenance_exclusion.value.start_time
        end_time       = maintenance_exclusion.value.end_time
        exclusion_options {
          scope = maintenance_exclusion.value.exclusion_scope
        }
      }
    }
  }

  # Release channel for controlled updates
  release_channel {
    channel = "REGULAR"  # Use REGULAR for better control, avoid RAPID
  }

  # Cluster-level logging for audit trail
  logging_config {
    enable_components = [
      "SYSTEM_COMPONENTS",
      "WORKLOADS",
      "API_SERVER"
    ]
  }

  # Monitoring for compliance reporting
  monitoring_config {
    enable_components = [
      "SYSTEM_COMPONENTS",
      "WORKLOADS"
    ]
    managed_prometheus {
      enabled = true
    }
  }
}

# Node pool configuration with maintenance settings
resource "google_container_node_pool" "primary_nodes" {
  count      = length(var.cluster_names)
  name       = "${var.cluster_names[count.index]}-nodes"
  cluster    = google_container_cluster.clusters[count.index].name
  location   = var.gke_zone

  # Auto-upgrade settings
  management {
    auto_repair  = true
    auto_upgrade = true
  }

  # Upgrade settings aligned with maintenance windows
  upgrade_settings {
    strategy      = "SURGE"
    max_surge     = 1
    max_unavailable = 0
  }

  node_config {
    machine_type = "e2-medium"
    
    # Service account with minimal permissions
    service_account = google_service_account.gke_nodes[count.index].email
    oauth_scopes = [
      "https://www.googleapis.com/auth/logging.write",
      "https://www.googleapis.com/auth/monitoring",
      "https://www.googleapis.com/auth/devstorage.read_only"
    ]

    labels = {
      environment = "production"
      compliance  = "sox"
      cluster     = var.cluster_names[count.index]
    }

    tags = ["gke-node", "sox-compliant"]
  }
}

# Service accounts for nodes
resource "google_service_account" "gke_nodes" {
  count        = length(var.cluster_names)
  account_id   = "${var.cluster_names[count.index]}-nodes-sa"
  display_name = "GKE nodes service account for ${var.cluster_names[count.index]}"
}
```

## 3. gcloud CLI Commands for Manual Management

```bash
#!/bin/bash
# maintenance-management.sh

# Set variables
PROJECT_ID="your-project-id"
CLUSTERS=("prod-cluster-1" "prod-cluster-2" "prod-cluster-3")
ZONE="us-central1-a"

# Function to set maintenance window for all clusters
set_maintenance_windows() {
    for cluster in "${CLUSTERS[@]}"; do
        echo "Setting maintenance window for $cluster..."
        
        # Set recurring maintenance window (Saturdays 2 AM UTC)
        gcloud container clusters update $cluster \
            --zone=$ZONE \
            --maintenance-window-start "2024-01-06T02:00:00Z" \
            --maintenance-window-end "2024-01-07T06:00:00Z" \
            --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA" \
            --project=$PROJECT_ID
    done
}

# Function to add quarterly exclusions
add_quarterly_exclusions() {
    local quarter=$1
    local start_date=$2
    local end_date=$3
    
    for cluster in "${CLUSTERS[@]}"; do
        echo "Adding Q${quarter} freeze exclusion to $cluster..."
        
        gcloud container clusters update $cluster \
            --zone=$ZONE \
            --add-maintenance-exclusion-name="q${quarter}-freeze-2024" \
            --add-maintenance-exclusion-start="${start_date}T00:00:00Z" \
            --add-maintenance-exclusion-end="${end_date}T23:59:59Z" \
            --add-maintenance-exclusion-scope="NO_UPGRADES" \
            --project=$PROJECT_ID
    done
}

# Function to add annual audit exclusion
add_audit_exclusion() {
    local year=$(date +%Y)
    
    for cluster in "${CLUSTERS[@]}"; do
        echo "Adding annual audit exclusion to $cluster..."
        
        gcloud container clusters update $cluster \
            --zone=$ZONE \
            --add-maintenance-exclusion-name="annual-sox-audit-${year}" \
            --add-maintenance-exclusion-start="${year}-11-01T00:00:00Z" \
            --add-maintenance-exclusion-end="${year}-11-30T23:59:59Z" \
            --add-maintenance-exclusion-scope="NO_UPGRADES" \
            --project=$PROJECT_ID
    done
}

# Function to check maintenance status
check_maintenance_status() {
    for cluster in "${CLUSTERS[@]}"; do
        echo "=== Maintenance status for $cluster ==="
        gcloud container clusters describe $cluster \
            --zone=$ZONE \
            --project=$PROJECT_ID \
            --format="yaml(maintenancePolicy)"
        echo ""
    done
}

# Execute functions
echo "Setting up maintenance windows and exclusions..."
set_maintenance_windows

echo "Adding quarterly exclusions..."
add_quarterly_exclusions "1" "2024-03-15" "2024-03-31"
add_quarterly_exclusions "2" "2024-06-15" "2024-06-30"
add_quarterly_exclusions "3" "2024-09-15" "2024-09-30"
add_quarterly_exclusions "4" "2024-12-15" "2024-12-31"

echo "Adding annual audit exclusion..."
add_audit_exclusion

echo "Checking maintenance status..."
check_maintenance_status
```

## 4. Monitoring and Alerting Configuration

```yaml
# monitoring-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: maintenance-monitoring
data:
  alert-policy: |
    displayName: "GKE Maintenance Policy Violations"
    conditions:
      - displayName: "Unauthorized upgrade detected"
        conditionThreshold:
          filter: 'resource.type="gke_cluster" AND log_name="projects/PROJECT_ID/logs/cloudaudit.googleapis.com%2Factivity"'
          comparison: COMPARISON_GREATER_THAN
          thresholdValue: 0
    notificationChannels:
      - "projects/PROJECT_ID/notificationChannels/CHANNEL_ID"
    alertStrategy:
      autoClose: "1800s"
---
apiVersion: batch/v1
kind: CronJob
metadata:
  name: maintenance-compliance-check
spec:
  schedule: "0 9 * * MON"  # Every Monday at 9 AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: compliance-checker
            image: google/cloud-sdk:alpine
            command:
            - /bin/bash
            - -c
            - |
              # Check for any upgrades that occurred outside maintenance windows
              gcloud logging read "
                resource.type=gke_cluster AND
                protoPayload.methodName=google.container.v1.ClusterManager.UpdateCluster AND
                timestamp >= '$(date -d '7 days ago' --iso-8601)'
              " --format="table(timestamp,resource.labels.cluster_name,protoPayload.authenticationInfo.principalEmail)"
          restartPolicy: OnFailure
```

## 5. Compliance Documentation Template

```markdown
# GKE Maintenance Policy - SOX Compliance Documentation

## Overview
This document outlines the maintenance windows and exclusions configured for our three production GKE clusters to ensure SOX compliance.

## Maintenance Windows
- **Schedule**: Saturdays 2:00 AM - Sundays 6:00 AM UTC
- **Frequency**: Weekly
- **Scope**: All cluster and node upgrades

## Maintenance Exclusions

### Quarterly Code Freezes
- Q1: March 15-31
- Q2: June 15-30  
- Q3: September 15-30
- Q4: December 15-31

### Annual Audit Period
- **Duration**: Entire month of November
- **Scope**: Complete upgrade freeze

### Holiday Exclusions
- Christmas/New Year: December 23 - January 2
- Thanksgiving: November 23-26

## Audit Trail
- All maintenance activities logged to Cloud Logging
- Weekly compliance reports generated
- Automated alerting for policy violations

## Emergency Procedures
For critical security updates during exclusion periods:
1. Document business justification
2. Get approval from SOX compliance team
3. Create temporary maintenance window
4. Document all changes in audit log
```

This configuration ensures:

1. **Weekend-only upgrades** (Saturday-Sunday maintenance windows)
2. **Quarterly freeze periods** with no upgrades
3. **November audit exclusion** (complete month)
4. **Holiday protections** for major holidays
5. **Comprehensive logging** for audit trails
6. **Automated monitoring** for compliance violations

The setup provides the control and documentation needed for SOX compliance while maintaining security through controlled, scheduled updates.
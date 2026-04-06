I'll help you configure maintenance windows and exclusions for SOX compliance across your 3 GKE Standard clusters. Here's a comprehensive setup:

## 1. Maintenance Window Configuration

First, let's configure weekend-only maintenance windows:

```yaml
# maintenance-policy.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: maintenance-policy-config
data:
  policy: |
    # Weekend maintenance window: Saturday 2 AM - Sunday 11 PM UTC
    # Adjust timezone as needed for your region
    maintenance_window:
      start_time: "2024-01-01T02:00:00Z"  # Saturday 2 AM UTC
      end_time: "2024-01-01T23:00:00Z"    # Sunday 11 PM UTC
      recurrence: "FREQ=WEEKLY;BYDAY=SA,SU"
```

## 2. Terraform Configuration for All 3 Clusters

```hcl
# variables.tf
variable "cluster_names" {
  description = "Names of the three GKE clusters"
  type        = list(string)
  default     = ["prod-cluster-1", "prod-cluster-2", "prod-cluster-3"]
}

variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP Region"
  type        = string
  default     = "us-central1"
}

# main.tf
resource "google_container_cluster" "sox_compliant_clusters" {
  count    = length(var.cluster_names)
  name     = var.cluster_names[count.index]
  location = var.region
  project  = var.project_id

  # Remove default node pool
  remove_default_node_pool = true
  initial_node_count       = 1

  # Maintenance policy for SOX compliance
  maintenance_policy {
    # Weekend maintenance window (Saturday 2 AM - Sunday 11 PM UTC)
    daily_maintenance_window {
      start_time = "02:00"
    }
    
    # Recurring maintenance window for weekends only
    recurring_window {
      start_time = "2024-01-06T02:00:00Z"  # First Saturday of 2024
      end_time   = "2024-01-07T23:00:00Z"  # First Sunday of 2024
      recurrence = "FREQ=WEEKLY;BYDAY=SA,SU"
    }

    # Maintenance exclusions for SOX compliance
    maintenance_exclusion {
      exclusion_name = "q1-code-freeze-2024"
      start_time     = "2024-03-15T00:00:00Z"
      end_time       = "2024-03-31T23:59:59Z"
      exclusion_scope = "UPGRADES"
    }

    maintenance_exclusion {
      exclusion_name = "q2-code-freeze-2024"
      start_time     = "2024-06-15T00:00:00Z"
      end_time       = "2024-06-30T23:59:59Z"
      exclusion_scope = "UPGRADES"
    }

    maintenance_exclusion {
      exclusion_name = "q3-code-freeze-2024"
      start_time     = "2024-09-15T00:00:00Z"
      end_time       = "2024-09-30T23:59:59Z"
      exclusion_scope = "UPGRADES"
    }

    maintenance_exclusion {
      exclusion_name = "annual-audit-november-2024"
      start_time     = "2024-11-01T00:00:00Z"
      end_time       = "2024-11-30T23:59:59Z"
      exclusion_scope = "UPGRADES"
    }

    maintenance_exclusion {
      exclusion_name = "q4-code-freeze-2024"
      start_time     = "2024-12-15T00:00:00Z"
      end_time       = "2024-12-31T23:59:59Z"
      exclusion_scope = "UPGRADES"
    }
  }

  # Release channel for controlled updates
  release_channel {
    channel = "REGULAR"  # Use STABLE for even more conservative updates
  }

  # Enable network policy for security
  network_policy {
    enabled = true
  }

  # Enable workload identity for security
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  # Logging and monitoring for audit trail
  logging_service    = "logging.googleapis.com/kubernetes"
  monitoring_service = "monitoring.googleapis.com/kubernetes"

  # Enable audit logs
  enable_legacy_abac = false
  
  master_auth {
    client_certificate_config {
      issue_client_certificate = false
    }
  }

  # Network configuration
  network    = "default"
  subnetwork = "default"

  # IP allocation policy
  ip_allocation_policy {
    cluster_ipv4_cidr_block  = "/14"
    services_ipv4_cidr_block = "/20"
  }
}

# Node pools for each cluster
resource "google_container_node_pool" "sox_compliant_nodes" {
  count      = length(var.cluster_names)
  name       = "${var.cluster_names[count.index]}-nodes"
  location   = var.region
  cluster    = google_container_cluster.sox_compliant_clusters[count.index].name
  project    = var.project_id
  
  node_count = 3

  # Auto-upgrade settings aligned with maintenance windows
  management {
    auto_repair  = true
    auto_upgrade = true
  }

  node_config {
    preemptible  = false
    machine_type = "e2-medium"

    # Security settings for SOX compliance
    service_account = google_service_account.gke_nodes[count.index].email
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]

    # Enable workload identity
    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    # Enable secure boot
    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }

    # Disk encryption
    disk_type    = "pd-standard"
    disk_size_gb = 100
    
    labels = {
      environment = "production"
      compliance  = "sox"
      cluster     = var.cluster_names[count.index]
    }
  }
}

# Service accounts for nodes
resource "google_service_account" "gke_nodes" {
  count        = length(var.cluster_names)
  account_id   = "${var.cluster_names[count.index]}-nodes-sa"
  display_name = "GKE Nodes Service Account for ${var.cluster_names[count.index]}"
  project      = var.project_id
}

# IAM bindings for node service accounts
resource "google_project_iam_member" "gke_nodes_iam" {
  count   = length(var.cluster_names)
  project = var.project_id
  role    = "roles/container.nodeServiceAccount"
  member  = "serviceAccount:${google_service_account.gke_nodes[count.index].email}"
}
```

## 3. gcloud Commands for Immediate Application

If you need to apply these settings immediately to existing clusters:

```bash
#!/bin/bash

# Set your project and clusters
PROJECT_ID="your-project-id"
REGION="us-central1"
CLUSTERS=("prod-cluster-1" "prod-cluster-2" "prod-cluster-3")

# Function to set maintenance windows and exclusions
setup_maintenance_policy() {
  local cluster_name=$1
  
  echo "Configuring maintenance policy for cluster: $cluster_name"
  
  # Set weekend maintenance window
  gcloud container clusters update $cluster_name \
    --region=$REGION \
    --project=$PROJECT_ID \
    --maintenance-window-start="2024-01-06T02:00:00Z" \
    --maintenance-window-end="2024-01-07T23:00:00Z" \
    --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SA,SU"
  
  # Add Q1 2024 code freeze exclusion
  gcloud container clusters update $cluster_name \
    --region=$REGION \
    --project=$PROJECT_ID \
    --add-maintenance-exclusion-name="q1-code-freeze-2024" \
    --add-maintenance-exclusion-start="2024-03-15T00:00:00Z" \
    --add-maintenance-exclusion-end="2024-03-31T23:59:59Z" \
    --add-maintenance-exclusion-scope="UPGRADES"
  
  # Add Q2 2024 code freeze exclusion
  gcloud container clusters update $cluster_name \
    --region=$REGION \
    --project=$PROJECT_ID \
    --add-maintenance-exclusion-name="q2-code-freeze-2024" \
    --add-maintenance-exclusion-start="2024-06-15T00:00:00Z" \
    --add-maintenance-exclusion-end="2024-06-30T23:59:59Z" \
    --add-maintenance-exclusion-scope="UPGRADES"
  
  # Add Q3 2024 code freeze exclusion
  gcloud container clusters update $cluster_name \
    --region=$REGION \
    --project=$PROJECT_ID \
    --add-maintenance-exclusion-name="q3-code-freeze-2024" \
    --add-maintenance-exclusion-start="2024-09-15T00:00:00Z" \
    --add-maintenance-exclusion-end="2024-09-30T23:59:59Z" \
    --add-maintenance-exclusion-scope="UPGRADES"
  
  # Add November audit exclusion
  gcloud container clusters update $cluster_name \
    --region=$REGION \
    --project=$PROJECT_ID \
    --add-maintenance-exclusion-name="annual-audit-november-2024" \
    --add-maintenance-exclusion-start="2024-11-01T00:00:00Z" \
    --add-maintenance-exclusion-end="2024-11-30T23:59:59Z" \
    --add-maintenance-exclusion-scope="UPGRADES"
  
  # Add Q4 2024 code freeze exclusion
  gcloud container clusters update $cluster_name \
    --region=$REGION \
    --project=$PROJECT_ID \
    --add-maintenance-exclusion-name="q4-code-freeze-2024" \
    --add-maintenance-exclusion-start="2024-12-15T00:00:00Z" \
    --add-maintenance-exclusion-end="2024-12-31T23:59:59Z" \
    --add-maintenance-exclusion-scope="UPGRADES"
}

# Apply to all clusters
for cluster in "${CLUSTERS[@]}"; do
  setup_maintenance_policy $cluster
  echo "Completed configuration for $cluster"
  echo "---"
done

echo "All clusters configured with SOX-compliant maintenance policies"
```

## 4. Monitoring and Alerting Setup

```yaml
# monitoring/maintenance-alerts.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: gke-maintenance-alerts
  namespace: monitoring
spec:
  groups:
  - name: gke-maintenance
    rules:
    - alert: MaintenanceWindowViolation
      expr: |
        (
          hour() < 2 or hour() > 23 or 
          (day_of_week() != 6 and day_of_week() != 0)
        ) and on() kube_node_info{kubelet_version=~".*-gke.*"}
      for: 5m
      labels:
        severity: warning
        compliance: sox
      annotations:
        summary: "Potential maintenance activity outside approved window"
        description: "GKE maintenance activity detected outside weekend window"
    
    - alert: UpcomingMaintenanceExclusion
      expr: |
        (
          (month() == 3 and day() >= 10 and day() <= 15) or
          (month() == 6 and day() >= 10 and day() <= 15) or
          (month() == 9 and day() >= 10 and day() <= 15) or
          (month() == 10 and day() >= 25) or
          (month() == 11) or
          (month() == 12 and day() >= 10 and day() <= 15)
        )
      labels:
        severity: info
        compliance: sox
      annotations:
        summary: "Approaching maintenance exclusion period"
        description: "Code freeze or audit period approaching - verify maintenance exclusions are active"
```

## 5. Validation Script

```bash
#!/bin/bash

# validate-maintenance-policy.sh
PROJECT_ID="your-project-id"
REGION="us-central1"
CLUSTERS=("prod-cluster-1" "prod-cluster-2" "prod-cluster-3")

validate_cluster_policy() {
  local cluster_name=$1
  
  echo "Validating maintenance policy for: $cluster_name"
  echo "================================================"
  
  # Get cluster maintenance policy
  gcloud container clusters describe $cluster_name \
    --region=$REGION \
    --project=$PROJECT_ID \
    --format="value(maintenancePolicy.window.dailyMaintenanceWindow.startTime,maintenancePolicy.window.recurringWindow.window.startTime,maintenancePolicy.window.recurringWindow.window.endTime,maintenancePolicy.window.recurringWindow.recurrence)"
  
  # List maintenance exclusions
  echo "Maintenance Exclusions:"
  gcloud container clusters describe $cluster_name \
    --region=$REGION \
    --project=$PROJECT_ID \
    --format="table(maintenancePolicy.window.maintenanceExclusions[].exclusionName,maintenancePolicy.window.maintenanceExclusions[].startTime,maintenancePolicy.window.maintenanceExclusions[].endTime,maintenancePolicy.window.maintenanceExclusions[].exclusionScope)"
  
  echo ""
}

# Validate all clusters
for cluster in "${CLUSTERS[@]}"; do
  validate_cluster_policy $cluster
done

# Check for any upcoming maintenance
echo "Checking for scheduled maintenance..."
for cluster in "${CLUSTERS[@]}"; do
  echo "Cluster: $cluster"
  gcloud container operations list \
    --filter="targetLink:$cluster AND operationType=UPGRADE_MASTER" \
    --project=$PROJECT_ID \
    --format="table(name,operationType,status,startTime,endTime)"
done
```

## 6. Annual Maintenance Schedule Template

Create a calendar entry template for your compliance team:

```json
{
  "annual_maintenance_schedule_2024": {
    "allowed_windows": {
      "frequency": "Weekly",
      "days": ["Saturday", "Sunday"],
      "time_range": "02:00 UTC - 23:00 UTC",
      "timezone": "UTC"
    },
    "exclusion_periods": [
      {
        "name": "Q1 Code Freeze",
        "start": "2024-03-15T00:00:00Z",
        "end": "2024-03-31T23:59:59Z",
        "reason": "Quarterly code freeze"
      },
      {
        "name": "Q2 Code Freeze",
        "start": "2024-06-15T00:00:00Z",
        "end": "2024-06-30T23:59:59Z",
        "reason": "Quarterly code freeze"
      },
      {
        "name": "Q3 Code Freeze",
        "start": "2024-09-15T00:00:00Z",
        "end": "2024-09-30T23:59:59Z",
        "reason": "Quarterly code freeze"
      },
      {
        "name": "Annual SOX
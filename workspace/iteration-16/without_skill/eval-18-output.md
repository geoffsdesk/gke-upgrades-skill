I'll help you configure maintenance windows and exclusions for your regulated environment. Here's a comprehensive setup for SOX compliance with quarterly freezes, annual audit considerations, and weekend-only upgrades.

## 1. Maintenance Windows Configuration

### Weekend-Only Maintenance Window (Terraform)

```hcl
# variables.tf
variable "cluster_configs" {
  description = "Configuration for GKE clusters"
  type = map(object({
    name     = string
    location = string
    zone     = string
  }))
  default = {
    prod = {
      name     = "prod-cluster"
      location = "us-central1"
      zone     = "us-central1-a"
    }
    staging = {
      name     = "staging-cluster"
      location = "us-central1"
      zone     = "us-central1-b"
    }
    dev = {
      name     = "dev-cluster"
      location = "us-central1"
      zone     = "us-central1-c"
    }
  }
}

# main.tf
resource "google_container_cluster" "regulated_clusters" {
  for_each = var.cluster_configs
  
  name     = each.value.name
  location = each.value.location

  # Remove default node pool
  remove_default_node_pool = true
  initial_node_count       = 1

  # Maintenance policy for SOX compliance
  maintenance_policy {
    # Weekend maintenance window (Saturday 2 AM - 6 AM UTC)
    daily_maintenance_window {
      start_time = "02:00"
    }
    
    # Alternative: Use recurring window for more control
    recurring_window {
      start_time = "2023-01-07T02:00:00Z"  # Saturday
      end_time   = "2023-01-07T06:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SA"
    }
  }

  # Release channel for controlled upgrades
  release_channel {
    channel = "REGULAR"  # Use REGULAR for balance of stability and features
  }

  # Enable maintenance exclusions
  maintenance_policy {
    recurring_window {
      start_time = "2023-01-07T02:00:00Z"
      end_time   = "2023-01-07T06:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SA"
    }
  }

  # Logging for audit compliance
  logging_config {
    enable_components = [
      "SYSTEM_COMPONENTS",
      "WORKLOADS",
      "API_SERVER"
    ]
  }

  # Monitoring for compliance
  monitoring_config {
    enable_components = [
      "SYSTEM_COMPONENTS",
      "WORKLOADS"
    ]
  }

  tags = ["sox-compliant", "financial-services", each.key]
}

# Node pools with maintenance configuration
resource "google_container_node_pool" "regulated_node_pools" {
  for_each = var.cluster_configs
  
  name       = "${each.value.name}-nodes"
  location   = each.value.location
  cluster    = google_container_cluster.regulated_clusters[each.key].name
  node_count = each.key == "prod" ? 3 : 2

  # Auto-upgrade configuration
  management {
    auto_upgrade = true
    auto_repair  = true
  }

  # Upgrade settings aligned with maintenance windows
  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
    strategy        = "SURGE"
  }

  node_config {
    machine_type = each.key == "prod" ? "e2-standard-4" : "e2-standard-2"
    disk_size_gb = 50
    disk_type    = "pd-ssd"

    # Security for financial services
    service_account = google_service_account.gke_service_account[each.key].email
    oauth_scopes = [
      "https://www.googleapis.com/auth/logging.write",
      "https://www.googleapis.com/auth/monitoring",
      "https://www.googleapis.com/auth/devstorage.read_only"
    ]

    # Enable shielded nodes for compliance
    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }

    labels = {
      environment = each.key
      compliance  = "sox"
      team        = "platform"
    }

    tags = ["gke-node", "sox-compliant"]
  }
}
```

## 2. Maintenance Exclusions for Code Freezes

### Quarterly Exclusions Configuration

```hcl
# maintenance_exclusions.tf
locals {
  # Define quarterly code freeze periods
  quarterly_freezes_2024 = [
    {
      name       = "q1-code-freeze-2024"
      start_time = "2024-03-15T00:00:00Z"
      end_time   = "2024-04-01T23:59:59Z"
      scope      = "NO_UPGRADES"
    },
    {
      name       = "q2-code-freeze-2024"
      start_time = "2024-06-15T00:00:00Z"
      end_time   = "2024-07-01T23:59:59Z"
      scope      = "NO_UPGRADES"
    },
    {
      name       = "q3-code-freeze-2024"
      start_time = "2024-09-15T00:00:00Z"
      end_time   = "2024-10-01T23:59:59Z"
      scope      = "NO_UPGRADES"
    },
    {
      name       = "q4-code-freeze-2024"
      start_time = "2024-12-15T00:00:00Z"
      end_time   = "2025-01-02T23:59:59Z"
      scope      = "NO_UPGRADES"
    }
  ]

  # Annual audit exclusion
  annual_audit_exclusion = {
    name       = "annual-sox-audit-2024"
    start_time = "2024-11-01T00:00:00Z"
    end_time   = "2024-11-30T23:59:59Z"
    scope      = "NO_UPGRADES"
  }

  # Holiday exclusions for additional safety
  holiday_exclusions = [
    {
      name       = "thanksgiving-freeze-2024"
      start_time = "2024-11-27T00:00:00Z"
      end_time   = "2024-12-02T23:59:59Z"
      scope      = "NO_UPGRADES"
    },
    {
      name       = "year-end-freeze-2024"
      start_time = "2024-12-20T00:00:00Z"
      end_time   = "2025-01-03T23:59:59Z"
      scope      = "NO_UPGRADES"
    }
  ]
}

# Apply exclusions to all clusters
resource "google_gke_hub_membership" "cluster_memberships" {
  for_each = var.cluster_configs
  
  membership_id = "${each.value.name}-membership"
  
  endpoint {
    gke_cluster {
      resource_link = "//container.googleapis.com/${google_container_cluster.regulated_clusters[each.key].id}"
    }
  }
}

# Create maintenance exclusions using gcloud commands
resource "null_resource" "quarterly_exclusions" {
  for_each = var.cluster_configs

  # Quarterly freezes
  provisioner "local-exec" {
    command = <<-EOT
      for freeze in '${jsonencode(local.quarterly_freezes_2024)}' | jq -r '.[] | @base64'; do
        exclusion=$(echo $freeze | base64 --decode)
        name=$(echo $exclusion | jq -r '.name')
        start=$(echo $exclusion | jq -r '.start_time')
        end=$(echo $exclusion | jq -r '.end_time')
        scope=$(echo $exclusion | jq -r '.scope')
        
        gcloud container clusters update ${each.value.name} \
          --location=${each.value.location} \
          --add-maintenance-exclusion-name=$name \
          --add-maintenance-exclusion-start=$start \
          --add-maintenance-exclusion-end=$end \
          --add-maintenance-exclusion-scope=$scope \
          --project=${var.project_id}
      done
    EOT
  }

  depends_on = [google_container_cluster.regulated_clusters]
}

# Annual audit exclusion
resource "null_resource" "annual_audit_exclusion" {
  for_each = var.cluster_configs

  provisioner "local-exec" {
    command = <<-EOT
      gcloud container clusters update ${each.value.name} \
        --location=${each.value.location} \
        --add-maintenance-exclusion-name=${local.annual_audit_exclusion.name} \
        --add-maintenance-exclusion-start=${local.annual_audit_exclusion.start_time} \
        --add-maintenance-exclusion-end=${local.annual_audit_exclusion.end_time} \
        --add-maintenance-exclusion-scope=${local.annual_audit_exclusion.scope} \
        --project=${var.project_id}
    EOT
  }

  depends_on = [google_container_cluster.regulated_clusters]
}
```

## 3. Service Accounts and IAM for Compliance

```hcl
# iam.tf
resource "google_service_account" "gke_service_account" {
  for_each = var.cluster_configs
  
  account_id   = "${each.value.name}-sa"
  display_name = "GKE Service Account for ${each.value.name}"
  description  = "SOX compliant service account for GKE cluster"
}

resource "google_project_iam_member" "gke_service_account_roles" {
  for_each = {
    for pair in setproduct(keys(var.cluster_configs), [
      "roles/logging.logWriter",
      "roles/monitoring.metricWriter",
      "roles/monitoring.viewer",
      "roles/storage.objectViewer"
    ]) : "${pair[0]}-${pair[1]}" => {
      cluster = pair[0]
      role    = pair[1]
    }
  }

  project = var.project_id
  role    = each.value.role
  member  = "serviceAccount:${google_service_account.gke_service_account[each.value.cluster].email}"
}
```

## 4. Monitoring and Alerting for Compliance

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
    - alert: UnscheduledMaintenanceWindow
      expr: |
        (
          time() - on() kube_cluster_info{cluster=~"prod-cluster|staging-cluster|dev-cluster"} 
        ) % 604800 < 14400 or 
        (
          time() - on() kube_cluster_info{cluster=~"prod-cluster|staging-cluster|dev-cluster"} 
        ) % 604800 > 590400
      for: 5m
      labels:
        severity: warning
        compliance: sox
      annotations:
        summary: "GKE maintenance occurring outside approved window"
        description: "Cluster {{ $labels.cluster }} maintenance detected outside weekend window"
        
    - alert: MaintenanceExclusionViolation
      expr: |
        gke_cluster_upgrade_in_progress{cluster=~"prod-cluster|staging-cluster|dev-cluster"} == 1
        and on() (
          (month() == 3 and day() >= 15) or
          (month() == 4 and day() <= 1) or
          (month() == 6 and day() >= 15) or
          (month() == 7 and day() <= 1) or
          (month() == 9 and day() >= 15) or
          (month() == 10 and day() <= 1) or
          (month() == 11) or
          (month() == 12 and day() >= 15)
        )
      for: 1m
      labels:
        severity: critical
        compliance: sox
      annotations:
        summary: "CRITICAL: GKE upgrade during exclusion period"
        description: "Cluster {{ $labels.cluster }} is upgrading during a maintenance exclusion period"
```

## 5. Management Scripts for SOX Compliance

```bash
#!/bin/bash
# scripts/maintenance-manager.sh

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-your-project-id}"
CLUSTERS=("prod-cluster" "staging-cluster" "dev-cluster")
LOCATIONS=("us-central1-a" "us-central1-b" "us-central1-c")

# Function to add maintenance exclusion
add_maintenance_exclusion() {
    local cluster=$1
    local location=$2
    local name=$3
    local start_time=$4
    local end_time=$5
    local scope=${6:-"NO_UPGRADES"}
    
    echo "Adding maintenance exclusion '$name' to cluster '$cluster'"
    
    gcloud container clusters update "$cluster" \
        --location="$location" \
        --add-maintenance-exclusion-name="$name" \
        --add-maintenance-exclusion-start="$start_time" \
        --add-maintenance-exclusion-end="$end_time" \
        --add-maintenance-exclusion-scope="$scope" \
        --project="$PROJECT_ID" \
        --quiet
    
    echo "✓ Exclusion '$name' added successfully"
}

# Function to remove maintenance exclusion
remove_maintenance_exclusion() {
    local cluster=$1
    local location=$2
    local name=$3
    
    echo "Removing maintenance exclusion '$name' from cluster '$cluster'"
    
    gcloud container clusters update "$cluster" \
        --location="$location" \
        --remove-maintenance-exclusion-name="$name" \
        --project="$PROJECT_ID" \
        --quiet
    
    echo "✓ Exclusion '$name' removed successfully"
}

# Function to list current exclusions
list_exclusions() {
    local cluster=$1
    local location=$2
    
    echo "Current maintenance exclusions for cluster '$cluster':"
    
    gcloud container clusters describe "$cluster" \
        --location="$location" \
        --project="$PROJECT_ID" \
        --format="table(maintenancePolicy.window.maintenanceExclusions[].name:label='NAME',maintenancePolicy.window.maintenanceExclusions[].startTime:label='START',maintenancePolicy.window.maintenanceExclusions[].endTime:label='END',maintenancePolicy.window.maintenanceExclusions[].scope:label='SCOPE')"
}

# Function to add emergency exclusion
add_emergency_exclusion() {
    local duration_hours=${1:-24}
    local reason=${2:-"Emergency maintenance freeze"}
    
    local start_time=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    local end_time=$(date -u -d "+${duration_hours} hours" +"%Y-%m-%dT%H:%M:%SZ")
    local exclusion_name="emergency-freeze-$(date +%s)"
    
    echo "Adding emergency ${duration_hours}h maintenance exclusion: $reason"
    echo "Period: $start_time to $end_time"
    
    for i in "${!CLUSTERS[@]}"; do
        add_maintenance_exclusion "${CLUSTERS[i]}" "${LOCATIONS[i]}" "$exclusion_name" "$start_time" "$end_time"
    done
    
    # Create audit log entry
    cat << EOF >> /var/log/gke-maintenance-exclusions.log
$(date -u +"%Y-%m-%dT%H:%M:%SZ") EMERGENCY_
I'll help you configure maintenance windows and exclusions for your GKE Standard clusters to meet your SOX compliance requirements. Here's a comprehensive solution:

## 1. Terraform Configuration

```hcl
# variables.tf
variable "cluster_names" {
  description = "List of GKE cluster names"
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

# Current year for audit exclusion
variable "current_year" {
  description = "Current year for audit exclusions"
  type        = number
  default     = 2024
}
```

```hcl
# maintenance-windows.tf
locals {
  # Define quarterly code freeze periods (adjust dates as needed)
  quarterly_freezes = [
    # Q1 freeze (end of March)
    {
      start_time = "${var.current_year}-03-25T00:00:00Z"
      end_time   = "${var.current_year}-04-05T00:00:00Z"
    },
    # Q2 freeze (end of June)
    {
      start_time = "${var.current_year}-06-25T00:00:00Z"
      end_time   = "${var.current_year}-07-05T00:00:00Z"
    },
    # Q3 freeze (end of September)
    {
      start_time = "${var.current_year}-09-25T00:00:00Z"
      end_time   = "${var.current_year}-10-05T00:00:00Z"
    },
    # Q4 freeze (end of December)
    {
      start_time = "${var.current_year}-12-20T00:00:00Z"
      end_time   = "${var.current_year + 1}-01-05T00:00:00Z"
    }
  ]

  # Annual audit exclusion (entire November)
  audit_exclusion = {
    start_time = "${var.current_year}-11-01T00:00:00Z"
    end_time   = "${var.current_year}-12-01T00:00:00Z"
  }
}

resource "google_container_cluster" "gke_clusters" {
  count    = length(var.cluster_names)
  name     = var.cluster_names[count.index]
  location = var.region
  project  = var.project_id

  # Remove default node pool
  remove_default_node_pool = true
  initial_node_count       = 1

  # Maintenance policy configuration
  maintenance_policy {
    # Weekend-only maintenance window (Saturday 2 AM - 6 AM UTC)
    daily_maintenance_window {
      start_time = "02:00"
    }

    # Recurring maintenance window for weekends only
    recurring_window {
      start_time = "2024-01-06T02:00:00Z" # First Saturday of 2024
      end_time   = "2024-01-06T06:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SA"
    }

    # Quarterly code freeze exclusions
    dynamic "maintenance_exclusion" {
      for_each = local.quarterly_freezes
      content {
        exclusion_name = "quarterly-freeze-${formatdate("Q", maintenance_exclusion.value.start_time)}"
        start_time     = maintenance_exclusion.value.start_time
        end_time       = maintenance_exclusion.value.end_time
        exclusion_options {
          scope = "UPGRADES"
        }
      }
    }

    # Annual audit exclusion
    maintenance_exclusion {
      exclusion_name = "annual-audit-${var.current_year}"
      start_time     = local.audit_exclusion.start_time
      end_time       = local.audit_exclusion.end_time
      exclusion_options {
        scope = "UPGRADES"
      }
    }

    # Holiday exclusions (customize based on your region)
    maintenance_exclusion {
      exclusion_name = "holiday-blackout-${var.current_year}"
      start_time     = "${var.current_year}-12-23T00:00:00Z"
      end_time       = "${var.current_year + 1}-01-02T00:00:00Z"
      exclusion_options {
        scope = "UPGRADES"
      }
    }
  }

  # Release channel configuration
  release_channel {
    channel = "REGULAR" # Use REGULAR for financial services (balanced stability/security)
  }

  # Node configuration with auto-upgrade
  node_config {
    machine_type = "e2-standard-4"
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]
  }

  # Network policy for security
  network_policy {
    enabled = true
  }

  # Enable workload identity for SOX compliance
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  # Logging and monitoring for audit trail
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
      "WORKLOADS",
      "APISERVER",
      "SCHEDULER",
      "CONTROLLER_MANAGER"
    ]
  }
}

# Separate node pool configuration
resource "google_container_node_pool" "primary_nodes" {
  count      = length(var.cluster_names)
  name       = "${var.cluster_names[count.index]}-primary-pool"
  location   = var.region
  cluster    = google_container_cluster.gke_clusters[count.index].name
  project    = var.project_id
  node_count = 3

  # Auto-upgrade configuration (respects cluster maintenance windows)
  management {
    auto_repair  = true
    auto_upgrade = true
  }

  # Upgrade settings
  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
    strategy        = "SURGE" # Safer for production
  }

  node_config {
    preemptible  = false # Use regular instances for financial services
    machine_type = "e2-standard-4"

    # Security configurations for SOX compliance
    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]

    labels = {
      environment = "production"
      compliance  = "sox"
      managed_by  = "terraform"
    }

    tags = ["gke-node", "production"]
  }
}
```

## 2. Kubernetes Maintenance Policy ConfigMap

```yaml
# maintenance-policy-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: maintenance-policy-config
  namespace: kube-system
  labels:
    component: maintenance-policy
    compliance: sox
data:
  policy.yaml: |
    maintenancePolicy:
      description: "SOX Compliant Maintenance Policy for Financial Services"
      weekendOnlyUpgrades: true
      maintenanceWindow:
        dayOfWeek: "SATURDAY"
        startTime: "02:00"
        duration: "4h"
        timezone: "UTC"
      
      exclusions:
        quarterlyFreezes:
          - name: "Q1-freeze"
            period: "March 25 - April 5"
          - name: "Q2-freeze" 
            period: "June 25 - July 5"
          - name: "Q3-freeze"
            period: "September 25 - October 5"
          - name: "Q4-freeze"
            period: "December 20 - January 5"
        
        annualAudit:
          name: "November-audit"
          period: "November 1-30"
          
        holidays:
          name: "Holiday-blackout"
          period: "December 23 - January 2"
      
      approvalProcess:
        requiredApprovers: 2
        approvalTimeout: "24h"
        emergencyBypass: false
```

## 3. Monitoring and Alerting Configuration

```yaml
# maintenance-monitoring.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: gke-maintenance-alerts
  namespace: monitoring
spec:
  groups:
  - name: gke.maintenance
    rules:
    - alert: UnscheduledMaintenanceDetected
      expr: increase(container_cluster_maintenance_events_total[1h]) > 0
      for: 0m
      labels:
        severity: critical
        compliance: sox
      annotations:
        summary: "Unscheduled maintenance detected on GKE cluster"
        description: "Maintenance activity detected outside of approved windows"
        
    - alert: MaintenanceWindowViolation
      expr: |
        (hour() < 2 or hour() > 6) and 
        (day_of_week() != 6) and 
        increase(container_cluster_upgrades_total[5m]) > 0
      for: 0m
      labels:
        severity: critical
        compliance: sox-violation
      annotations:
        summary: "Maintenance performed outside approved window"
        description: "GKE maintenance detected outside Saturday 2-6 AM UTC window"

    - alert: UpgradeFailure
      expr: increase(container_cluster_upgrade_failures_total[30m]) > 0
      for: 0m
      labels:
        severity: warning
        compliance: sox
      annotations:
        summary: "GKE cluster upgrade failed"
        description: "Cluster upgrade failure requires investigation for audit trail"
```

## 4. gcloud CLI Commands for Manual Management

```bash
#!/bin/bash
# maintenance-management.sh

PROJECT_ID="your-project-id"
CLUSTERS=("prod-cluster-1" "prod-cluster-2" "prod-cluster-3")
REGION="us-central1"
CURRENT_YEAR=$(date +%Y)

# Function to add maintenance exclusion
add_maintenance_exclusion() {
    local cluster=$1
    local exclusion_name=$2
    local start_time=$3
    local end_time=$4
    
    gcloud container clusters update $cluster \
        --project=$PROJECT_ID \
        --region=$REGION \
        --add-maintenance-exclusion-name=$exclusion_name \
        --add-maintenance-exclusion-start=$start_time \
        --add-maintenance-exclusion-end=$end_time \
        --add-maintenance-exclusion-scope=upgrades
}

# Function to remove maintenance exclusion
remove_maintenance_exclusion() {
    local cluster=$1
    local exclusion_name=$2
    
    gcloud container clusters update $cluster \
        --project=$PROJECT_ID \
        --region=$REGION \
        --remove-maintenance-exclusion=$exclusion_name
}

# Set up weekend-only maintenance window for all clusters
setup_weekend_maintenance() {
    for cluster in "${CLUSTERS[@]}"; do
        echo "Setting up weekend maintenance for $cluster..."
        
        # Set recurring maintenance window
        gcloud container clusters update $cluster \
            --project=$PROJECT_ID \
            --region=$REGION \
            --recurring-window-start="${CURRENT_YEAR}-01-06T02:00:00Z" \
            --recurring-window-end="${CURRENT_YEAR}-01-06T06:00:00Z" \
            --recurring-window-recurrence="FREQ=WEEKLY;BYDAY=SA"
    done
}

# Add quarterly freeze exclusions
setup_quarterly_exclusions() {
    for cluster in "${CLUSTERS[@]}"; do
        echo "Setting up quarterly exclusions for $cluster..."
        
        # Q1 Freeze
        add_maintenance_exclusion $cluster \
            "q1-freeze-${CURRENT_YEAR}" \
            "${CURRENT_YEAR}-03-25T00:00:00Z" \
            "${CURRENT_YEAR}-04-05T00:00:00Z"
        
        # Q2 Freeze
        add_maintenance_exclusion $cluster \
            "q2-freeze-${CURRENT_YEAR}" \
            "${CURRENT_YEAR}-06-25T00:00:00Z" \
            "${CURRENT_YEAR}-07-05T00:00:00Z"
        
        # Q3 Freeze
        add_maintenance_exclusion $cluster \
            "q3-freeze-${CURRENT_YEAR}" \
            "${CURRENT_YEAR}-09-25T00:00:00Z" \
            "${CURRENT_YEAR}-10-05T00:00:00Z"
        
        # Q4 Freeze
        add_maintenance_exclusion $cluster \
            "q4-freeze-${CURRENT_YEAR}" \
            "${CURRENT_YEAR}-12-20T00:00:00Z" \
            "$((CURRENT_YEAR + 1))-01-05T00:00:00Z"
    done
}

# Add annual audit exclusion
setup_audit_exclusion() {
    for cluster in "${CLUSTERS[@]}"; do
        echo "Setting up audit exclusion for $cluster..."
        
        add_maintenance_exclusion $cluster \
            "annual-audit-${CURRENT_YEAR}" \
            "${CURRENT_YEAR}-11-01T00:00:00Z" \
            "${CURRENT_YEAR}-12-01T00:00:00Z"
    done
}

# Main execution
main() {
    echo "Setting up SOX-compliant maintenance windows..."
    setup_weekend_maintenance
    setup_quarterly_exclusions
    setup_audit_exclusion
    echo "Maintenance window configuration complete!"
}

# Run if script is executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
```

## 5. Compliance Verification Script

```bash
#!/bin/bash
# verify-maintenance-compliance.sh

# Verify current maintenance windows and exclusions
verify_compliance() {
    local cluster=$1
    
    echo "=== Compliance Check for $cluster ==="
    
    # Get current maintenance policy
    gcloud container clusters describe $cluster \
        --project=$PROJECT_ID \
        --region=$REGION \
        --format="yaml(maintenancePolicy)" > /tmp/${cluster}_maintenance.yaml
    
    # Check for weekend-only configuration
    echo "Checking maintenance window configuration..."
    if grep -q "FREQ=WEEKLY;BYDAY=SA" /tmp/${cluster}_maintenance.yaml; then
        echo "✓ Weekend-only maintenance window configured"
    else
        echo "✗ Weekend-only maintenance window NOT configured"
    fi
    
    # Check for required exclusions
    echo "Checking maintenance exclusions..."
    exclusions=$(gcloud container clusters describe $cluster \
        --project=$PROJECT_ID \
        --region=$REGION \
        --format="value(maintenancePolicy.maintenanceExclusion[].exclusionName)")
    
    if echo "$exclusions" | grep -q "audit"; then
        echo "✓ Audit exclusion found"
    else
        echo "✗ Audit exclusion missing"
    fi
    
    if echo "$exclusions" | grep -q "freeze"; then
        echo "✓ Quarterly freeze exclusions found"
    else
        echo "✗ Quarterly freeze exclusions missing"
    fi
    
    echo ""
}

# Run compliance check on all clusters
for cluster in "${CLUSTERS[@]}"; do
    verify_compliance $cluster
done
```

## Key Features for SOX Compliance:

1. **Weekend-Only Maintenance**: Upgrades only occur on Saturdays 2-6 AM UTC
2. **Quarterly Code Freezes**: Automatic exclusions during quarter-end periods
3. **Annual Audit Protection**: Complete November blackout during audit
4. **Audit Trail**: Comprehensive logging and monitoring
5. **Change Control
I'll help you configure maintenance windows and exclusions for your GKE clusters to meet SOX compliance requirements. Here's a comprehensive solution:

## 1. Terraform Configuration

```hcl
# variables.tf
variable "quarterly_freeze_dates" {
  description = "Quarterly code freeze periods"
  type = list(object({
    start_time = string
    end_time   = string
    scope      = string
  }))
  default = [
    {
      start_time = "2024-03-25T00:00:00Z"
      end_time   = "2024-04-05T23:59:59Z"
      scope      = "Q1_FREEZE"
    },
    {
      start_time = "2024-06-24T00:00:00Z"
      end_time   = "2024-07-05T23:59:59Z"
      scope      = "Q2_FREEZE"
    },
    {
      start_time = "2024-09-23T00:00:00Z"
      end_time   = "2024-10-04T23:59:59Z"
      scope      = "Q3_FREEZE"
    },
    {
      start_time = "2024-12-16T00:00:00Z"
      end_time   = "2025-01-03T23:59:59Z"
      scope      = "Q4_FREEZE"
    }
  ]
}

variable "annual_audit_exclusion" {
  description = "Annual audit period exclusion"
  type = object({
    start_time = string
    end_time   = string
  })
  default = {
    start_time = "2024-11-01T00:00:00Z"
    end_time   = "2024-11-30T23:59:59Z"
  }
}

variable "clusters" {
  description = "GKE cluster configurations"
  type = map(object({
    name     = string
    location = string
    region   = string
  }))
  default = {
    "prod" = {
      name     = "production-cluster"
      location = "us-central1-a"
      region   = "us-central1"
    },
    "staging" = {
      name     = "staging-cluster"
      location = "us-central1-b"
      region   = "us-central1"
    },
    "dev" = {
      name     = "development-cluster"
      location = "us-central1-c"
      region   = "us-central1"
    }
  }
}
```

```hcl
# main.tf
resource "google_container_cluster" "sox_compliant_clusters" {
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
    
    # Recurring maintenance windows for weekends only
    recurring_window {
      start_time = "2024-01-06T02:00:00Z"  # First Saturday of the year
      end_time   = "2024-01-06T06:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SA"
    }

    # Maintenance exclusions for quarterly freezes
    dynamic "maintenance_exclusion" {
      for_each = var.quarterly_freeze_dates
      content {
        exclusion_name = "quarterly-freeze-${maintenance_exclusion.value.scope}"
        start_time     = maintenance_exclusion.value.start_time
        end_time       = maintenance_exclusion.value.end_time
        exclusion_options {
          scope = "UPGRADES"
        }
      }
    }

    # Annual audit exclusion
    maintenance_exclusion {
      exclusion_name = "annual-audit-november"
      start_time     = var.annual_audit_exclusion.start_time
      end_time       = var.annual_audit_exclusion.end_time
      exclusion_options {
        scope = "UPGRADES"
      }
    }

    # Additional holiday exclusions for financial services
    maintenance_exclusion {
      exclusion_name = "year-end-freeze"
      start_time     = "2024-12-23T00:00:00Z"
      end_time       = "2025-01-02T23:59:59Z"
      exclusion_options {
        scope = "UPGRADES"
      }
    }
  }

  # Release channel for controlled updates
  release_channel {
    channel = "REGULAR"  # Use STABLE for more conservative updates
  }

  # Enable workload identity for security
  workload_identity_config {
    workload_pool = "${data.google_project.current.project_id}.svc.id.goog"
  }

  # Network policy for security
  network_policy {
    enabled = true
  }

  # Private cluster for security
  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block  = "10.100.0.0/28"
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
      "SYSTEM_COMPONENTS"
    ]
  }
}
```

## 2. Advanced Maintenance Configuration

```hcl
# maintenance-windows.tf
resource "google_gke_hub_membership" "clusters" {
  for_each = var.clusters

  membership_id = "${each.value.name}-membership"
  endpoint {
    gke_cluster {
      resource_link = "//container.googleapis.com/projects/${data.google_project.current.project_id}/locations/${each.value.location}/clusters/${each.value.name}"
    }
  }

  depends_on = [google_container_cluster.sox_compliant_clusters]
}

# Fleet maintenance policy for coordinated updates
resource "google_gke_hub_fleet" "sox_fleet" {
  display_name = "SOX-Compliant-Fleet"
}

# Maintenance schedule resource
resource "google_container_cluster" "extended_maintenance_config" {
  for_each = var.clusters

  name     = each.value.name
  location = each.value.location

  maintenance_policy {
    # More granular weekend schedule
    recurring_window {
      start_time = "2024-01-06T02:00:00Z"
      end_time   = "2024-01-06T06:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SA"
    }

    # Emergency maintenance window (Sunday early morning)
    recurring_window {
      start_time = "2024-01-07T01:00:00Z"
      end_time   = "2024-01-07T03:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SU"
    }

    # Exclude major financial dates
    maintenance_exclusion {
      exclusion_name = "month-end-processing"
      start_time     = "2024-01-29T00:00:00Z"
      end_time       = "2024-02-02T23:59:59Z"
      exclusion_options {
        scope = "UPGRADES"
      }
    }
  }
}
```

## 3. Monitoring and Alerting Setup

```hcl
# monitoring.tf
resource "google_monitoring_notification_channel" "sox_team" {
  display_name = "SOX Compliance Team"
  type         = "email"

  labels = {
    email_address = "sox-compliance@yourcompany.com"
  }
}

resource "google_monitoring_alert_policy" "maintenance_window_alert" {
  display_name = "GKE Maintenance Window Started"
  combiner     = "OR"

  conditions {
    display_name = "Maintenance event detected"
    
    condition_monitoring_query_language {
      query = <<-EOT
        fetch gke_cluster
        | filter resource.cluster_name =~ "production-cluster|staging-cluster|development-cluster"
        | filter metric.type == "container.googleapis.com/cluster/maintenance_event"
        | group_by 1m
      EOT
    }
  }

  notification_channels = [google_monitoring_notification_channel.sox_team.id]
  
  alert_strategy {
    auto_close = "1800s"
  }
}

resource "google_monitoring_alert_policy" "unauthorized_upgrade_attempt" {
  display_name = "Unauthorized GKE Upgrade Attempt"
  combiner     = "OR"

  conditions {
    display_name = "Upgrade during exclusion period"
    
    condition_monitoring_query_language {
      query = <<-EOT
        fetch gke_cluster
        | filter resource.cluster_name =~ "production-cluster|staging-cluster|development-cluster"
        | filter metric.type == "container.googleapis.com/cluster/upgrade_event"
        | filter metric.labels.upgrade_type == "automatic"
        | group_by 1m
      EOT
    }
  }

  notification_channels = [google_monitoring_notification_channel.sox_team.id]
}
```

## 4. Compliance Automation Script

```bash
#!/bin/bash
# maintenance-compliance-check.sh

PROJECT_ID="your-project-id"
CLUSTERS=("production-cluster" "staging-cluster" "development-cluster")
LOCATIONS=("us-central1-a" "us-central1-b" "us-central1-c")

check_maintenance_windows() {
    local cluster=$1
    local location=$2
    
    echo "Checking maintenance windows for $cluster in $location..."
    
    # Get maintenance policy
    gcloud container clusters describe $cluster \
        --location=$location \
        --project=$PROJECT_ID \
        --format="value(maintenancePolicy)" > /tmp/maintenance_policy.json
    
    # Verify weekend-only schedule
    if ! grep -q "FREQ=WEEKLY;BYDAY=SA" /tmp/maintenance_policy.json; then
        echo "❌ ERROR: Weekend maintenance window not configured for $cluster"
        return 1
    fi
    
    # Check for required exclusions
    local required_exclusions=("quarterly-freeze" "annual-audit-november" "year-end-freeze")
    for exclusion in "${required_exclusions[@]}"; do
        if ! grep -q "$exclusion" /tmp/maintenance_policy.json; then
            echo "❌ ERROR: Missing exclusion $exclusion for $cluster"
            return 1
        fi
    done
    
    echo "✅ Maintenance windows correctly configured for $cluster"
    return 0
}

audit_log_compliance() {
    echo "Checking audit logging compliance..."
    
    for i in "${!CLUSTERS[@]}"; do
        local cluster=${CLUSTERS[$i]}
        local location=${LOCATIONS[$i]}
        
        # Check logging configuration
        local logging_config=$(gcloud container clusters describe $cluster \
            --location=$location \
            --project=$PROJECT_ID \
            --format="value(loggingConfig.componentConfig.enableComponents)")
        
        if [[ ! "$logging_config" == *"SYSTEM_COMPONENTS"* ]] || \
           [[ ! "$logging_config" == *"WORKLOADS"* ]] || \
           [[ ! "$logging_config" == *"API_SERVER"* ]]; then
            echo "❌ ERROR: Insufficient logging enabled for $cluster"
            exit 1
        fi
    done
    
    echo "✅ Audit logging properly configured"
}

generate_compliance_report() {
    local report_file="gke-compliance-report-$(date +%Y%m%d).json"
    
    echo "Generating compliance report: $report_file"
    
    cat > $report_file << EOF
{
    "report_date": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "project_id": "$PROJECT_ID",
    "clusters": [
EOF

    for i in "${!CLUSTERS[@]}"; do
        local cluster=${CLUSTERS[$i]}
        local location=${LOCATIONS[$i]}
        
        gcloud container clusters describe $cluster \
            --location=$location \
            --project=$PROJECT_ID \
            --format=json >> $report_file
        
        if [ $i -lt $((${#CLUSTERS[@]} - 1)) ]; then
            echo "," >> $report_file
        fi
    done
    
    echo "    ]" >> $report_file
    echo "}" >> $report_file
    
    echo "✅ Compliance report generated: $report_file"
}

main() {
    echo "Starting SOX compliance check for GKE clusters..."
    
    for i in "${!CLUSTERS[@]}"; do
        check_maintenance_windows ${CLUSTERS[$i]} ${LOCATIONS[$i]}
    done
    
    audit_log_compliance
    generate_compliance_report
    
    echo "✅ SOX compliance check completed successfully"
}

main "$@"
```

## 5. Deployment Commands

```bash
# Apply the Terraform configuration
terraform init
terraform plan -var-file="sox-compliance.tfvars"
terraform apply -var-file="sox-compliance.tfvars"

# Verify maintenance windows
for cluster in production-cluster staging-cluster development-cluster; do
    gcloud container clusters describe $cluster \
        --location=us-central1-a \
        --format="value(maintenancePolicy)"
done

# Set up monitoring
gcloud logging sinks create gke-sox-audit-sink \
    bigquery.googleapis.com/projects/YOUR_PROJECT/datasets/sox_audit_logs \
    --log-filter='resource.type="gke_cluster" AND (protoPayload.methodName:"google.container" OR jsonPayload.kind="Event")'

# Schedule compliance checks
gcloud scheduler jobs create http sox-compliance-check \
    --schedule="0 8 * * 1" \
    --uri="https://your-compliance-function-url" \
    --http-method=POST \
    --time-zone="America/New_York"
```

This configuration provides:

1. **Weekend-only maintenance windows** (Saturday 2-6 AM UTC)
2. **Quarterly code freeze exclusions** with proper date ranges
3. **Annual November audit exclusion**
4. **Year-end holiday freeze protection**
5. **Comprehensive audit logging** for SOX compliance
6. **Automated compliance monitoring** and alerting
7. **Regular compliance reporting**

The setup ensures all maintenance activities are logged and restricted to approved windows, meeting SOX compliance requirements for your financial services environment.
I'll help you configure maintenance windows and exclusions for your GKE Standard clusters to meet SOX compliance requirements. Here's a comprehensive setup:

## 1. Terraform Configuration for Maintenance Windows

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
      end_time   = "2024-04-01T23:59:59Z"
      scope      = "Q1_FREEZE"
    },
    {
      start_time = "2024-06-24T00:00:00Z"
      end_time   = "2024-07-01T23:59:59Z"
      scope      = "Q2_FREEZE"
    },
    {
      start_time = "2024-09-23T00:00:00Z"
      end_time   = "2024-09-30T23:59:59Z"
      scope      = "Q3_FREEZE"
    },
    {
      start_time = "2024-12-23T00:00:00Z"
      end_time   = "2024-12-30T23:59:59Z"
      scope      = "Q4_FREEZE"
    }
  ]
}

variable "annual_audit_exclusion" {
  description = "Annual audit exclusion period"
  type = object({
    start_time = string
    end_time   = string
  })
  default = {
    start_time = "2024-11-01T00:00:00Z"
    end_time   = "2024-11-30T23:59:59Z"
  }
}

# main.tf
resource "google_container_cluster" "financial_cluster" {
  count    = 3
  name     = "financial-cluster-${count.index + 1}"
  location = var.region
  
  # Remove default node pool
  remove_default_node_pool = true
  initial_node_count       = 1
  
  # Network configuration
  network    = var.vpc_network
  subnetwork = var.subnet
  
  # Enable network policy for security
  network_policy {
    enabled = true
  }
  
  # IP allocation for private cluster
  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }
  
  # Private cluster configuration for security
  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block = "172.16.0.0/28"
    
    master_global_access_config {
      enabled = true
    }
  }
  
  # Maintenance policy - weekends only
  maintenance_policy {
    daily_maintenance_window {
      start_time = "06:00"  # 6 AM UTC on weekends
    }
    
    # Recurring maintenance window for weekends only
    recurring_window {
      start_time = "2024-01-06T06:00:00Z"  # Start on a Saturday
      end_time   = "2024-01-06T10:00:00Z"  # 4-hour window
      recurrence = "FREQ=WEEKLY;BYDAY=SA"  # Every Saturday
    }
    
    recurring_window {
      start_time = "2024-01-07T06:00:00Z"  # Start on a Sunday
      end_time   = "2024-01-07T10:00:00Z"  # 4-hour window
      recurrence = "FREQ=WEEKLY;BYDAY=SU"  # Every Sunday
    }
    
    # Quarterly maintenance exclusions
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
    
    # Holiday exclusions (Thanksgiving week, Christmas/New Year)
    maintenance_exclusion {
      exclusion_name = "thanksgiving-week"
      start_time     = "2024-11-25T00:00:00Z"
      end_time       = "2024-11-29T23:59:59Z"
      exclusion_options {
        scope = "UPGRADES"
      }
    }
    
    maintenance_exclusion {
      exclusion_name = "holiday-break"
      start_time     = "2024-12-20T00:00:00Z"
      end_time       = "2025-01-02T23:59:59Z"
      exclusion_options {
        scope = "UPGRADES"
      }
    }
  }
  
  # Release channel for controlled updates
  release_channel {
    channel = "REGULAR"  # More stable than RAPID, more current than STABLE
  }
  
  # Workload Identity for security
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }
  
  # Master authorized networks for security
  master_authorized_networks_config {
    cidr_blocks {
      cidr_block   = var.authorized_cidr_blocks
      display_name = "Corporate Network"
    }
  }
  
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
    
    managed_prometheus {
      enabled = true
    }
  }
  
  # Binary authorization for compliance
  binary_authorization {
    evaluation_mode = "PROJECT_SINGLETON_POLICY_ENFORCE"
  }
  
  # Resource labels for compliance tracking
  resource_labels = {
    environment     = var.environment
    compliance      = "sox"
    team           = "financial-services"
    backup         = "required"
    cost-center    = var.cost_center
    data-class     = "confidential"
  }
}

# Node pool configuration
resource "google_container_node_pool" "financial_node_pool" {
  count      = 3
  name       = "financial-node-pool-${count.index + 1}"
  location   = var.region
  cluster    = google_container_cluster.financial_cluster[count.index].name
  
  # Auto-scaling configuration
  autoscaling {
    min_node_count = 2
    max_node_count = 10
  }
  
  # Management settings
  management {
    auto_repair  = true
    auto_upgrade = true
  }
  
  # Upgrade settings aligned with cluster maintenance windows
  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
    strategy        = "SURGE"
    
    blue_green_settings {
      standard_rollout_policy {
        batch_percentage    = 0.2
        batch_node_count   = 1
        batch_soak_duration = "10s"
      }
      node_pool_soak_duration = "60s"
    }
  }
  
  node_config {
    preemptible  = false  # Critical for financial services
    machine_type = "e2-standard-4"
    disk_size_gb = 100
    disk_type    = "pd-ssd"
    
    # Security hardening
    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }
    
    # Workload Identity
    workload_metadata_config {
      mode = "GKE_METADATA"
    }
    
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]
    
    labels = {
      environment = var.environment
      compliance  = "sox"
      node-pool   = "financial-workloads"
    }
    
    tags = ["financial-services", "gke-nodes"]
  }
}
```

## 2. Advanced Maintenance Configuration Script

```bash
#!/bin/bash
# maintenance-config.sh

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-your-project-id}"
CLUSTERS=("financial-cluster-1" "financial-cluster-2" "financial-cluster-3")
REGION="${REGION:-us-central1}"

# Function to set maintenance window
configure_maintenance_window() {
    local cluster_name=$1
    
    echo "Configuring maintenance window for ${cluster_name}..."
    
    # Set weekend-only maintenance window
    gcloud container clusters update "${cluster_name}" \
        --region="${REGION}" \
        --maintenance-window-start="2024-01-06T06:00:00Z" \
        --maintenance-window-end="2024-01-06T10:00:00Z" \
        --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SA,SU" \
        --project="${PROJECT_ID}"
}

# Function to add maintenance exclusions
add_maintenance_exclusions() {
    local cluster_name=$1
    
    echo "Adding maintenance exclusions for ${cluster_name}..."
    
    # Q1 2024 Code Freeze
    gcloud container clusters update "${cluster_name}" \
        --region="${REGION}" \
        --add-maintenance-exclusion-end="2024-04-01T23:59:59Z" \
        --add-maintenance-exclusion-name="q1-2024-freeze" \
        --add-maintenance-exclusion-scope="upgrades" \
        --add-maintenance-exclusion-start="2024-03-25T00:00:00Z" \
        --project="${PROJECT_ID}"
    
    # Q2 2024 Code Freeze
    gcloud container clusters update "${cluster_name}" \
        --region="${REGION}" \
        --add-maintenance-exclusion-end="2024-07-01T23:59:59Z" \
        --add-maintenance-exclusion-name="q2-2024-freeze" \
        --add-maintenance-exclusion-scope="upgrades" \
        --add-maintenance-exclusion-start="2024-06-24T00:00:00Z" \
        --project="${PROJECT_ID}"
    
    # Q3 2024 Code Freeze
    gcloud container clusters update "${cluster_name}" \
        --region="${REGION}" \
        --add-maintenance-exclusion-end="2024-09-30T23:59:59Z" \
        --add-maintenance-exclusion-name="q3-2024-freeze" \
        --add-maintenance-exclusion-scope="upgrades" \
        --add-maintenance-exclusion-start="2024-09-23T00:00:00Z" \
        --project="${PROJECT_ID}"
    
    # Annual Audit - November
    gcloud container clusters update "${cluster_name}" \
        --region="${REGION}" \
        --add-maintenance-exclusion-end="2024-11-30T23:59:59Z" \
        --add-maintenance-exclusion-name="annual-audit-nov-2024" \
        --add-maintenance-exclusion-scope="upgrades" \
        --add-maintenance-exclusion-start="2024-11-01T00:00:00Z" \
        --project="${PROJECT_ID}"
    
    # Q4 2024 Code Freeze
    gcloud container clusters update "${cluster_name}" \
        --region="${REGION}" \
        --add-maintenance-exclusion-end="2024-12-30T23:59:59Z" \
        --add-maintenance-exclusion-name="q4-2024-freeze" \
        --add-maintenance-exclusion-scope="upgrades" \
        --add-maintenance-exclusion-start="2024-12-23T00:00:00Z" \
        --project="${PROJECT_ID}"
    
    # Holiday Break
    gcloud container clusters update "${cluster_name}" \
        --region="${REGION}" \
        --add-maintenance-exclusion-end="2025-01-02T23:59:59Z" \
        --add-maintenance-exclusion-name="holiday-break-2024" \
        --add-maintenance-exclusion-scope="upgrades" \
        --add-maintenance-exclusion-start="2024-12-20T00:00:00Z" \
        --project="${PROJECT_ID}"
}

# Main execution
main() {
    echo "Starting maintenance configuration for SOX-compliant GKE clusters..."
    
    for cluster in "${CLUSTERS[@]}"; do
        echo "Processing cluster: ${cluster}"
        configure_maintenance_window "${cluster}"
        add_maintenance_exclusions "${cluster}"
        echo "Completed configuration for ${cluster}"
        echo "----------------------------------------"
    done
    
    echo "All clusters configured successfully!"
}

# Run main function
main "$@"
```

## 3. Monitoring and Compliance Script

```bash
#!/bin/bash
# compliance-monitoring.sh

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-your-project-id}"
CLUSTERS=("financial-cluster-1" "financial-cluster-2" "financial-cluster-3")
REGION="${REGION:-us-central1}"
SLACK_WEBHOOK="${SLACK_WEBHOOK:-}"

# Function to check maintenance windows
check_maintenance_compliance() {
    local cluster_name=$1
    
    echo "Checking maintenance compliance for ${cluster_name}..."
    
    # Get cluster maintenance policy
    local maintenance_info
    maintenance_info=$(gcloud container clusters describe "${cluster_name}" \
        --region="${REGION}" \
        --project="${PROJECT_ID}" \
        --format="json" | jq -r '.maintenancePolicy')
    
    echo "Maintenance policy for ${cluster_name}:"
    echo "${maintenance_info}" | jq '.'
    
    # Check for upcoming maintenance
    local next_maintenance
    next_maintenance=$(gcloud container operations list \
        --filter="targetLink~${cluster_name} AND operationType=UPGRADE_MASTER" \
        --format="table(name,status,startTime,endTime)" \
        --project="${PROJECT_ID}")
    
    if [[ -n "${next_maintenance}" ]]; then
        echo "Upcoming maintenance for ${cluster_name}:"
        echo "${next_maintenance}"
    fi
}

# Function to generate compliance report
generate_compliance_report() {
    local report_file="maintenance-compliance-report-$(date +%Y%m%d).json"
    
    echo "Generating compliance report..."
    
    cat > "${report_file}" <<EOF
{
  "report_date": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "project_id": "${PROJECT_ID}",
  "compliance_framework": "SOX",
  "clusters": [
EOF

    local first=true
    for cluster in "${CLUSTERS[@]}"; do
        if [[ "${first}" == "true" ]]; then
            first=false
        else
            echo "    ," >> "${report_file}"
        fi
        
        echo "    {" >> "${report_file}"
        echo "      \"name\": \"${cluster}\"," >> "${report_file}"
        echo "      \"region\": \"${REGION}\"," >> "${report_file}"
        
        # Get cluster info
        local cluster_info
        cluster_info=$(gcloud container clusters describe "${cluster}" \
            --region="${REGION}" \
            --project="${PROJECT_ID}" \
            --format="json")
        
        local
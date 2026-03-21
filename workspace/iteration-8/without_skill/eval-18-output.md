I'll help you set up maintenance windows and exclusions for your GKE Standard clusters to meet your SOX compliance requirements. Here's a comprehensive configuration:

## 1. Terraform Configuration

```hcl
# terraform/gke-maintenance.tf

# Data source for quarterly code freeze dates (you'll need to update these)
locals {
  # Update these dates for your specific quarters
  quarterly_freezes = {
    q1_2024 = {
      start = "2024-03-15T00:00:00Z"
      end   = "2024-03-31T23:59:59Z"
    }
    q2_2024 = {
      start = "2024-06-15T00:00:00Z"
      end   = "2024-06-30T23:59:59Z"
    }
    q3_2024 = {
      start = "2024-09-15T00:00:00Z"
      end   = "2024-09-30T23:59:59Z"
    }
    q4_2024 = {
      start = "2024-12-15T00:00:00Z"
      end   = "2024-12-31T23:59:59Z"
    }
  }
  
  # Annual audit exclusion (November)
  annual_audit_2024 = {
    start = "2024-11-01T00:00:00Z"
    end   = "2024-11-30T23:59:59Z"
  }
  
  cluster_names = ["prod-cluster-1", "prod-cluster-2", "prod-cluster-3"]
}

# GKE clusters with maintenance configuration
resource "google_container_cluster" "production_clusters" {
  count    = length(local.cluster_names)
  name     = local.cluster_names[count.index]
  location = var.cluster_zones[count.index]

  # Remove default node pool
  remove_default_node_pool = true
  initial_node_count       = 1

  # Network configuration
  network    = var.vpc_network
  subnetwork = var.subnet

  # Maintenance policy - weekends only (Saturday 2 AM UTC)
  maintenance_policy {
    recurring_window {
      start_time = "2024-01-06T02:00:00Z"  # First Saturday of 2024
      end_time   = "2024-01-06T06:00:00Z"  # 4-hour window
      recurrence = "FREQ=WEEKLY;BYDAY=SA"   # Every Saturday
    }

    # Maintenance exclusions for compliance
    dynamic "maintenance_exclusion" {
      for_each = local.quarterly_freezes
      content {
        exclusion_name = "quarterly-freeze-${maintenance_exclusion.key}"
        start_time     = maintenance_exclusion.value.start
        end_time       = maintenance_exclusion.value.end
        exclusion_options {
          scope = "ALL_UPGRADES"
        }
      }
    }

    # Annual audit exclusion
    maintenance_exclusion {
      exclusion_name = "annual-audit-november-2024"
      start_time     = local.annual_audit_2024.start
      end_time       = local.annual_audit_2024.end
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }
  }

  # Release channel for controlled updates
  release_channel {
    channel = "REGULAR"  # More predictable than RAPID, more current than STABLE
  }

  # Enable network policy for security
  network_policy {
    enabled = true
  }

  # Enable workload identity
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
      "WORKLOADS"
    ]
  }
}

# Node pools with separate maintenance configuration
resource "google_container_node_pool" "primary_nodes" {
  count      = length(local.cluster_names)
  name       = "${local.cluster_names[count.index]}-primary-pool"
  location   = var.cluster_zones[count.index]
  cluster    = google_container_cluster.production_clusters[count.index].name
  
  node_count = var.node_count_per_zone

  # Node configuration
  node_config {
    preemptible  = false
    machine_type = var.machine_type

    # Security settings
    service_account = google_service_account.gke_nodes.email
    oauth_scopes = [
      "https://www.googleapis.com/auth/logging.write",
      "https://www.googleapis.com/auth/monitoring",
      "https://www.googleapis.com/auth/cloud-platform"
    ]

    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }
  }

  # Auto-upgrade settings aligned with maintenance windows
  management {
    auto_repair  = true
    auto_upgrade = true
  }

  # Upgrade settings
  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
    strategy        = "SURGE"
  }
}
```

## 2. Variables Configuration

```hcl
# terraform/variables.tf

variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "cluster_zones" {
  description = "Zones for the clusters"
  type        = list(string)
  default     = ["us-central1-a", "us-central1-b", "us-central1-c"]
}

variable "vpc_network" {
  description = "VPC network name"
  type        = string
  default     = "default"
}

variable "subnet" {
  description = "Subnet name"
  type        = string
  default     = "default"
}

variable "machine_type" {
  description = "Machine type for nodes"
  type        = string
  default     = "e2-medium"
}

variable "node_count_per_zone" {
  description = "Number of nodes per zone"
  type        = number
  default     = 2
}
```

## 3. Service Account for Audit Compliance

```hcl
# terraform/service-accounts.tf

resource "google_service_account" "gke_nodes" {
  account_id   = "gke-nodes-sa"
  display_name = "GKE Nodes Service Account"
  description  = "Service account for GKE nodes with audit logging"
}

resource "google_project_iam_member" "gke_nodes_logging" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

resource "google_project_iam_member" "gke_nodes_monitoring" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

resource "google_project_iam_member" "gke_nodes_monitoring_viewer" {
  project = var.project_id
  role    = "roles/monitoring.viewer"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}
```

## 4. Maintenance Management Script

```bash
#!/bin/bash
# scripts/update-maintenance-exclusions.sh

set -e

PROJECT_ID="your-project-id"
CLUSTERS=("prod-cluster-1" "prod-cluster-2" "prod-cluster-3")
ZONES=("us-central1-a" "us-central1-b" "us-central1-c")

# Function to add maintenance exclusion
add_maintenance_exclusion() {
    local cluster=$1
    local zone=$2
    local exclusion_name=$3
    local start_time=$4
    local end_time=$5
    
    echo "Adding maintenance exclusion for cluster: $cluster"
    
    gcloud container clusters update "$cluster" \
        --zone="$zone" \
        --add-maintenance-exclusion-name="$exclusion_name" \
        --add-maintenance-exclusion-start="$start_time" \
        --add-maintenance-exclusion-end="$end_time" \
        --add-maintenance-exclusion-scope="ALL_UPGRADES" \
        --project="$PROJECT_ID"
}

# Function to remove expired exclusions
remove_maintenance_exclusion() {
    local cluster=$1
    local zone=$2
    local exclusion_name=$3
    
    echo "Removing maintenance exclusion for cluster: $cluster"
    
    gcloud container clusters update "$cluster" \
        --zone="$zone" \
        --remove-maintenance-exclusion="$exclusion_name" \
        --project="$PROJECT_ID"
}

# Add quarterly exclusions for all clusters
case "$1" in
    "add-q1")
        for i in "${!CLUSTERS[@]}"; do
            add_maintenance_exclusion "${CLUSTERS[$i]}" "${ZONES[$i]}" \
                "quarterly-freeze-q1-2024" "2024-03-15T00:00:00Z" "2024-03-31T23:59:59Z"
        done
        ;;
    "add-q2")
        for i in "${!CLUSTERS[@]}"; do
            add_maintenance_exclusion "${CLUSTERS[$i]}" "${ZONES[$i]}" \
                "quarterly-freeze-q2-2024" "2024-06-15T00:00:00Z" "2024-06-30T23:59:59Z"
        done
        ;;
    "add-audit")
        for i in "${!CLUSTERS[@]}"; do
            add_maintenance_exclusion "${CLUSTERS[$i]}" "${ZONES[$i]}" \
                "annual-audit-november-2024" "2024-11-01T00:00:00Z" "2024-11-30T23:59:59Z"
        done
        ;;
    "remove-expired")
        # Add logic to remove expired exclusions
        current_date=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
        echo "Checking for expired exclusions as of: $current_date"
        # Implementation depends on your specific needs
        ;;
    *)
        echo "Usage: $0 {add-q1|add-q2|add-audit|remove-expired}"
        exit 1
        ;;
esac
```

## 5. Monitoring and Alerting

```yaml
# monitoring/maintenance-alerts.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: maintenance-monitoring
  namespace: kube-system
data:
  alert-rules.yaml: |
    groups:
    - name: gke-maintenance
      rules:
      - alert: MaintenanceWindowViolation
        expr: |
          (
            time() % 86400 < 7200 or time() % 86400 > 21600
          ) and on() gke_cluster_maintenance_active == 1
        for: 5m
        labels:
          severity: critical
          compliance: sox
        annotations:
          summary: "GKE maintenance occurring outside approved window"
          description: "Cluster maintenance detected outside weekend maintenance window"
      
      - alert: UpgradesDuringFreeze
        expr: |
          gke_cluster_upgrade_active == 1 and on() maintenance_freeze_active == 1
        for: 1m
        labels:
          severity: critical
          compliance: sox
        annotations:
          summary: "GKE upgrade during maintenance freeze"
          description: "Cluster upgrade detected during compliance freeze period"
```

## 6. Compliance Validation Script

```python
#!/usr/bin/env python3
# scripts/validate-maintenance-compliance.py

import json
import subprocess
import datetime
from typing import List, Dict

class MaintenanceValidator:
    def __init__(self, project_id: str, clusters: List[Dict]):
        self.project_id = project_id
        self.clusters = clusters
        
    def get_cluster_maintenance_policy(self, cluster_name: str, zone: str) -> Dict:
        """Get maintenance policy for a cluster"""
        cmd = [
            'gcloud', 'container', 'clusters', 'describe', cluster_name,
            '--zone', zone, '--project', self.project_id, '--format', 'json'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"Failed to get cluster info: {result.stderr}")
            
        return json.loads(result.stdout)
    
    def validate_maintenance_windows(self) -> Dict:
        """Validate that maintenance windows are correctly configured"""
        validation_results = {}
        
        for cluster in self.clusters:
            cluster_name = cluster['name']
            zone = cluster['zone']
            
            try:
                cluster_info = self.get_cluster_maintenance_policy(cluster_name, zone)
                maintenance_policy = cluster_info.get('maintenancePolicy', {})
                
                # Check recurring window
                recurring_window = maintenance_policy.get('recurringWindow', {})
                if not recurring_window:
                    validation_results[cluster_name] = {
                        'status': 'FAIL',
                        'reason': 'No recurring maintenance window configured'
                    }
                    continue
                
                # Validate weekend-only maintenance
                recurrence = recurring_window.get('recurrence', '')
                if 'BYDAY=SA' not in recurrence and 'BYDAY=SU' not in recurrence:
                    validation_results[cluster_name] = {
                        'status': 'FAIL',
                        'reason': 'Maintenance window not configured for weekends only'
                    }
                    continue
                
                # Check exclusions
                exclusions = maintenance_policy.get('maintenanceExclusions', [])
                required_exclusions = ['quarterly-freeze', 'annual-audit']
                
                exclusion_names = [exc.get('name', '') for exc in exclusions]
                missing_exclusions = []
                
                for req_exclusion in required_exclusions:
                    if not any(req_exclusion in name for name in exclusion_names):
                        missing_exclusions.append(req_exclusion)
                
                if missing_exclusions:
                    validation_results[cluster_name] = {
                        'status': 'WARN',
                        'reason': f'Missing exclusions: {", ".join(missing_exclusions)}'
                    }
                else:
                    validation_results[cluster_name] = {
                        'status': 'PASS',
                        'reason': 'All compliance requirements met'
                    }
                    
            except Exception as e:
                validation_results[cluster_name] = {
                    'status': 'ERROR',
                    'reason': str(e)
                }
        
        return validation_results
    
    def generate_compliance_report(self) -> str:
        """Generate compliance report"""
        results = self.validate_maintenance_windows()
        
        report = f"""
GKE Maintenance Compliance Report
Generated: {datetime.datetime.now().isoformat()}
Project: {self.project_id}

Cluster Compliance Status:
"""
        
        for cluster_name, result in results.items():
            status = result['status']
            reason = result['reason']
            report += f"  {cluster_name}: {status} - {reason}\n"
        
        # Summary
        total_clusters = len(results)
        passed = len([r for r in results.values() if r['status'] == 'PASS'])
        
        report += f"""
Summary:
  Total Clusters: {total_clusters}
  Compliant: {passed}
  Compliance Rate: {(passed/total_clusters)*100:.1f}%
"""
        
        
I'll help you configure maintenance windows and exclusions for your GKE clusters to meet SOX compliance requirements. Here's a comprehensive setup:

## 1. Terraform Configuration for Maintenance Windows

```hcl
# variables.tf
variable "clusters" {
  description = "Map of cluster configurations"
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
      location = "us-west1-a"
      region   = "us-west1"
    }
  }
}

# Local values for maintenance schedule
locals {
  # Current year for maintenance exclusions
  current_year = formatdate("YYYY", timestamp())
  next_year    = tostring(tonumber(local.current_year) + 1)
  
  # Quarterly code freeze periods (adjust dates as needed)
  quarterly_freezes = [
    {
      name       = "Q1-freeze-${local.current_year}"
      start_time = "${local.current_year}-03-15T00:00:00Z"
      end_time   = "${local.current_year}-03-31T23:59:59Z"
    },
    {
      name       = "Q2-freeze-${local.current_year}"
      start_time = "${local.current_year}-06-15T00:00:00Z"
      end_time   = "${local.current_year}-06-30T23:59:59Z"
    },
    {
      name       = "Q3-freeze-${local.current_year}"
      start_time = "${local.current_year}-09-15T00:00:00Z"
      end_time   = "${local.current_year}-09-30T23:59:59Z"
    },
    {
      name       = "Q4-freeze-${local.current_year}"
      start_time = "${local.current_year}-12-15T00:00:00Z"
      end_time   = "${local.current_year}-12-31T23:59:59Z"
    }
  ]
  
  # Annual audit exclusion (entire November)
  annual_audit = {
    name       = "annual-audit-${local.current_year}"
    start_time = "${local.current_year}-11-01T00:00:00Z"
    end_time   = "${local.current_year}-11-30T23:59:59Z"
  }
  
  # Holiday exclusions (common financial services blackout dates)
  holiday_exclusions = [
    {
      name       = "year-end-freeze-${local.current_year}"
      start_time = "${local.current_year}-12-20T00:00:00Z"
      end_time   = "${local.next_year}-01-05T23:59:59Z"
    },
    {
      name       = "memorial-day-${local.current_year}"
      start_time = "${local.current_year}-05-25T00:00:00Z"
      end_time   = "${local.current_year}-05-27T23:59:59Z"
    },
    {
      name       = "independence-day-${local.current_year}"
      start_time = "${local.current_year}-07-03T00:00:00Z"
      end_time   = "${local.current_year}-07-05T23:59:59Z"
    },
    {
      name       = "thanksgiving-${local.current_year}"
      start_time = "${local.current_year}-11-23T00:00:00Z"
      end_time   = "${local.current_year}-11-25T23:59:59Z"
    }
  ]
}

# main.tf
resource "google_container_cluster" "clusters" {
  for_each = var.clusters
  
  name     = each.value.name
  location = each.value.location
  
  # Remove default node pool
  remove_default_node_pool = true
  initial_node_count       = 1
  
  # Release channel for managed upgrades
  release_channel {
    channel = "REGULAR"  # Use STABLE for production if preferred
  }
  
  # Maintenance policy with weekend-only windows
  maintenance_policy {
    # Recurring maintenance window: Saturdays 2-6 AM UTC
    recurring_window {
      start_time = "2023-01-07T02:00:00Z"  # First Saturday
      end_time   = "2023-01-07T06:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SA"
    }
  }
  
  # Network policy for security
  network_policy {
    enabled = true
  }
  
  # Master authorized networks for SOX compliance
  master_authorized_networks_config {
    cidr_blocks {
      cidr_block   = "10.0.0.0/8"
      display_name = "internal-network"
    }
  }
  
  # Enable network policy
  addons_config {
    network_policy_config {
      disabled = false
    }
  }
  
  # Workload Identity for security
  workload_identity_config {
    workload_pool = "${data.google_project.current.project_id}.svc.id.goog"
  }
}

# Maintenance exclusions for each cluster
resource "google_gke_maintenance_policy" "exclusions" {
  for_each = var.clusters
  
  project  = data.google_project.current.project_id
  location = each.value.location
  cluster  = google_container_cluster.clusters[each.key].name
  
  # Quarterly code freezes
  dynamic "exclusion" {
    for_each = local.quarterly_freezes
    content {
      exclusion_name = exclusion.value.name
      start_time     = exclusion.value.start_time
      end_time       = exclusion.value.end_time
    }
  }
  
  # Annual audit exclusion
  exclusion {
    exclusion_name = local.annual_audit.name
    start_time     = local.annual_audit.start_time
    end_time       = local.annual_audit.end_time
  }
  
  # Holiday exclusions
  dynamic "exclusion" {
    for_each = local.holiday_exclusions
    content {
      exclusion_name = exclusion.value.name
      start_time     = exclusion.value.start_time
      end_time       = exclusion.value.end_time
    }
  }
  
  depends_on = [google_container_cluster.clusters]
}

# Node pools with maintenance settings
resource "google_container_node_pool" "primary_nodes" {
  for_each = var.clusters
  
  name       = "${each.value.name}-node-pool"
  location   = each.value.location
  cluster    = google_container_cluster.clusters[each.key].name
  node_count = 3
  
  # Upgrade settings for controlled rollouts
  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0  # Ensure no downtime during upgrades
  }
  
  # Management settings
  management {
    auto_repair  = true
    auto_upgrade = true
  }
  
  node_config {
    preemptible  = false  # Use regular instances for production
    machine_type = "e2-medium"
    
    # Security settings for SOX compliance
    service_account = google_service_account.gke_nodes[each.key].email
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]
    
    # Workload Identity
    workload_metadata_config {
      mode = "GKE_METADATA"
    }
    
    # Enable secure boot and integrity monitoring
    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }
  }
}

# Service accounts for nodes
resource "google_service_account" "gke_nodes" {
  for_each = var.clusters
  
  account_id   = "${each.value.name}-nodes"
  display_name = "GKE ${each.value.name} Node Service Account"
}

# IAM bindings for node service accounts
resource "google_project_iam_member" "gke_nodes" {
  for_each = var.clusters
  
  project = data.google_project.current.project_id
  role    = "roles/container.nodeServiceAccount"
  member  = "serviceAccount:${google_service_account.gke_nodes[each.key].email}"
}

data "google_project" "current" {}
```

## 2. Python Script for Dynamic Maintenance Management

```python
#!/usr/bin/env python3
"""
GKE Maintenance Window Manager for SOX Compliance
Manages maintenance exclusions and notifications
"""

import json
import datetime
from typing import List, Dict, Any
from google.cloud import container_v1
from google.cloud import monitoring_v3
import logging

class GKEMaintenanceManager:
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.client = container_v1.ClusterManagerClient()
        self.monitoring_client = monitoring_v3.NotificationChannelServiceClient()
        
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

    def create_maintenance_exclusion(
        self, 
        cluster_name: str, 
        location: str,
        exclusion_name: str,
        start_time: str,
        end_time: str,
        description: str = ""
    ) -> bool:
        """Create a maintenance exclusion period"""
        try:
            parent = f"projects/{self.project_id}/locations/{location}/clusters/{cluster_name}"
            
            exclusion = {
                'name': exclusion_name,
                'start_time': start_time,
                'end_time': end_time,
                'description': description or f"SOX compliance exclusion: {exclusion_name}"
            }
            
            request = container_v1.SetMaintenancePolicyRequest(
                project_id=self.project_id,
                zone=location,  # Use zone for zonal clusters
                cluster_id=cluster_name,
                maintenance_policy=container_v1.MaintenancePolicy(
                    maintenance_exclusions=[exclusion]
                )
            )
            
            operation = self.client.set_maintenance_policy(request=request)
            self.logger.info(f"Created maintenance exclusion '{exclusion_name}' for {cluster_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to create maintenance exclusion: {str(e)}")
            return False

    def get_upcoming_maintenance_windows(self, days_ahead: int = 30) -> List[Dict[str, Any]]:
        """Get upcoming maintenance windows across all clusters"""
        maintenance_windows = []
        
        try:
            # List all clusters
            parent = f"projects/{self.project_id}/locations/-"
            clusters = self.client.list_clusters(parent=parent).clusters
            
            for cluster in clusters:
                if cluster.maintenance_policy:
                    window_info = {
                        'cluster_name': cluster.name,
                        'location': cluster.location,
                        'maintenance_policy': cluster.maintenance_policy,
                        'current_version': cluster.current_master_version,
                        'node_version': cluster.current_node_version
                    }
                    maintenance_windows.append(window_info)
                    
        except Exception as e:
            self.logger.error(f"Failed to retrieve maintenance windows: {str(e)}")
            
        return maintenance_windows

    def validate_sox_compliance(self) -> Dict[str, Any]:
        """Validate SOX compliance requirements"""
        compliance_report = {
            'compliant': True,
            'issues': [],
            'clusters_checked': 0,
            'timestamp': datetime.datetime.utcnow().isoformat()
        }
        
        try:
            parent = f"projects/{self.project_id}/locations/-"
            clusters = self.client.list_clusters(parent=parent).clusters
            
            for cluster in clusters:
                compliance_report['clusters_checked'] += 1
                cluster_issues = []
                
                # Check if maintenance policy exists
                if not cluster.maintenance_policy:
                    cluster_issues.append("No maintenance policy configured")
                
                # Check if network policy is enabled
                if not cluster.network_policy or not cluster.network_policy.enabled:
                    cluster_issues.append("Network policy not enabled")
                
                # Check if workload identity is enabled
                if not cluster.workload_identity_config:
                    cluster_issues.append("Workload Identity not configured")
                
                # Check master authorized networks
                if not cluster.master_authorized_networks_config:
                    cluster_issues.append("Master authorized networks not configured")
                
                if cluster_issues:
                    compliance_report['compliant'] = False
                    compliance_report['issues'].append({
                        'cluster': cluster.name,
                        'location': cluster.location,
                        'issues': cluster_issues
                    })
                    
        except Exception as e:
            self.logger.error(f"Compliance validation failed: {str(e)}")
            compliance_report['compliant'] = False
            compliance_report['issues'].append({'error': str(e)})
            
        return compliance_report

def generate_annual_exclusions(year: int) -> List[Dict[str, str]]:
    """Generate annual maintenance exclusions"""
    return [
        {
            'name': f'q1-code-freeze-{year}',
            'start_time': f'{year}-03-15T00:00:00Z',
            'end_time': f'{year}-03-31T23:59:59Z',
            'description': 'Q1 quarterly code freeze'
        },
        {
            'name': f'q2-code-freeze-{year}',
            'start_time': f'{year}-06-15T00:00:00Z',
            'end_time': f'{year}-06-30T23:59:59Z',
            'description': 'Q2 quarterly code freeze'
        },
        {
            'name': f'q3-code-freeze-{year}',
            'start_time': f'{year}-09-15T00:00:00Z',
            'end_time': f'{year}-09-30T23:59:59Z',
            'description': 'Q3 quarterly code freeze'
        },
        {
            'name': f'annual-audit-{year}',
            'start_time': f'{year}-11-01T00:00:00Z',
            'end_time': f'{year}-11-30T23:59:59Z',
            'description': 'Annual audit period - no changes allowed'
        },
        {
            'name': f'q4-code-freeze-{year}',
            'start_time': f'{year}-12-15T00:00:00Z',
            'end_time': f'{year}-12-31T23:59:59Z',
            'description': 'Q4 quarterly code freeze'
        },
        {
            'name': f'year-end-freeze-{year}',
            'start_time': f'{year}-12-20T00:00:00Z',
            'end_time': f'{year + 1}-01-05T23:59:59Z',
            'description': 'Year-end holiday freeze'
        }
    ]

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='GKE Maintenance Manager')
    parser.add_argument('--project-id', required=True
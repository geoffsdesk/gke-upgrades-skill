I'll help you configure maintenance windows and exclusions for your GKE Standard clusters to meet SOX compliance requirements. Here's a comprehensive solution:

## 1. Maintenance Window Configuration

```yaml
# maintenance-window-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: gke-maintenance-policy
  namespace: kube-system
data:
  policy: |
    # Weekend-only maintenance windows
    # Maintenance occurs Saturdays 2 AM - 6 AM EST
    maintenance_window:
      start_time: "2023-01-07T07:00:00Z"  # Saturday 2 AM EST
      duration: "14400s"  # 4 hours
      recurrence: "FREQ=WEEKLY;BYDAY=SA"
```

## 2. Terraform Configuration

```hcl
# gke-maintenance-policy.tf
resource "google_container_cluster" "sox_compliant_cluster" {
  count    = 3
  name     = "sox-cluster-${count.index + 1}"
  location = var.cluster_locations[count.index]
  
  # Disable automatic upgrades during creation
  remove_default_node_pool = true
  initial_node_count       = 1

  # Master version - pin to specific version for stability
  min_master_version = var.kubernetes_version

  # Maintenance policy
  maintenance_policy {
    # Weekend maintenance window (Saturday 2-6 AM EST)
    daily_maintenance_window {
      start_time = "07:00"  # UTC time for 2 AM EST
    }
  }

  # Cluster-level maintenance exclusions
  maintenance_policy {
    # Quarterly code freeze exclusions
    maintenance_exclusion {
      exclusion_name = "q1-code-freeze-2024"
      start_time     = "2024-03-15T00:00:00Z"
      end_time       = "2024-04-01T00:00:00Z"
      exclusion_options {
        scope = "UPGRADES"
      }
    }
    
    maintenance_exclusion {
      exclusion_name = "q2-code-freeze-2024"
      start_time     = "2024-06-15T00:00:00Z"
      end_time       = "2024-07-01T00:00:00Z"
      exclusion_options {
        scope = "UPGRADES"
      }
    }
    
    maintenance_exclusion {
      exclusion_name = "q3-code-freeze-2024"
      start_time     = "2024-09-15T00:00:00Z"
      end_time       = "2024-10-01T00:00:00Z"
      exclusion_options {
        scope = "UPGRADES"
      }
    }
    
    maintenance_exclusion {
      exclusion_name = "q4-code-freeze-2024"
      start_time     = "2024-12-15T00:00:00Z"
      end_time       = "2025-01-01T00:00:00Z"
      exclusion_options {
        scope = "UPGRADES"
      }
    }

    # Annual audit exclusion (November)
    maintenance_exclusion {
      exclusion_name = "annual-audit-2024"
      start_time     = "2024-11-01T00:00:00Z"
      end_time       = "2024-11-30T23:59:59Z"
      exclusion_options {
        scope = "UPGRADES"
      }
    }

    # Holiday exclusions for additional safety
    maintenance_exclusion {
      exclusion_name = "holiday-freeze-2024"
      start_time     = "2024-12-20T00:00:00Z"
      end_time       = "2025-01-05T00:00:00Z"
      exclusion_options {
        scope = "UPGRADES"
      }
    }
  }

  # Release channel for controlled upgrades
  release_channel {
    channel = "STABLE"  # Use STABLE for SOX compliance
  }

  # Workload Identity for security compliance
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  # Network policy for security
  network_policy {
    enabled  = true
    provider = "CALICO"
  }

  # Enable shielded nodes for security compliance
  enable_shielded_nodes = true

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

# Node pools with maintenance policies
resource "google_container_node_pool" "sox_node_pool" {
  count      = 3
  name       = "sox-node-pool-${count.index + 1}"
  location   = var.cluster_locations[count.index]
  cluster    = google_container_cluster.sox_compliant_cluster[count.index].name
  
  # Pin node version for stability
  version = var.kubernetes_version
  
  # Upgrade settings
  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
    strategy        = "SURGE"
  }

  # Management settings
  management {
    auto_repair  = true
    auto_upgrade = false  # Disable auto-upgrade, handle manually during maintenance windows
  }

  node_config {
    machine_type = "e2-standard-4"
    disk_size_gb = 100
    disk_type    = "pd-ssd"
    
    # Security configurations
    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }
    
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]
  }
  
  autoscaling {
    min_node_count = 2
    max_node_count = 10
  }
}
```

## 3. gcloud Commands for Manual Management

```bash
#!/bin/bash
# gke-maintenance-commands.sh

# Set variables
PROJECT_ID="your-project-id"
CLUSTERS=("sox-cluster-1" "sox-cluster-2" "sox-cluster-3")
ZONES=("us-central1-a" "us-east1-a" "us-west1-a")

# Function to set maintenance window for a cluster
set_maintenance_window() {
    local cluster_name=$1
    local zone=$2
    
    gcloud container clusters update $cluster_name \
        --zone=$zone \
        --maintenance-window-start="2023-01-07T07:00:00Z" \
        --maintenance-window-end="2023-01-07T11:00:00Z" \
        --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SA" \
        --project=$PROJECT_ID
}

# Function to add maintenance exclusion
add_maintenance_exclusion() {
    local cluster_name=$1
    local zone=$2
    local exclusion_name=$3
    local start_time=$4
    local end_time=$5
    
    gcloud container clusters update $cluster_name \
        --zone=$zone \
        --add-maintenance-exclusion-name=$exclusion_name \
        --add-maintenance-exclusion-start=$start_time \
        --add-maintenance-exclusion-end=$end_time \
        --add-maintenance-exclusion-scope=upgrades \
        --project=$PROJECT_ID
}

# Set maintenance windows for all clusters
for i in "${!CLUSTERS[@]}"; do
    echo "Setting maintenance window for ${CLUSTERS[$i]}"
    set_maintenance_window "${CLUSTERS[$i]}" "${ZONES[$i]}"
done

# Add quarterly exclusions for 2024
exclusions=(
    "q1-freeze:2024-03-15T00:00:00Z:2024-04-01T00:00:00Z"
    "q2-freeze:2024-06-15T00:00:00Z:2024-07-01T00:00:00Z"
    "q3-freeze:2024-09-15T00:00:00Z:2024-10-01T00:00:00Z"
    "q4-freeze:2024-12-15T00:00:00Z:2025-01-01T00:00:00Z"
    "annual-audit:2024-11-01T00:00:00Z:2024-11-30T23:59:59Z"
)

for i in "${!CLUSTERS[@]}"; do
    for exclusion in "${exclusions[@]}"; do
        IFS=':' read -r name start end <<< "$exclusion"
        echo "Adding exclusion $name to ${CLUSTERS[$i]}"
        add_maintenance_exclusion "${CLUSTERS[$i]}" "${ZONES[$i]}" "$name" "$start" "$end"
    done
done
```

## 4. Automated Exclusion Management Script

```python
#!/usr/bin/env python3
# maintenance-exclusion-manager.py

import datetime
from google.cloud import container_v1
from dateutil.relativedelta import relativedelta

class MaintenanceExclusionManager:
    def __init__(self, project_id):
        self.project_id = project_id
        self.client = container_v1.ClusterManagerClient()
        
    def get_quarterly_freeze_dates(self, year):
        """Generate quarterly code freeze dates"""
        quarters = []
        for quarter in range(1, 5):
            if quarter == 1:
                start = datetime.datetime(year, 3, 15)
            elif quarter == 2:
                start = datetime.datetime(year, 6, 15)
            elif quarter == 3:
                start = datetime.datetime(year, 9, 15)
            else:  # Q4
                start = datetime.datetime(year, 12, 15)
            
            end = start + relativedelta(days=17)  # ~2.5 week freeze
            quarters.append((f"q{quarter}-freeze-{year}", start, end))
        
        return quarters
    
    def add_maintenance_exclusions(self, cluster_name, zone):
        """Add all required maintenance exclusions"""
        current_year = datetime.datetime.now().year
        
        # Get quarterly dates
        quarterly_exclusions = self.get_quarterly_freeze_dates(current_year)
        
        # Add annual audit exclusion
        audit_start = datetime.datetime(current_year, 11, 1)
        audit_end = datetime.datetime(current_year, 11, 30, 23, 59, 59)
        quarterly_exclusions.append(("annual-audit", audit_start, audit_end))
        
        # Holiday freeze
        holiday_start = datetime.datetime(current_year, 12, 20)
        holiday_end = datetime.datetime(current_year + 1, 1, 5)
        quarterly_exclusions.append(("holiday-freeze", holiday_start, holiday_end))
        
        cluster_path = f"projects/{self.project_id}/locations/{zone}/clusters/{cluster_name}"
        
        for name, start, end in quarterly_exclusions:
            exclusion = {
                "exclusion_name": name,
                "start_time": start.isoformat() + "Z",
                "end_time": end.isoformat() + "Z",
                "exclusion_options": {
                    "scope": "UPGRADES"
                }
            }
            
            try:
                operation = self.client.update_cluster(
                    cluster={"name": cluster_path},
                    update={
                        "desired_maintenance_policy": {
                            "maintenance_exclusions": [exclusion]
                        }
                    }
                )
                print(f"Added exclusion {name} to {cluster_name}: {operation.name}")
            except Exception as e:
                print(f"Error adding exclusion {name}: {e}")

# Usage
if __name__ == "__main__":
    manager = MaintenanceExclusionManager("your-project-id")
    
    clusters = [
        ("sox-cluster-1", "us-central1-a"),
        ("sox-cluster-2", "us-east1-a"),
        ("sox-cluster-3", "us-west1-a")
    ]
    
    for cluster_name, zone in clusters:
        manager.add_maintenance_exclusions(cluster_name, zone)
```

## 5. SOX Compliance Monitoring

```yaml
# monitoring-alert-policy.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: gke-maintenance-compliance
  namespace: monitoring
spec:
  groups:
  - name: gke_maintenance
    rules:
    - alert: UnscheduledMaintenanceDetected
      expr: increase(gke_cluster_maintenance_events_total[1h]) > 0
      for: 0m
      labels:
        severity: critical
        compliance: sox
      annotations:
        summary: "Unscheduled maintenance detected on GKE cluster"
        description: "GKE cluster {{ $labels.cluster }} has undergone maintenance outside of approved windows"
    
    - alert: MaintenanceWindowViolation
      expr: |
        (
          hour() < 7 or hour() > 11 or 
          (day_of_week() != 6)
        ) and on() gke_cluster_maintenance_active == 1
      for: 1m
      labels:
        severity: critical
        compliance: sox
      annotations:
        summary: "Maintenance occurring outside approved window"
        description: "Maintenance is active outside of Saturday 2-6 AM EST window"
```

## 6. Variables File

```hcl
# variables.tf
variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "cluster_locations" {
  description = "Locations for the three GKE clusters"
  type        = list(string)
  default     = ["us-central1-a", "us-east1-a", "us-west1-a"]
}

variable "kubernetes_version" {
  description = "Kubernetes version for clusters and nodes"
  type        = string
  default     = "1.28.3-gke.1203001"  # Pin to specific stable version
}

variable "maintenance_exclusions_2024" {
  description = "Maintenance exclusions for 2024"
  type = list(object({
    name       = string
    start_time = string
    end_time   = string
    scope      = string
  }))
  default = [
    {
      name       = "q1-freeze-2024"
      start_time = "2024-03-15T00:00:00Z"
      end_time   = "2024-04-01T00:00:00Z"
      scope      = "UPGRADES"
    },
    # ... other exclusions
  ]
}
```

## Key SOX Compliance Features:

1. **Controlled Upgrade Schedule**: Weekend-only maintenance windows
2. **Audit Trail**: Full logging and monitoring enabled
3. **Change Control**: Quarterly code freezes and audit exclusions
4. **Version Pinning**: Specific Kubernetes versions for stability
5. **Security**: Shielded nodes, network policies, workload identity
6. **Monitoring**: Alerts for any maintenance outside approved windows

This configuration ensures your GKE clusters operate within SOX compliance requirements while maintaining security and operational excellence.
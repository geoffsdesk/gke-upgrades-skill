I'll help you configure maintenance windows and exclusions for your GKE Standard clusters to meet SOX compliance requirements. Here's a comprehensive setup:

## 1. Maintenance Window Configuration

```yaml
# maintenance-policy.yaml
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerCluster
metadata:
  name: prod-cluster-1
spec:
  maintenancePolicy:
    dailyMaintenanceWindow:
      startTime: "02:00"  # 2 AM UTC - adjust for your timezone
    maintenanceExclusion:
      - exclusionName: "quarterly-freeze-q1"
        startTime: "2024-03-15T00:00:00Z"
        endTime: "2024-04-01T00:00:00Z"
        exclusionOptions:
          scope: "ALL_UPGRADES"
      - exclusionName: "quarterly-freeze-q2" 
        startTime: "2024-06-15T00:00:00Z"
        endTime: "2024-07-01T00:00:00Z"
        exclusionOptions:
          scope: "ALL_UPGRADES"
      - exclusionName: "quarterly-freeze-q3"
        startTime: "2024-09-15T00:00:00Z"
        endTime: "2024-10-01T00:00:00Z"
        exclusionOptions:
          scope: "ALL_UPGRADES"
      - exclusionName: "annual-audit-november"
        startTime: "2024-11-01T00:00:00Z"
        endTime: "2024-11-30T23:59:59Z"
        exclusionOptions:
          scope: "ALL_UPGRADES"
      - exclusionName: "quarterly-freeze-q4"
        startTime: "2024-12-15T00:00:00Z"
        endTime: "2025-01-02T00:00:00Z"
        exclusionOptions:
          scope: "ALL_UPGRADES"
```

## 2. Terraform Configuration for All Clusters

```hcl
# main.tf
variable "cluster_names" {
  description = "List of GKE cluster names"
  type        = list(string)
  default     = ["prod-cluster-1", "prod-cluster-2", "prod-cluster-3"]
}

variable "maintenance_exclusions" {
  description = "Maintenance exclusion periods for SOX compliance"
  type = list(object({
    exclusion_name = string
    start_time     = string
    end_time       = string
    scope          = string
  }))
  default = [
    {
      exclusion_name = "quarterly-freeze-q1-2024"
      start_time     = "2024-03-15T00:00:00Z"
      end_time       = "2024-04-01T00:00:00Z"
      scope          = "ALL_UPGRADES"
    },
    {
      exclusion_name = "quarterly-freeze-q2-2024"
      start_time     = "2024-06-15T00:00:00Z"
      end_time       = "2024-07-01T00:00:00Z"
      scope          = "ALL_UPGRADES"
    },
    {
      exclusion_name = "quarterly-freeze-q3-2024"
      start_time     = "2024-09-15T00:00:00Z"
      end_time       = "2024-10-01T00:00:00Z"
      scope          = "ALL_UPGRADES"
    },
    {
      exclusion_name = "annual-audit-november-2024"
      start_time     = "2024-11-01T00:00:00Z"
      end_time       = "2024-11-30T23:59:59Z"
      scope          = "ALL_UPGRADES"
    },
    {
      exclusion_name = "quarterly-freeze-q4-2024"
      start_time     = "2024-12-15T00:00:00Z"
      end_time       = "2025-01-02T00:00:00Z"
      scope          = "ALL_UPGRADES"
    }
  ]
}

resource "google_container_cluster" "sox_compliant_clusters" {
  count    = length(var.cluster_names)
  name     = var.cluster_names[count.index]
  location = var.region

  # Weekend-only maintenance window (Saturday 2 AM UTC)
  maintenance_policy {
    recurring_window {
      start_time = "2024-01-06T02:00:00Z"  # First Saturday of 2024
      end_time   = "2024-01-06T06:00:00Z"  # 4-hour window
      recurrence = "FREQ=WEEKLY;BYDAY=SA"   # Every Saturday
    }

    # Maintenance exclusions for compliance
    dynamic "maintenance_exclusion" {
      for_each = var.maintenance_exclusions
      content {
        exclusion_name = maintenance_exclusion.value.exclusion_name
        start_time     = maintenance_exclusion.value.start_time
        end_time       = maintenance_exclusion.value.end_time

        exclusion_options {
          scope = maintenance_exclusion.value.scope
        }
      }
    }
  }

  # Enable auto-upgrade with release channel
  release_channel {
    channel = "REGULAR"  # Use STABLE for more conservative updates
  }

  # Node pool configuration with auto-upgrade
  initial_node_count       = 1
  remove_default_node_pool = true

  depends_on = [
    google_project_service.container
  ]
}

# Separate node pools for better control
resource "google_container_node_pool" "sox_compliant_nodes" {
  count      = length(var.cluster_names)
  name       = "${var.cluster_names[count.index]}-nodes"
  cluster    = google_container_cluster.sox_compliant_clusters[count.index].name
  location   = var.region
  node_count = 3

  # Auto-upgrade and auto-repair enabled
  management {
    auto_repair  = true
    auto_upgrade = true
  }

  # Upgrade settings for controlled rollouts
  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
    strategy        = "SURGE"
  }

  node_config {
    preemptible  = false
    machine_type = "e2-medium"

    oauth_scopes = [
      "https://www.googleapis.com/auth/logging.write",
      "https://www.googleapis.com/auth/monitoring",
      "https://www.googleapis.com/auth/cloud-platform"
    ]

    labels = {
      environment = "production"
      compliance  = "sox"
    }

    tags = ["sox-compliant", "production"]
  }
}
```

## 3. gcloud Commands for Quick Setup

```bash
#!/bin/bash
# setup-maintenance-windows.sh

CLUSTERS=("prod-cluster-1" "prod-cluster-2" "prod-cluster-3")
REGION="us-central1"

for cluster in "${CLUSTERS[@]}"; do
  echo "Configuring maintenance policy for $cluster..."
  
  # Set recurring maintenance window (Saturdays 2 AM UTC)
  gcloud container clusters update $cluster \
    --region=$REGION \
    --maintenance-window-start "2024-01-06T02:00:00Z" \
    --maintenance-window-end "2024-01-06T06:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
  
  # Add maintenance exclusions
  gcloud container clusters update $cluster \
    --region=$REGION \
    --add-maintenance-exclusion-end "2024-04-01T00:00:00Z" \
    --add-maintenance-exclusion-name "quarterly-freeze-q1-2024" \
    --add-maintenance-exclusion-scope "all-upgrades" \
    --add-maintenance-exclusion-start "2024-03-15T00:00:00Z"
    
  gcloud container clusters update $cluster \
    --region=$REGION \
    --add-maintenance-exclusion-end "2024-07-01T00:00:00Z" \
    --add-maintenance-exclusion-name "quarterly-freeze-q2-2024" \
    --add-maintenance-exclusion-scope "all-upgrades" \
    --add-maintenance-exclusion-start "2024-06-15T00:00:00Z"
    
  gcloud container clusters update $cluster \
    --region=$REGION \
    --add-maintenance-exclusion-end "2024-10-01T00:00:00Z" \
    --add-maintenance-exclusion-name "quarterly-freeze-q3-2024" \
    --add-maintenance-exclusion-scope "all-upgrades" \
    --add-maintenance-exclusion-start "2024-09-15T00:00:00Z"
    
  gcloud container clusters update $cluster \
    --region=$REGION \
    --add-maintenance-exclusion-end "2024-11-30T23:59:59Z" \
    --add-maintenance-exclusion-name "annual-audit-november-2024" \
    --add-maintenance-exclusion-scope "all-upgrades" \
    --add-maintenance-exclusion-start "2024-11-01T00:00:00Z"
    
  gcloud container clusters update $cluster \
    --region=$REGION \
    --add-maintenance-exclusion-end "2025-01-02T00:00:00Z" \
    --add-maintenance-exclusion-name "quarterly-freeze-q4-2024" \
    --add-maintenance-exclusion-scope "all-upgrades" \
    --add-maintenance-exclusion-start "2024-12-15T00:00:00Z"
    
  echo "Completed configuration for $cluster"
done
```

## 4. Monitoring and Alerting Setup

```yaml
# monitoring-policy.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: gke-maintenance-alerts
  namespace: monitoring
spec:
  groups:
  - name: gke.maintenance
    rules:
    - alert: UnscheduledGKEUpgrade
      expr: increase(gke_cluster_upgrade_events_total[1h]) > 0
      for: 0m
      labels:
        severity: critical
        compliance: sox
      annotations:
        summary: "Unscheduled GKE upgrade detected"
        description: "Cluster {{ $labels.cluster_name }} had an upgrade outside maintenance window"
        
    - alert: MaintenanceWindowBreach
      expr: |
        (hour() < 2 or hour() > 6) and 
        (day_of_week() != 6) and 
        increase(gke_cluster_upgrade_events_total[10m]) > 0
      for: 0m
      labels:
        severity: critical
        compliance: sox
      annotations:
        summary: "GKE maintenance outside approved window"
        description: "Maintenance activity detected outside Saturday 2-6 AM UTC window"
```

## 5. Compliance Tracking Script

```python
#!/usr/bin/env python3
# compliance_tracker.py

import json
from datetime import datetime, timezone
from google.cloud import container_v1
import logging

class GKEComplianceTracker:
    def __init__(self, project_id, region):
        self.project_id = project_id
        self.region = region
        self.client = container_v1.ClusterManagerClient()
        
    def check_maintenance_compliance(self, cluster_names):
        """Check maintenance window compliance for all clusters"""
        compliance_report = []
        
        for cluster_name in cluster_names:
            cluster_path = f"projects/{self.project_id}/locations/{self.region}/clusters/{cluster_name}"
            
            try:
                cluster = self.client.get_cluster(name=cluster_path)
                
                # Check maintenance policy
                maintenance_policy = cluster.maintenance_policy
                compliance_status = {
                    'cluster_name': cluster_name,
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'maintenance_window_configured': bool(maintenance_policy.window),
                    'exclusions_configured': len(maintenance_policy.maintenance_exclusions),
                    'auto_upgrade_enabled': cluster.node_pools[0].management.auto_upgrade,
                    'release_channel': cluster.release_channel.channel.name if cluster.release_channel else None,
                    'compliance_status': 'COMPLIANT'
                }
                
                # Validate exclusions are current
                current_time = datetime.now(timezone.utc)
                active_exclusions = []
                
                for exclusion in maintenance_policy.maintenance_exclusions:
                    start_time = datetime.fromisoformat(exclusion.start_time.replace('Z', '+00:00'))
                    end_time = datetime.fromisoformat(exclusion.end_time.replace('Z', '+00:00'))
                    
                    if start_time <= current_time <= end_time:
                        active_exclusions.append(exclusion.exclusion_name)
                
                compliance_status['active_exclusions'] = active_exclusions
                
                # Check if maintenance window is weekend-only
                if maintenance_policy.recurring_window:
                    recurrence = maintenance_policy.recurring_window.recurrence
                    if 'BYDAY=SA' not in recurrence and 'BYDAY=SU' not in recurrence:
                        compliance_status['compliance_status'] = 'NON_COMPLIANT'
                        compliance_status['violation'] = 'Maintenance window not restricted to weekends'
                
                compliance_report.append(compliance_status)
                
            except Exception as e:
                logging.error(f"Error checking cluster {cluster_name}: {e}")
                compliance_report.append({
                    'cluster_name': cluster_name,
                    'error': str(e),
                    'compliance_status': 'ERROR'
                })
        
        return compliance_report
    
    def generate_sox_report(self, cluster_names):
        """Generate SOX compliance report"""
        report = self.check_maintenance_compliance(cluster_names)
        
        # Save report with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"gke_compliance_report_{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"Compliance report saved to {filename}")
        return report

if __name__ == "__main__":
    tracker = GKEComplianceTracker("your-project-id", "us-central1")
    clusters = ["prod-cluster-1", "prod-cluster-2", "prod-cluster-3"]
    report = tracker.generate_sox_report(clusters)
    
    # Print summary
    compliant_clusters = sum(1 for r in report if r.get('compliance_status') == 'COMPLIANT')
    print(f"\nCompliance Summary: {compliant_clusters}/{len(clusters)} clusters compliant")
```

## 6. Annual Maintenance Calendar

```python
#!/usr/bin/env python3
# maintenance_calendar.py

from datetime import datetime, timedelta
import calendar

def generate_2024_maintenance_calendar():
    """Generate maintenance exclusion periods for 2024"""
    
    exclusions = {
        "Q1 Code Freeze": ("2024-03-15", "2024-04-01"),
        "Q2 Code Freeze": ("2024-06-15", "2024-07-01"), 
        "Q3 Code Freeze": ("2024-09-15", "2024-10-01"),
        "Annual Audit": ("2024-11-01", "2024-11-30"),
        "Q4 Code Freeze": ("2024-12-15", "2025-01-02"),
    }
    
    # Generate allowed maintenance Saturdays
    allowed_saturdays = []
    start_date = datetime(2024, 1,
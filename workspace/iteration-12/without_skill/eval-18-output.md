I'll help you configure maintenance windows and exclusions for your GKE Standard clusters to meet your SOX compliance requirements. Here's a comprehensive setup:

## 1. Terraform Configuration for Maintenance Windows

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

# Current year for maintenance exclusions
variable "current_year" {
  description = "Current year for maintenance exclusions"
  type        = number
  default     = 2024
}

# maintenance-windows.tf
resource "google_container_cluster" "compliant_clusters" {
  count    = length(var.cluster_names)
  name     = var.cluster_names[count.index]
  location = var.region
  project  = var.project_id

  # Weekend-only maintenance window (Saturday 2 AM - 6 AM UTC)
  maintenance_policy {
    recurring_window {
      start_time = "2024-01-06T02:00:00Z" # First Saturday of 2024
      end_time   = "2024-01-06T06:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SA"
    }

    # Q1 Code Freeze (March 15-31)
    maintenance_exclusion {
      exclusion_name = "q1-code-freeze-${var.current_year}"
      start_time     = "${var.current_year}-03-15T00:00:00Z"
      end_time       = "${var.current_year}-03-31T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    # Q2 Code Freeze (June 15-30)
    maintenance_exclusion {
      exclusion_name = "q2-code-freeze-${var.current_year}"
      start_time     = "${var.current_year}-06-15T00:00:00Z"
      end_time       = "${var.current_year}-06-30T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    # Q3 Code Freeze (September 15-30)
    maintenance_exclusion {
      exclusion_name = "q3-code-freeze-${var.current_year}"
      start_time     = "${var.current_year}-09-15T00:00:00Z"
      end_time       = "${var.current_year}-09-30T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    # Q4 Code Freeze + Annual Audit (November 1 - December 15)
    maintenance_exclusion {
      exclusion_name = "q4-freeze-annual-audit-${var.current_year}"
      start_time     = "${var.current_year}-11-01T00:00:00Z"
      end_time       = "${var.current_year}-12-15T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    # Holiday blackout period (December 16-31, January 1-7)
    maintenance_exclusion {
      exclusion_name = "holiday-blackout-${var.current_year}"
      start_time     = "${var.current_year}-12-16T00:00:00Z"
      end_time       = "${var.current_year + 1}-01-07T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }
  }

  # Enable auto-upgrade for nodes
  node_pool {
    name       = "default-pool"
    node_count = 3

    management {
      auto_repair  = true
      auto_upgrade = true
    }

    upgrade_settings {
      max_surge       = 1
      max_unavailable = 1
      strategy        = "SURGE"
      
      # Blue-green upgrade for compliance
      blue_green_settings {
        standard_rollout_policy {
          batch_percentage    = 0.2
          batch_node_count    = 1
          batch_soak_duration = "300s"
        }
        node_pool_soak_duration = "1800s"
      }
    }
  }

  # Release channel for controlled updates
  release_channel {
    channel = "REGULAR"  # More predictable than RAPID, more current than STABLE
  }

  # Enable network policy for security compliance
  network_policy {
    enabled = true
  }

  # Enable master authorized networks for SOX compliance
  master_authorized_networks_config {
    cidr_blocks {
      cidr_block   = "10.0.0.0/8"
      display_name = "internal-network"
    }
  }

  # Enable logging and monitoring for audit trails
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
```

## 2. gcloud CLI Commands for Quick Setup

```bash
#!/bin/bash
# setup-maintenance-windows.sh

PROJECT_ID="your-project-id"
CLUSTERS=("prod-cluster-1" "prod-cluster-2" "prod-cluster-3")
REGION="us-central1"
CURRENT_YEAR=$(date +%Y)
NEXT_YEAR=$((CURRENT_YEAR + 1))

for cluster in "${CLUSTERS[@]}"; do
  echo "Configuring maintenance windows for $cluster..."
  
  # Set weekend maintenance window (Saturday 2-6 AM UTC)
  gcloud container clusters update $cluster \
    --project=$PROJECT_ID \
    --region=$REGION \
    --maintenance-window-start="2024-01-06T02:00:00Z" \
    --maintenance-window-end="2024-01-06T06:00:00Z" \
    --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SA"
  
  # Add maintenance exclusions
  
  # Q1 Code Freeze
  gcloud container clusters update $cluster \
    --project=$PROJECT_ID \
    --region=$REGION \
    --add-maintenance-exclusion-name="q1-code-freeze-$CURRENT_YEAR" \
    --add-maintenance-exclusion-start="${CURRENT_YEAR}-03-15T00:00:00Z" \
    --add-maintenance-exclusion-end="${CURRENT_YEAR}-03-31T23:59:59Z" \
    --add-maintenance-exclusion-scope="ALL_UPGRADES"
  
  # Q2 Code Freeze  
  gcloud container clusters update $cluster \
    --project=$PROJECT_ID \
    --region=$REGION \
    --add-maintenance-exclusion-name="q2-code-freeze-$CURRENT_YEAR" \
    --add-maintenance-exclusion-start="${CURRENT_YEAR}-06-15T00:00:00Z" \
    --add-maintenance-exclusion-end="${CURRENT_YEAR}-06-30T23:59:59Z" \
    --add-maintenance-exclusion-scope="ALL_UPGRADES"
  
  # Q3 Code Freeze
  gcloud container clusters update $cluster \
    --project=$PROJECT_ID \
    --region=$REGION \
    --add-maintenance-exclusion-name="q3-code-freeze-$CURRENT_YEAR" \
    --add-maintenance-exclusion-start="${CURRENT_YEAR}-09-15T00:00:00Z" \
    --add-maintenance-exclusion-end="${CURRENT_YEAR}-09-30T23:59:59Z" \
    --add-maintenance-exclusion-scope="ALL_UPGRADES"
  
  # Q4 + Annual Audit
  gcloud container clusters update $cluster \
    --project=$PROJECT_ID \
    --region=$REGION \
    --add-maintenance-exclusion-name="q4-audit-$CURRENT_YEAR" \
    --add-maintenance-exclusion-start="${CURRENT_YEAR}-11-01T00:00:00Z" \
    --add-maintenance-exclusion-end="${CURRENT_YEAR}-12-15T23:59:59Z" \
    --add-maintenance-exclusion-scope="ALL_UPGRADES"
  
  # Holiday Blackout
  gcloud container clusters update $cluster \
    --project=$PROJECT_ID \
    --region=$REGION \
    --add-maintenance-exclusion-name="holiday-blackout-$CURRENT_YEAR" \
    --add-maintenance-exclusion-start="${CURRENT_YEAR}-12-16T00:00:00Z" \
    --add-maintenance-exclusion-end="${NEXT_YEAR}-01-07T23:59:59Z" \
    --add-maintenance-exclusion-scope="ALL_UPGRADES"
  
  echo "Completed configuration for $cluster"
done
```

## 3. Monitoring and Alerting Configuration

```yaml
# monitoring-policy.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: maintenance-monitoring
  namespace: kube-system
data:
  alert-rules.yaml: |
    groups:
    - name: maintenance.rules
      rules:
      - alert: UnscheduledMaintenanceDetected
        expr: increase(gke_cluster_maintenance_events_total[1h]) > 0
        for: 0m
        labels:
          severity: critical
          compliance: sox
        annotations:
          summary: "Unscheduled GKE maintenance detected"
          description: "Cluster {{ $labels.cluster_name }} has maintenance activity outside of approved windows"
      
      - alert: MaintenanceWindowViolation
        expr: |
          (
            increase(gke_cluster_upgrades_total[1h]) > 0
          ) and (
            day_of_week() != 6  # Not Saturday
          )
        for: 0m
        labels:
          severity: critical
          compliance: sox
        annotations:
          summary: "GKE upgrade outside maintenance window"
          description: "Cluster upgrade occurred outside of approved Saturday maintenance window"

---
# Create monitoring dashboard
apiVersion: v1
kind: ConfigMap
metadata:
  name: compliance-dashboard
data:
  dashboard.json: |
    {
      "dashboard": {
        "title": "GKE SOX Compliance Dashboard",
        "panels": [
          {
            "title": "Maintenance Events Timeline",
            "type": "graph",
            "targets": [
              {
                "expr": "gke_cluster_maintenance_events_total",
                "legendFormat": "{{ cluster_name }}"
              }
            ]
          },
          {
            "title": "Upgrade Activity",
            "type": "graph", 
            "targets": [
              {
                "expr": "gke_cluster_upgrades_total",
                "legendFormat": "{{ cluster_name }} - {{ upgrade_type }}"
              }
            ]
          }
        ]
      }
    }
```

## 4. Automated Compliance Reporting

```python
#!/usr/bin/env python3
# compliance-report.py

import json
import datetime
from google.cloud import container_v1
from google.cloud import monitoring_v3

class GKEComplianceReporter:
    def __init__(self, project_id):
        self.project_id = project_id
        self.container_client = container_v1.ClusterManagerClient()
        self.monitoring_client = monitoring_v3.MetricServiceClient()
    
    def generate_maintenance_report(self, cluster_names, region):
        """Generate SOX compliance report for maintenance windows"""
        report = {
            "report_date": datetime.datetime.now().isoformat(),
            "project_id": self.project_id,
            "clusters": []
        }
        
        for cluster_name in cluster_names:
            cluster_path = f"projects/{self.project_id}/locations/{region}/clusters/{cluster_name}"
            
            try:
                cluster = self.container_client.get_cluster(name=cluster_path)
                
                cluster_report = {
                    "name": cluster_name,
                    "status": cluster.status.name,
                    "maintenance_policy": self._extract_maintenance_policy(cluster),
                    "compliance_status": self._check_compliance(cluster),
                    "last_maintenance": self._get_last_maintenance(cluster_name)
                }
                
                report["clusters"].append(cluster_report)
                
            except Exception as e:
                print(f"Error processing cluster {cluster_name}: {e}")
        
        return report
    
    def _extract_maintenance_policy(self, cluster):
        """Extract maintenance policy details"""
        if not cluster.maintenance_policy:
            return {"configured": False}
        
        policy = cluster.maintenance_policy
        exclusions = []
        
        for exclusion in policy.maintenance_exclusions:
            exclusions.append({
                "name": exclusion.exclusion_name,
                "start": exclusion.start_time,
                "end": exclusion.end_time,
                "scope": exclusion.exclusion_options.scope.name
            })
        
        return {
            "configured": True,
            "window": {
                "start_time": policy.window.daily_maintenance_window.start_time if policy.window.daily_maintenance_window else None,
                "recurrence": str(policy.window.recurring_window.recurrence) if policy.window.recurring_window else None
            },
            "exclusions": exclusions
        }
    
    def _check_compliance(self, cluster):
        """Check if cluster meets SOX compliance requirements"""
        compliance_checks = {
            "maintenance_window_configured": bool(cluster.maintenance_policy and cluster.maintenance_policy.window),
            "exclusions_configured": bool(cluster.maintenance_policy and cluster.maintenance_policy.maintenance_exclusions),
            "auto_repair_enabled": False,
            "auto_upgrade_enabled": False,
            "logging_enabled": bool(cluster.logging_config),
            "monitoring_enabled": bool(cluster.monitoring_config)
        }
        
        # Check node pool settings
        for node_pool in cluster.node_pools:
            if node_pool.management:
                compliance_checks["auto_repair_enabled"] = node_pool.management.auto_repair
                compliance_checks["auto_upgrade_enabled"] = node_pool.management.auto_upgrade
                break
        
        compliance_checks["overall_compliant"] = all(compliance_checks.values())
        return compliance_checks
    
    def _get_last_maintenance(self, cluster_name):
        """Get last maintenance activity from monitoring metrics"""
        # This would query Cloud Monitoring for maintenance events
        # Implementation depends on specific monitoring setup
        return {
            "last_upgrade": None,
            "last_repair": None,
            "within_window": None
        }

# Usage example
if __name__ == "__main__":
    reporter = GKEComplianceReporter("your-project-id")
    clusters = ["prod-cluster-1", "prod-cluster-2", "prod-cluster-3"]
    
    report = reporter.generate_maintenance_report(clusters, "us-central1")
    
    # Save report
    with open(f"gke-compliance-report-{datetime.date.today()}.json", "w") as f:
        json.dump(report, f, indent=2, default=str)
    
    print("Compliance report generated successfully")
```

## 5. Annual Maintenance Schedule Automation

```bash
#!/bin/bash
# annual-schedule-update.sh

# Script to update maintenance exclusions for the next year
# Run this in December to prepare for the following year

CURRENT_YEAR=$(date +%Y)
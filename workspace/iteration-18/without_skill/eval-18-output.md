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

# Current year for maintenance exclusions
variable "current_year" {
  description = "Current year for maintenance exclusions"
  type        = number
  default     = 2024
}

# main.tf - Maintenance Windows Configuration
resource "google_container_cluster" "regulated_clusters" {
  count    = length(var.cluster_names)
  name     = var.cluster_names[count.index]
  project  = var.project_id
  location = var.region

  # Weekend-only maintenance window (Saturday 2 AM - 6 AM UTC)
  maintenance_policy {
    recurring_window {
      start_time = "2024-01-06T02:00:00Z"  # First Saturday of 2024
      end_time   = "2024-01-06T06:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SA"   # Every Saturday
    }

    # Q1 Code Freeze (March)
    maintenance_exclusion {
      exclusion_name = "q1-code-freeze-${var.current_year}"
      start_time     = "${var.current_year}-03-01T00:00:00Z"
      end_time       = "${var.current_year}-03-31T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    # Q2 Code Freeze (June)
    maintenance_exclusion {
      exclusion_name = "q2-code-freeze-${var.current_year}"
      start_time     = "${var.current_year}-06-01T00:00:00Z"
      end_time       = "${var.current_year}-06-30T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    # Q3 Code Freeze (September)
    maintenance_exclusion {
      exclusion_name = "q3-code-freeze-${var.current_year}"
      start_time     = "${var.current_year}-09-01T00:00:00Z"
      end_time       = "${var.current_year}-09-30T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    # Q4 Code Freeze + Annual Audit (November - December)
    maintenance_exclusion {
      exclusion_name = "q4-code-freeze-annual-audit-${var.current_year}"
      start_time     = "${var.current_year}-11-01T00:00:00Z"
      end_time       = "${var.current_year}-12-31T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    # Holiday exclusion (Thanksgiving week - US financial markets)
    maintenance_exclusion {
      exclusion_name = "thanksgiving-week-${var.current_year}"
      start_time     = "${var.current_year}-11-25T00:00:00Z"
      end_time       = "${var.current_year}-12-01T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    # Year-end exclusion (additional protection)
    maintenance_exclusion {
      exclusion_name = "year-end-freeze-${var.current_year}"
      start_time     = "${var.current_year}-12-20T00:00:00Z"
      end_time       = "${var.current_year + 1}-01-05T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }
  }

  # Node pool configuration with weekend maintenance
  node_pool {
    name       = "default-pool"
    node_count = 3

    management {
      auto_repair  = true
      auto_upgrade = true
    }

    upgrade_settings {
      strategy      = "SURGE"
      max_surge     = 1
      max_unavailable = 0
    }
  }

  # Enable network policy for security
  network_policy {
    enabled = true
  }

  # Enable workload identity for SOX compliance
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  # Logging and monitoring for audit trails
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
      "API_SERVER"
    ]
  }
}
```

## 2. gcloud CLI Commands

```bash
#!/bin/bash
# configure-maintenance-windows.sh

PROJECT_ID="your-project-id"
CLUSTERS=("prod-cluster-1" "prod-cluster-2" "prod-cluster-3")
REGION="us-central1"
CURRENT_YEAR=$(date +%Y)

for cluster in "${CLUSTERS[@]}"; do
  echo "Configuring maintenance window for cluster: $cluster"
  
  # Set weekend maintenance window (Saturday 2-6 AM UTC)
  gcloud container clusters update $cluster \
    --project=$PROJECT_ID \
    --region=$REGION \
    --maintenance-window-start="2024-01-06T02:00:00Z" \
    --maintenance-window-end="2024-01-06T06:00:00Z" \
    --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SA"

  # Add Q1 code freeze exclusion
  gcloud container clusters update $cluster \
    --project=$PROJECT_ID \
    --region=$REGION \
    --add-maintenance-exclusion-end="${CURRENT_YEAR}-03-31T23:59:59Z" \
    --add-maintenance-exclusion-name="q1-code-freeze-${CURRENT_YEAR}" \
    --add-maintenance-exclusion-scope="all_upgrades" \
    --add-maintenance-exclusion-start="${CURRENT_YEAR}-03-01T00:00:00Z"

  # Add Q2 code freeze exclusion  
  gcloud container clusters update $cluster \
    --project=$PROJECT_ID \
    --region=$REGION \
    --add-maintenance-exclusion-end="${CURRENT_YEAR}-06-30T23:59:59Z" \
    --add-maintenance-exclusion-name="q2-code-freeze-${CURRENT_YEAR}" \
    --add-maintenance-exclusion-scope="all_upgrades" \
    --add-maintenance-exclusion-start="${CURRENT_YEAR}-06-01T00:00:00Z"

  # Add Q3 code freeze exclusion
  gcloud container clusters update $cluster \
    --project=$PROJECT_ID \
    --region=$REGION \
    --add-maintenance-exclusion-end="${CURRENT_YEAR}-09-30T23:59:59Z" \
    --add-maintenance-exclusion-name="q3-code-freeze-${CURRENT_YEAR}" \
    --add-maintenance-exclusion-scope="all_upgrades" \
    --add-maintenance-exclusion-start="${CURRENT_YEAR}-09-01T00:00:00Z"

  # Add Q4 code freeze + annual audit exclusion
  gcloud container clusters update $cluster \
    --project=$PROJECT_ID \
    --region=$REGION \
    --add-maintenance-exclusion-end="${CURRENT_YEAR}-12-31T23:59:59Z" \
    --add-maintenance-exclusion-name="q4-audit-freeze-${CURRENT_YEAR}" \
    --add-maintenance-exclusion-scope="all_upgrades" \
    --add-maintenance-exclusion-start="${CURRENT_YEAR}-11-01T00:00:00Z"

  echo "Maintenance configuration completed for $cluster"
done
```

## 3. Monitoring and Alerting Script

```bash
#!/bin/bash
# maintenance-monitoring.sh

# Create Pub/Sub topic for maintenance notifications
gcloud pubsub topics create gke-maintenance-notifications

# Create alert policy for maintenance events
cat > maintenance-alert-policy.yaml << 'EOF'
displayName: "GKE Maintenance Events"
documentation:
  content: "Alert when GKE maintenance events occur for SOX compliance tracking"
conditions:
  - displayName: "GKE Maintenance Activity"
    conditionThreshold:
      filter: 'resource.type="gke_cluster" AND protoPayload.methodName=~"google.container.*"'
      comparison: COMPARISON_GREATER_THAN
      thresholdValue: 0
      duration: 60s
alertStrategy:
  autoClose: 86400s
notificationChannels:
  - projects/PROJECT_ID/notificationChannels/NOTIFICATION_CHANNEL_ID
EOF

gcloud alpha monitoring policies create --policy-from-file=maintenance-alert-policy.yaml
```

## 4. Validation and Compliance Script

```python
#!/usr/bin/env python3
# validate_maintenance_config.py

from google.cloud import container_v1
import json
from datetime import datetime, timezone
import sys

def validate_cluster_maintenance_config(project_id, cluster_names, region):
    """Validate maintenance configuration for SOX compliance"""
    
    client = container_v1.ClusterManagerClient()
    
    compliance_report = {
        "validation_date": datetime.now(timezone.utc).isoformat(),
        "clusters": {}
    }
    
    for cluster_name in cluster_names:
        cluster_path = f"projects/{project_id}/locations/{region}/clusters/{cluster_name}"
        
        try:
            cluster = client.get_cluster(name=cluster_path)
            
            cluster_compliance = {
                "maintenance_window_configured": False,
                "weekend_only": False,
                "code_freeze_exclusions": [],
                "audit_exclusions": [],
                "compliance_status": "NON_COMPLIANT"
            }
            
            if cluster.maintenance_policy:
                maintenance_policy = cluster.maintenance_policy
                
                # Check maintenance window
                if maintenance_policy.window:
                    cluster_compliance["maintenance_window_configured"] = True
                    
                    # Validate weekend-only schedule
                    if hasattr(maintenance_policy.window, 'recurring_window'):
                        recurrence = maintenance_policy.window.recurring_window.recurrence
                        if "BYDAY=SA" in recurrence:
                            cluster_compliance["weekend_only"] = True
                
                # Check maintenance exclusions
                exclusions = []
                for exclusion in maintenance_policy.maintenance_exclusions:
                    exclusion_info = {
                        "name": exclusion.exclusion_name,
                        "start": exclusion.start_time,
                        "end": exclusion.end_time,
                        "scope": exclusion.exclusion_options.scope
                    }
                    exclusions.append(exclusion_info)
                    
                    # Categorize exclusions
                    if "code-freeze" in exclusion.exclusion_name.lower():
                        cluster_compliance["code_freeze_exclusions"].append(exclusion_info)
                    elif "audit" in exclusion.exclusion_name.lower():
                        cluster_compliance["audit_exclusions"].append(exclusion_info)
                
                # Determine compliance status
                if (cluster_compliance["maintenance_window_configured"] and
                    cluster_compliance["weekend_only"] and
                    len(cluster_compliance["code_freeze_exclusions"]) >= 4 and
                    len(cluster_compliance["audit_exclusions"]) >= 1):
                    cluster_compliance["compliance_status"] = "COMPLIANT"
            
            compliance_report["clusters"][cluster_name] = cluster_compliance
            
        except Exception as e:
            compliance_report["clusters"][cluster_name] = {
                "error": str(e),
                "compliance_status": "ERROR"
            }
    
    return compliance_report

if __name__ == "__main__":
    project_id = "your-project-id"
    cluster_names = ["prod-cluster-1", "prod-cluster-2", "prod-cluster-3"]
    region = "us-central1"
    
    report = validate_cluster_maintenance_config(project_id, cluster_names, region)
    
    print(json.dumps(report, indent=2))
    
    # Check overall compliance
    all_compliant = all(
        cluster.get("compliance_status") == "COMPLIANT" 
        for cluster in report["clusters"].values()
    )
    
    if not all_compliant:
        print("\nWARNING: Not all clusters are compliant with maintenance policy requirements!")
        sys.exit(1)
    else:
        print("\nSUCCESS: All clusters are compliant with SOX maintenance requirements.")
```

## 5. Annual Maintenance Calendar Generator

```python
#!/usr/bin/env python3
# generate_maintenance_calendar.py

from datetime import datetime, timedelta
import calendar
import json

def generate_annual_maintenance_calendar(year):
    """Generate maintenance calendar for SOX compliance planning"""
    
    calendar_data = {
        "year": year,
        "maintenance_windows": [],
        "exclusion_periods": [],
        "allowed_maintenance_dates": []
    }
    
    # Define exclusion periods
    exclusions = [
        {"name": "Q1 Code Freeze", "start": f"{year}-03-01", "end": f"{year}-03-31"},
        {"name": "Q2 Code Freeze", "start": f"{year}-06-01", "end": f"{year}-06-30"},
        {"name": "Q3 Code Freeze", "start": f"{year}-09-01", "end": f"{year}-09-30"},
        {"name": "Q4 Code Freeze + Audit", "start": f"{year}-11-01", "end": f"{year}-12-31"},
    ]
    
    calendar_data["exclusion_periods"] = exclusions
    
    # Generate all Saturdays in the year
    start_date = datetime(year, 1, 1)
    end_date = datetime(year, 12, 31)
    
    current_date = start_date
    while current_date <= end_date:
        if current_date.weekday() == 5:  # Saturday
            saturday_str = current_date.strftime("%Y-%m-%d")
            
            # Check if this Saturday falls in an exclusion period
            in_exclusion = False
            for exclusion in exclusions:
                exclusion_start = datetime.strptime(exclusion["start"], "%Y-%m-%d")
                exclusion_end = datetime.strptime(exclusion["end"], "%Y-%m-%d")
                
                if exclusion_start <= current_date <= exclusion_end:
                    in_exclusion = True
                    break
            
            window_info = {
                "date": saturday_str,
                "maintenance_window": "02:00-06:00 UTC",
                "available": not in_exclusion,
                "exclusion_reason": "Code freeze or audit period" if in_exclusion else None
            }
            
            calendar_data["maintenance_windows"].append(window_info)
            
            if not in_exclusion:
                calendar_data["allowed_maintenance_dates"].append(saturday_str)
        
        current_date += timedelta(days=1)
    
    return calendar_data

if __name__ == "__main__":
    current_year = datetime.now().year
    calendar_data = generate_annual_maintenance_calendar(
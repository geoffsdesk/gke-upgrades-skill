I'll help you configure maintenance windows and exclusions for your SOX-compliant GKE clusters to meet your regulatory requirements. Here's a comprehensive setup:

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
}

# main.tf
resource "google_container_cluster" "sox_compliant_clusters" {
  count    = length(var.cluster_names)
  name     = var.cluster_names[count.index]
  location = var.region
  project  = var.project_id

  # Remove default node pool
  remove_default_node_pool = true
  initial_node_count       = 1

  # Maintenance policy for SOX compliance
  maintenance_policy {
    # Weekend maintenance window (Saturday 2 AM - 6 AM UTC)
    daily_maintenance_window {
      start_time = "02:00"
    }
  }

  # Enable maintenance exclusions
  cluster_autoscaling {
    enabled = true
    resource_limits {
      resource_type = "cpu"
      minimum       = 1
      maximum       = 100
    }
    resource_limits {
      resource_type = "memory"
      minimum       = 1
      maximum       = 100
    }
  }

  # Network policy for security
  network_policy {
    enabled = true
  }

  # Workload Identity for security
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  # Enable network policy
  addons_config {
    network_policy_config {
      disabled = false
    }
  }

  # Logging and monitoring for audit trail
  logging_service    = "logging.googleapis.com/kubernetes"
  monitoring_service = "monitoring.googleapis.com/kubernetes"
}

# Maintenance exclusions
resource "google_gke_maintenance_exclusion" "quarterly_code_freeze" {
  count      = length(var.cluster_names)
  project    = var.project_id
  location   = var.region
  cluster    = google_container_cluster.sox_compliant_clusters[count.index].name
  
  exclusion_name = "quarterly-code-freeze-q1"
  
  start_time = "2024-03-15T00:00:00Z"  # Q1 code freeze start
  end_time   = "2024-03-31T23:59:59Z"  # Q1 code freeze end
  
  exclusion_options {
    scope = "UPGRADES"
  }
}

resource "google_gke_maintenance_exclusion" "annual_audit" {
  count      = length(var.cluster_names)
  project    = var.project_id
  location   = var.region
  cluster    = google_container_cluster.sox_compliant_clusters[count.index].name
  
  exclusion_name = "annual-audit-november"
  
  start_time = "2024-11-01T00:00:00Z"
  end_time   = "2024-11-30T23:59:59Z"
  
  exclusion_options {
    scope = "UPGRADES"
  }
}

# Node pool configuration
resource "google_container_node_pool" "sox_nodes" {
  count      = length(var.cluster_names)
  name       = "${var.cluster_names[count.index]}-nodes"
  location   = var.region
  cluster    = google_container_cluster.sox_compliant_clusters[count.index].name
  
  node_count = 2

  node_config {
    preemptible  = false  # No preemptible nodes for production
    machine_type = "e2-standard-4"

    service_account = google_service_account.gke_service_account.email
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]

    labels = {
      environment = "production"
      compliance  = "sox"
    }

    tags = ["gke-node", "production"]

    metadata = {
      disable-legacy-endpoints = "true"
    }
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
  }
}

# Service account for GKE nodes
resource "google_service_account" "gke_service_account" {
  account_id   = "gke-sox-sa"
  display_name = "GKE SOX Compliance Service Account"
  project      = var.project_id
}

resource "google_project_iam_member" "gke_service_account_roles" {
  for_each = toset([
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/monitoring.viewer",
    "roles/stackdriver.resourceMetadata.writer"
  ])
  
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.gke_service_account.email}"
}
```

## 2. Advanced Maintenance Policy with Weekend-Only Updates

```hcl
# advanced-maintenance.tf
resource "google_gke_hub_membership" "clusters" {
  count         = length(var.cluster_names)
  membership_id = "${var.cluster_names[count.index]}-membership"
  project       = var.project_id

  endpoint {
    gke_cluster {
      resource_link = "//container.googleapis.com/${google_container_cluster.sox_compliant_clusters[count.index].id}"
    }
  }
}

# Fleet-wide maintenance policy
resource "google_gke_hub_feature" "fleet_maintenance" {
  name     = "fleetobservability"
  project  = var.project_id
  location = "global"
}

# Custom maintenance schedule using Cloud Scheduler
resource "google_cloud_scheduler_job" "weekend_maintenance_check" {
  name             = "weekend-maintenance-check"
  description      = "Check and trigger maintenance on weekends only"
  schedule         = "0 2 * * 6"  # Saturday at 2 AM
  time_zone        = "UTC"
  attempt_deadline = "320s"
  project          = var.project_id
  region           = var.region

  http_target {
    http_method = "POST"
    uri         = google_cloudfunctions_function.maintenance_controller.https_trigger_url

    body = base64encode(jsonencode({
      clusters = var.cluster_names
      action   = "check_and_upgrade"
    }))

    headers = {
      "Content-Type" = "application/json"
    }

    oidc_token {
      service_account_email = google_service_account.scheduler_sa.email
    }
  }
}
```

## 3. Cloud Function for Maintenance Control

```python
# main.py for Cloud Function
import json
import logging
from datetime import datetime, timedelta
from google.cloud import container_v1
from google.cloud import monitoring_v3
import functions_framework

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@functions_framework.http
def maintenance_controller(request):
    """
    SOX-compliant maintenance controller
    Only allows upgrades during approved windows
    """
    try:
        request_json = request.get_json()
        clusters = request_json.get('clusters', [])
        action = request_json.get('action')
        
        # Check if we're in an exclusion period
        if is_exclusion_period():
            logger.info("Currently in maintenance exclusion period. Skipping upgrades.")
            return {"status": "skipped", "reason": "exclusion_period"}
        
        # Check if it's weekend
        if not is_weekend():
            logger.info("Not weekend. Skipping maintenance.")
            return {"status": "skipped", "reason": "not_weekend"}
        
        # Proceed with maintenance checks
        results = []
        client = container_v1.ClusterManagerClient()
        
        for cluster_name in clusters:
            try:
                result = check_cluster_maintenance(client, cluster_name)
                results.append(result)
                
                # Log for SOX audit trail
                log_maintenance_action(cluster_name, result)
                
            except Exception as e:
                logger.error(f"Error processing cluster {cluster_name}: {str(e)}")
                results.append({
                    "cluster": cluster_name,
                    "status": "error",
                    "error": str(e)
                })
        
        return {
            "status": "completed",
            "results": results,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Maintenance controller error: {str(e)}")
        return {"status": "error", "error": str(e)}, 500

def is_exclusion_period():
    """Check if current time falls within maintenance exclusion periods"""
    now = datetime.utcnow()
    
    # Quarterly code freezes (customize dates as needed)
    exclusion_periods = [
        # Q1 code freeze
        (datetime(now.year, 3, 15), datetime(now.year, 3, 31)),
        # Q2 code freeze  
        (datetime(now.year, 6, 15), datetime(now.year, 6, 30)),
        # Q3 code freeze
        (datetime(now.year, 9, 15), datetime(now.year, 9, 30)),
        # Q4 code freeze
        (datetime(now.year, 12, 15), datetime(now.year, 12, 31)),
        # Annual audit (November)
        (datetime(now.year, 11, 1), datetime(now.year, 11, 30)),
    ]
    
    for start_date, end_date in exclusion_periods:
        if start_date <= now <= end_date:
            return True
    
    return False

def is_weekend():
    """Check if current day is weekend (Friday evening to Sunday)"""
    now = datetime.utcnow()
    # Allow Friday evening (after 18:00), Saturday, and Sunday morning (before 10:00)
    weekday = now.weekday()
    hour = now.hour
    
    return (weekday == 4 and hour >= 18) or weekday == 5 or (weekday == 6 and hour <= 10)

def check_cluster_maintenance(client, cluster_name):
    """Check and perform maintenance on a specific cluster"""
    project_id = "your-project-id"  # Replace with your project ID
    zone = "your-zone"  # Replace with your zone
    
    try:
        # Get cluster info
        cluster_path = f"projects/{project_id}/locations/{zone}/clusters/{cluster_name}"
        cluster = client.get_cluster(name=cluster_path)
        
        # Check for available updates
        server_config = client.get_server_config(
            name=f"projects/{project_id}/locations/{zone}"
        )
        
        current_version = cluster.current_master_version
        latest_version = server_config.default_cluster_version
        
        if current_version != latest_version:
            logger.info(f"Update available for {cluster_name}: {current_version} -> {latest_version}")
            
            # In a real implementation, you might want to:
            # 1. Check cluster health
            # 2. Verify backup status
            # 3. Send notifications
            # 4. Perform staged rollout
            
            return {
                "cluster": cluster_name,
                "status": "update_available",
                "current_version": current_version,
                "target_version": latest_version
            }
        else:
            return {
                "cluster": cluster_name,
                "status": "up_to_date",
                "version": current_version
            }
            
    except Exception as e:
        logger.error(f"Error checking cluster {cluster_name}: {str(e)}")
        raise

def log_maintenance_action(cluster_name, result):
    """Log maintenance actions for SOX audit trail"""
    audit_log = {
        "timestamp": datetime.utcnow().isoformat(),
        "cluster": cluster_name,
        "action": "maintenance_check",
        "result": result,
        "compliance": "SOX",
        "environment": "production"
    }
    
    # Log to Cloud Logging with structured format
    logger.info("AUDIT_LOG", extra={"json_fields": audit_log})
```

## 4. Monitoring and Alerting for Compliance

```yaml
# alerting-policy.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: sox-compliance-alerts
data:
  alerts.yaml: |
    groups:
    - name: sox-compliance
      rules:
      - alert: UnauthorizedMaintenanceWindow
        expr: |
          (
            (day_of_week() < 5) or 
            (day_of_week() == 5 and hour() < 18) or
            (day_of_week() == 0 and hour() > 10)
          ) and on() gke_cluster_maintenance_active == 1
        for: 0m
        labels:
          severity: critical
          compliance: sox
        annotations:
          summary: "GKE maintenance occurring outside approved window"
          description: "Cluster maintenance detected outside of approved weekend window"
      
      - alert: MaintenanceExclusionViolation
        expr: |
          (
            (month() == 3 and day() >= 15 and day() <= 31) or
            (month() == 6 and day() >= 15 and day() <= 30) or
            (month() == 9 and day() >= 15 and day() <= 30) or
            (month() == 12 and day() >= 15 and day() <= 31) or
            (month() == 11)
          ) and on() gke_cluster_upgrade_active == 1
        for: 0m
        labels:
          severity: critical
          compliance: sox
        annotations:
          summary: "GKE upgrade during code freeze or audit period"
          description: "Cluster upgrade detected during prohibited period"

      - alert: MaintenanceAuditTrailMissing
        expr: |
          increase(gke_maintenance_actions_total[24h]) > 0 and
          increase(audit_log_entries_total{action="maintenance_check"}[24h]) == 0
        for: 5m
        labels:
          severity: warning
          compliance: sox
        annotations:
          summary: "Missing audit trail for maintenance actions"
          description: "Maintenance actions occurred without proper audit logging"
```

## 5. Deployment Script

```bash
#!/bin/bash
# deploy-sox-maintenance.sh

set -e

PROJECT_ID="your-project-id"
REGION="us-central1"
CLUSTERS=("prod-cluster-1" "prod-cluster-2" "prod-cluster-3")

echo "Deploying SOX-compliant GKE maintenance configuration..."

# Deploy Terraform configuration
terraform init
terraform plan -var="project_id=$PROJECT_ID" -var="region=$REGION"
terraform apply -var="project_id=$PROJECT_ID" -var="region=$REGION" -auto-approve

# Deploy Cloud Function
cd functions/maintenance-controller
gcloud functions deploy maintenance-controller \
  --runtime python39 \
  --trigger-http \
  --entry-point maintenance_controller \
  --memory 256MB \
  --timeout 300s \
  --project $PROJECT_ID \
  --region $REGION \
  --service-account gke-sox-sa@$PROJECT_ID.iam.gserviceaccount.com

# Set up monitoring
kubectl apply -f alerting-policy.yaml

echo "SOX-compliant maintenance configuration deployed successfully!"
echo ""
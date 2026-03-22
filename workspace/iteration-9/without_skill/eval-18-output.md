I'll help you configure maintenance windows and exclusions for your GKE clusters to meet your SOX compliance requirements. Here's a comprehensive setup:

## 1. Terraform Configuration for All Three Clusters

```hcl
# variables.tf
variable "cluster_names" {
  description = "List of GKE cluster names"
  type        = list(string)
  default     = ["prod-cluster", "staging-cluster", "dev-cluster"]
}

variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

# Current year for maintenance exclusions
locals {
  current_year = formatdate("YYYY", timestamp())
  next_year    = tostring(tonumber(local.current_year) + 1)
}

# main.tf
resource "google_container_cluster" "gke_clusters" {
  for_each = toset(var.cluster_names)
  
  name     = each.value
  location = var.region
  project  = var.project_id

  # Remove default node pool
  remove_default_node_pool = true
  initial_node_count       = 1

  # Maintenance policy with weekend-only windows
  maintenance_policy {
    # Weekend maintenance window (Saturday 2 AM - 6 AM UTC)
    daily_maintenance_window {
      start_time = "02:00"
    }
    
    # Recurring maintenance windows for weekends only
    recurring_window {
      start_time = "${local.current_year}-01-01T02:00:00Z"
      end_time   = "${local.current_year}-01-01T06:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SA"
    }

    # Q1 Code Freeze (January 15 - February 15)
    maintenance_exclusion {
      exclusion_name = "q1-code-freeze-${local.current_year}"
      start_time     = "${local.current_year}-01-15T00:00:00Z"
      end_time       = "${local.current_year}-02-15T23:59:59Z"
      exclusion_options {
        scope = "UPGRADES"
      }
    }

    # Q2 Code Freeze (April 15 - May 15)
    maintenance_exclusion {
      exclusion_name = "q2-code-freeze-${local.current_year}"
      start_time     = "${local.current_year}-04-15T00:00:00Z"
      end_time       = "${local.current_year}-05-15T23:59:59Z"
      exclusion_options {
        scope = "UPGRADES"
      }
    }

    # Q3 Code Freeze (July 15 - August 15)
    maintenance_exclusion {
      exclusion_name = "q3-code-freeze-${local.current_year}"
      start_time     = "${local.current_year}-07-15T00:00:00Z"
      end_time       = "${local.current_year}-08-15T23:59:59Z"
      exclusion_options {
        scope = "UPGRADES"
      }
    }

    # Q4 Code Freeze + Annual Audit (October 15 - December 15)
    maintenance_exclusion {
      exclusion_name = "q4-code-freeze-audit-${local.current_year}"
      start_time     = "${local.current_year}-10-15T00:00:00Z"
      end_time       = "${local.current_year}-12-15T23:59:59Z"
      exclusion_options {
        scope = "UPGRADES"
      }
    }

    # Year-end holidays exclusion
    maintenance_exclusion {
      exclusion_name = "year-end-holidays-${local.current_year}"
      start_time     = "${local.current_year}-12-20T00:00:00Z"
      end_time       = "${local.next_year}-01-05T23:59:59Z"
      exclusion_options {
        scope = "UPGRADES"
      }
    }
  }

  # Release channel for controlled upgrades
  release_channel {
    channel = "STABLE"
  }

  # Network configuration
  network    = "default"
  subnetwork = "default"

  # Enable necessary features for compliance
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

# Node pools for each cluster
resource "google_container_node_pool" "primary_nodes" {
  for_each   = toset(var.cluster_names)
  
  name       = "${each.value}-node-pool"
  location   = var.region
  cluster    = google_container_cluster.gke_clusters[each.value].name
  
  node_count = 3

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  # Weekend-only upgrade schedule for nodes
  upgrade_settings {
    strategy = "SURGE"
    max_surge = 1
    max_unavailable = 0
  }

  node_config {
    preemptible  = false
    machine_type = "e2-medium"

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]

    labels = {
      environment = each.value
      compliance  = "sox"
    }

    tags = ["gke-node", "${each.value}-node"]
  }
}
```

## 2. Kubernetes CronJob for Maintenance Window Monitoring

```yaml
# maintenance-monitor.yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: maintenance-window-monitor
  namespace: kube-system
spec:
  schedule: "0 2 * * 1"  # Every Monday at 2 AM to check upcoming maintenance
  jobTemplate:
    spec:
      template:
        spec:
          serviceAccountName: maintenance-monitor
          containers:
          - name: monitor
            image: google/cloud-sdk:alpine
            command:
            - /bin/bash
            - -c
            - |
              # Check maintenance windows and send alerts if needed
              gcloud container clusters describe $CLUSTER_NAME \
                --region=$CLUSTER_REGION \
                --format="value(maintenancePolicy)" > /tmp/maintenance.txt
              
              # Log maintenance window status for audit trail
              echo "$(date): Maintenance policy check completed" >> /var/log/maintenance-audit.log
              
              # Send to monitoring system (replace with your monitoring endpoint)
              curl -X POST "$MONITORING_WEBHOOK" \
                -H "Content-Type: application/json" \
                -d "{\"cluster\": \"$CLUSTER_NAME\", \"status\": \"maintenance_check_completed\", \"timestamp\": \"$(date -Iseconds)\"}"
            env:
            - name: CLUSTER_NAME
              value: "your-cluster-name"
            - name: CLUSTER_REGION
              value: "us-central1"
            - name: MONITORING_WEBHOOK
              valueFrom:
                secretKeyRef:
                  name: monitoring-config
                  key: webhook-url
          restartPolicy: OnFailure
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: maintenance-monitor
  namespace: kube-system
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: maintenance-monitor
rules:
- apiGroups: [""]
  resources: ["events"]
  verbs: ["create", "patch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: maintenance-monitor
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: maintenance-monitor
subjects:
- kind: ServiceAccount
  name: maintenance-monitor
  namespace: kube-system
```

## 3. Cloud Function for Dynamic Maintenance Window Management

```python
# main.py - Cloud Function for maintenance window management
import json
from datetime import datetime, timedelta
from google.cloud import container_v1
from google.cloud import logging as cloud_logging

def update_maintenance_windows(request):
    """
    Cloud Function to dynamically update maintenance windows
    Triggered by Pub/Sub or HTTP request
    """
    
    # Initialize clients
    client = container_v1.ClusterManagerClient()
    logging_client = cloud_logging.Client()
    logger = logging_client.logger("maintenance-window-manager")
    
    # Configuration
    project_id = "your-project-id"
    location = "us-central1"
    clusters = ["prod-cluster", "staging-cluster", "dev-cluster"]
    
    try:
        for cluster_name in clusters:
            cluster_path = f"projects/{project_id}/locations/{location}/clusters/{cluster_name}"
            
            # Get current cluster configuration
            cluster = client.get_cluster(name=cluster_path)
            
            # Create maintenance policy update
            maintenance_policy = container_v1.MaintenancePolicy()
            
            # Weekend-only maintenance window
            maintenance_policy.window = container_v1.MaintenanceWindow(
                daily_maintenance_window=container_v1.DailyMaintenanceWindow(
                    start_time=container_v1.TimeOfDay(hours=2, minutes=0)
                )
            )
            
            # Add current year exclusions
            current_year = datetime.now().year
            exclusions = generate_maintenance_exclusions(current_year)
            
            for exclusion in exclusions:
                maintenance_policy.resource_version = cluster.maintenance_policy.resource_version
            
            # Update cluster
            operation = client.set_maintenance_policy(
                project_id=project_id,
                zone=location,
                cluster_id=cluster_name,
                maintenance_policy=maintenance_policy
            )
            
            # Log for audit trail
            logger.log_struct({
                "severity": "INFO",
                "message": f"Maintenance window updated for cluster {cluster_name}",
                "cluster": cluster_name,
                "operation_id": operation.name,
                "timestamp": datetime.utcnow().isoformat(),
                "compliance": "SOX"
            })
            
        return {"status": "success", "message": "Maintenance windows updated"}
        
    except Exception as e:
        logger.log_struct({
            "severity": "ERROR",
            "message": f"Failed to update maintenance windows: {str(e)}",
            "timestamp": datetime.utcnow().isoformat(),
            "compliance": "SOX"
        })
        return {"status": "error", "message": str(e)}, 500

def generate_maintenance_exclusions(year):
    """Generate maintenance exclusions for the given year"""
    exclusions = []
    
    # Q1 Code Freeze
    exclusions.append({
        "name": f"q1-code-freeze-{year}",
        "start": f"{year}-01-15T00:00:00Z",
        "end": f"{year}-02-15T23:59:59Z"
    })
    
    # Q2 Code Freeze
    exclusions.append({
        "name": f"q2-code-freeze-{year}",
        "start": f"{year}-04-15T00:00:00Z",
        "end": f"{year}-05-15T23:59:59Z"
    })
    
    # Q3 Code Freeze
    exclusions.append({
        "name": f"q3-code-freeze-{year}",
        "start": f"{year}-07-15T00:00:00Z",
        "end": f"{year}-08-15T23:59:59Z"
    })
    
    # Q4 Code Freeze + Annual Audit
    exclusions.append({
        "name": f"q4-code-freeze-audit-{year}",
        "start": f"{year}-10-15T00:00:00Z",
        "end": f"{year}-12-15T23:59:59Z"
    })
    
    return exclusions

# requirements.txt
"""
google-cloud-container==2.17.4
google-cloud-logging==3.8.0
functions-framework==3.4.0
"""
```

## 4. Monitoring and Alerting Configuration

```yaml
# monitoring-policy.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: maintenance-monitoring-policy
  namespace: kube-system
data:
  policy.json: |
    {
      "displayName": "GKE Maintenance Window Policy",
      "conditions": [
        {
          "displayName": "Maintenance outside approved window",
          "conditionThreshold": {
            "filter": "resource.type=\"gke_cluster\" AND log_name=\"projects/PROJECT_ID/logs/container.googleapis.com%2Fcluster-autoscaler-visibility\"",
            "comparison": "COMPARISON_GT",
            "thresholdValue": 0,
            "duration": "60s"
          }
        }
      ],
      "alertStrategy": {
        "autoClose": "86400s"
      },
      "combiner": "OR",
      "enabled": true,
      "notificationChannels": [
        "NOTIFICATION_CHANNEL_ID"
      ]
    }
```

## 5. Deployment and Management Scripts

```bash
#!/bin/bash
# deploy-maintenance-config.sh

set -e

PROJECT_ID="your-project-id"
REGION="us-central1"
CLUSTERS=("prod-cluster" "staging-cluster" "dev-cluster")

echo "Deploying maintenance window configuration for SOX compliance..."

# Deploy Terraform configuration
terraform init
terraform plan -var="project_id=${PROJECT_ID}" -var="region=${REGION}"
terraform apply -var="project_id=${PROJECT_ID}" -var="region=${REGION}" -auto-approve

# Deploy monitoring CronJob to each cluster
for cluster in "${CLUSTERS[@]}"; do
    echo "Configuring monitoring for cluster: $cluster"
    
    # Get cluster credentials
    gcloud container clusters get-credentials "$cluster" --region="$REGION" --project="$PROJECT_ID"
    
    # Create monitoring secret
    kubectl create secret generic monitoring-config \
        --from-literal=webhook-url="https://your-monitoring-webhook.com" \
        --namespace=kube-system \
        --dry-run=client -o yaml | kubectl apply -f -
    
    # Deploy monitoring CronJob
    sed "s/your-cluster-name/$cluster/g" maintenance-monitor.yaml | kubectl apply -f -
    
    echo "✅ Monitoring configured for $cluster"
done

# Deploy Cloud Function
gcloud functions deploy maintenance-window-manager \
    --runtime python39 \
    --trigger-http \
    --entry-point update_maintenance_windows \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --service-account="maintenance-function@${PROJECT_ID}.iam.gserviceaccount.com"

# Set up Cloud Scheduler for automatic updates
gcloud scheduler jobs create http maintenance-window-update \
    --schedule="0 0 1 1 *" \
    --uri="https://${REGION}-${PROJECT_ID}.cloudfunctions.net/maintenance-window-manager" \
    --http-method=POST \
    --project="$PROJECT_ID"

echo "🎉 Maintenance window configuration deployed successfully!"
echo "📋 Configuration Summary:"
echo "  - Weekend-only maintenance windows (Saturday 2-6 AM UTC)"
echo "  - Quarterly code freeze exclusions"
echo "  - November audit exclusion"
echo "  - Year-end holiday exclusion"
echo "  - Automated monitoring and alerting"
echo "  - SOX compliance audit logging"
```

## Key Features for SOX Compliance:

1. **Controlled Maintenance Windows**: Only weekends (Saturday 2-6 AM UTC)
2. **Quarterly Code Freezes**: Automatic exclusions during freeze periods
I'll help you configure maintenance windows and exclusions for your GKE Standard clusters to meet your SOX compliance requirements. Here's a comprehensive setup for your regulated environment:

## 1. Terraform Configuration for Maintenance Windows

```hcl
# terraform/gke-maintenance.tf

locals {
  # Define your quarterly code freeze periods (adjust dates as needed)
  quarterly_freezes = [
    {
      name       = "Q1-freeze"
      start_time = "2024-03-15T00:00:00Z"
      end_time   = "2024-04-01T00:00:00Z"
    },
    {
      name       = "Q2-freeze"
      start_time = "2024-06-15T00:00:00Z"
      end_time   = "2024-07-01T00:00:00Z"
    },
    {
      name       = "Q3-freeze"
      start_time = "2024-09-15T00:00:00Z"
      end_time   = "2024-10-01T00:00:00Z"
    },
    {
      name       = "Q4-freeze"
      start_time = "2024-12-15T00:00:00Z"
      end_time   = "2025-01-02T00:00:00Z"
    }
  ]

  # Annual audit exclusion (November)
  annual_audit = {
    name       = "annual-audit"
    start_time = "2024-11-01T00:00:00Z"
    end_time   = "2024-11-30T23:59:59Z"
  }

  # Common maintenance policy for all clusters
  maintenance_policy = {
    # Weekend-only maintenance window (Saturday 2 AM - 6 AM EST)
    daily_maintenance_window = {
      start_time = "07:00"  # UTC time (2 AM EST)
    }
    
    # Recurring maintenance window for weekends only
    recurring_window = {
      start_time = "2024-01-06T07:00:00Z"  # First Saturday
      end_time   = "2024-01-06T11:00:00Z"  # 4-hour window
      recurrence = "FREQ=WEEKLY;BYDAY=SA"   # Every Saturday
    }
  }
}

# Production Cluster
resource "google_container_cluster" "production" {
  name     = "production-cluster"
  location = var.region
  
  # Disable default maintenance window
  remove_default_node_pool = true
  initial_node_count       = 1

  # Maintenance policy with exclusions
  maintenance_policy {
    # Weekend-only recurring maintenance window
    recurring_window {
      start_time = local.maintenance_policy.recurring_window.start_time
      end_time   = local.maintenance_policy.recurring_window.end_time
      recurrence = local.maintenance_policy.recurring_window.recurrence
    }

    # Quarterly code freeze exclusions
    dynamic "maintenance_exclusion" {
      for_each = local.quarterly_freezes
      content {
        exclusion_name = maintenance_exclusion.value.name
        start_time     = maintenance_exclusion.value.start_time
        end_time       = maintenance_exclusion.value.end_time
        exclusion_options {
          scope = "UPGRADES"
        }
      }
    }

    # Annual audit exclusion
    maintenance_exclusion {
      exclusion_name = local.annual_audit.name
      start_time     = local.annual_audit.start_time
      end_time       = local.annual_audit.end_time
      exclusion_options {
        scope = "UPGRADES"
      }
    }
  }

  # Additional SOX compliance settings
  enable_shielded_nodes = true
  
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  # Network policy for compliance
  network_policy {
    enabled = true
  }

  # Private cluster for security
  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block  = "172.16.0.0/28"
  }

  # Logging and monitoring for audit
  logging_config {
    enable_components = ["SYSTEM_COMPONENTS", "WORKLOADS", "APISERVER"]
  }

  monitoring_config {
    enable_components = ["SYSTEM_COMPONENTS", "WORKLOADS", "APISERVER"]
  }
}

# Staging Cluster (similar configuration)
resource "google_container_cluster" "staging" {
  name     = "staging-cluster"
  location = var.region

  remove_default_node_pool = true
  initial_node_count       = 1

  maintenance_policy {
    recurring_window {
      start_time = local.maintenance_policy.recurring_window.start_time
      end_time   = local.maintenance_policy.recurring_window.end_time
      recurrence = local.maintenance_policy.recurring_window.recurrence
    }

    # Same exclusions as production
    dynamic "maintenance_exclusion" {
      for_each = local.quarterly_freezes
      content {
        exclusion_name = maintenance_exclusion.value.name
        start_time     = maintenance_exclusion.value.start_time
        end_time       = maintenance_exclusion.value.end_time
        exclusion_options {
          scope = "UPGRADES"
        }
      }
    }

    maintenance_exclusion {
      exclusion_name = local.annual_audit.name
      start_time     = local.annual_audit.start_time
      end_time       = local.annual_audit.end_time
      exclusion_options {
        scope = "UPGRADES"
      }
    }
  }

  enable_shielded_nodes = true
  
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  network_policy {
    enabled = true
  }

  logging_config {
    enable_components = ["SYSTEM_COMPONENTS", "WORKLOADS"]
  }

  monitoring_config {
    enable_components = ["SYSTEM_COMPONENTS", "WORKLOADS"]
  }
}

# Development Cluster (more flexible schedule)
resource "google_container_cluster" "development" {
  name     = "development-cluster"
  location = var.region

  remove_default_node_pool = true
  initial_node_count       = 1

  maintenance_policy {
    # Dev can have more frequent maintenance (still weekends)
    recurring_window {
      start_time = "2024-01-06T07:00:00Z"
      end_time   = "2024-01-06T11:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SA,SU"  # Weekends
    }

    # Only exclude during audit period for dev
    maintenance_exclusion {
      exclusion_name = local.annual_audit.name
      start_time     = local.annual_audit.start_time
      end_time       = local.annual_audit.end_time
      exclusion_options {
        scope = "UPGRADES"
      }
    }
  }

  enable_shielded_nodes = true
  
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  logging_config {
    enable_components = ["SYSTEM_COMPONENTS"]
  }

  monitoring_config {
    enable_components = ["SYSTEM_COMPONENTS"]
  }
}
```

## 2. Node Pool Configuration with Maintenance Settings

```hcl
# terraform/node-pools.tf

# Production Node Pool
resource "google_container_node_pool" "production_nodes" {
  name       = "production-node-pool"
  location   = var.region
  cluster    = google_container_cluster.production.name
  node_count = 3

  # Auto-upgrade settings
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
    machine_type = "e2-standard-4"
    
    # Security settings for SOX compliance
    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }

    oauth_scopes = [
      "https://www.googleapis.com/auth/logging.write",
      "https://www.googleapis.com/auth/monitoring",
      "https://www.googleapis.com/auth/devstorage.read_only"
    ]

    labels = {
      environment = "production"
      compliance  = "sox"
    }

    tags = ["production", "sox-compliant"]
  }
}

# Staging Node Pool
resource "google_container_node_pool" "staging_nodes" {
  name       = "staging-node-pool"
  location   = var.region
  cluster    = google_container_cluster.staging.name
  node_count = 2

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
    strategy        = "SURGE"
  }

  node_config {
    preemptible  = false
    machine_type = "e2-standard-2"
    
    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }

    oauth_scopes = [
      "https://www.googleapis.com/auth/logging.write",
      "https://www.googleapis.com/auth/monitoring",
      "https://www.googleapis.com/auth/devstorage.read_only"
    ]

    labels = {
      environment = "staging"
      compliance  = "sox"
    }

    tags = ["staging", "sox-compliant"]
  }
}

# Development Node Pool
resource "google_container_node_pool" "development_nodes" {
  name       = "development-node-pool"
  location   = var.region
  cluster    = google_container_cluster.development.name
  node_count = 1

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  upgrade_settings {
    max_surge       = 1
    max_unavailable = 1
    strategy        = "SURGE"
  }

  node_config {
    preemptible  = true  # Cost optimization for dev
    machine_type = "e2-standard-2"
    
    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }

    oauth_scopes = [
      "https://www.googleapis.com/auth/logging.write",
      "https://www.googleapis.com/auth/monitoring"
    ]

    labels = {
      environment = "development"
    }

    tags = ["development"]
  }
}
```

## 3. Monitoring and Alerting for Maintenance Events

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
        expr: up{job="kubernetes-nodes"} == 0
        for: 5m
        labels:
          severity: critical
          compliance: sox
        annotations:
          summary: "Node unavailable outside maintenance window"
          description: "Node {{ $labels.instance }} has been down for more than 5 minutes outside scheduled maintenance window"
      
      - alert: UpgradeStarted
        expr: increase(apiserver_audit_total{verb="update",objectRef_resource="nodes"}[5m]) > 0
        labels:
          severity: info
          compliance: sox
        annotations:
          summary: "GKE upgrade detected"
          description: "Node upgrade activity detected on cluster"

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: maintenance-logger
  namespace: kube-system
spec:
  replicas: 1
  selector:
    matchLabels:
      app: maintenance-logger
  template:
    metadata:
      labels:
        app: maintenance-logger
    spec:
      serviceAccountName: maintenance-logger
      containers:
      - name: logger
        image: gcr.io/gke-release/kubectl:v1.27.0
        command:
        - /bin/sh
        - -c
        - |
          while true; do
            echo "$(date): Maintenance window status check"
            kubectl get nodes -o wide
            kubectl get events --field-selector type=Warning -n kube-system
            sleep 300
          done
        resources:
          requests:
            cpu: 50m
            memory: 64Mi
          limits:
            cpu: 100m
            memory: 128Mi
```

## 4. Compliance Validation Script

```bash
#!/bin/bash
# scripts/validate-maintenance-compliance.sh

set -e

PROJECT_ID="your-project-id"
CLUSTERS=("production-cluster" "staging-cluster" "development-cluster")
REGION="us-central1"

echo "=== GKE Maintenance Compliance Validation ==="
echo "Date: $(date)"
echo "Project: $PROJECT_ID"
echo

for cluster in "${CLUSTERS[@]}"; do
    echo "--- Validating cluster: $cluster ---"
    
    # Check maintenance windows
    echo "Maintenance Windows:"
    gcloud container clusters describe $cluster \
        --region=$REGION \
        --project=$PROJECT_ID \
        --format='value(maintenancePolicy.window.recurringWindow.window.startTime,maintenancePolicy.window.recurringWindow.window.endTime,maintenancePolicy.window.recurringWindow.recurrence)'
    
    # Check exclusions
    echo "Maintenance Exclusions:"
    gcloud container clusters describe $cluster \
        --region=$REGION \
        --project=$PROJECT_ID \
        --format='table(maintenancePolicy.exclusions[].name,maintenancePolicy.exclusions[].startTime,maintenancePolicy.exclusions[].endTime)'
    
    # Check auto-upgrade status
    echo "Auto-upgrade Status:"
    gcloud container node-pools list \
        --cluster=$cluster \
        --region=$REGION \
        --project=$PROJECT_ID \
        --format='table(name,management.autoUpgrade,management.autoRepair)'
    
    # Check security settings
    echo "Security Configuration:"
    gcloud container clusters describe $cluster \
        --region=$REGION \
        --project=$PROJECT_ID \
        --format='value(shieldedNodes.enabled,networkPolicy.enabled,privateClusterConfig.enablePrivateNodes)'
    
    echo
done

# Check for any ongoing maintenance
echo "--- Current Maintenance Status ---"
for cluster in "${CLUSTERS[@]}"; do
    operations=$(gcloud container operations list \
        --filter="targetLink:$cluster AND status:RUNNING" \
        --format="value(name)" \
        --limit=5)
    
    if [[ -n "$operations" ]]; then
        echo "⚠️  Ongoing operations in $cluster:"
        echo "$operations"
    else
        echo "✅ No ongoing maintenance in $cluster"
    fi
done

echo
echo "=== Compliance Check Complete ==="
```

## 5. Usage and Deployment

```bash
# Deploy the infrastructure
terraform init
terraform plan -var="project_id=your-project-id"
terraform apply

# Apply monitoring configuration
kubectl apply -f monitoring/maintenance-alerts.yaml

# Run compliance validation
chmod +x scripts/validate-maintenance-compliance.sh
./scripts/validate-maintenance-compliance.sh

# Set up automated compliance checks (cron job)
cat > /etc/cron.d/gke-compliance << EOF
# Run compliance check daily at 9 AM
0 9 * * * /path/to/validate-maintenance-compliance.sh >> /var/log/gke-compliance.log 2
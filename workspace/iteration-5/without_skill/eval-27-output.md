For financial services with strict change windows, here's the recommended configuration to maximize upgrade control while maintaining security:

## Cluster Configuration

```yaml
# Cluster with maintenance windows and controlled upgrades
apiVersion: container.v1
kind: Cluster
metadata:
  name: finserv-cluster
spec:
  releaseChannel:
    channel: "REGULAR"  # Balanced stability and security updates
  
  maintenancePolicy:
    window:
      recurringWindow:
        window:
          startTime: "2023-01-15T02:00:00Z"  # Your change window
          endTime: "2023-01-15T06:00:00Z"
        recurrence: "FREQ=WEEKLY;BYDAY=SU"   # Weekly Sunday maintenance
    
    exclusions:
      blackout-q4:
        startTime: "2023-12-01T00:00:00Z"
        endTime: "2024-01-02T00:00:00Z"
        scope: "NO_UPGRADES"
      
      blackout-audit:
        startTime: "2023-06-15T00:00:00Z"
        endTime: "2023-06-30T00:00:00Z"
        scope: "NO_MINOR_UPGRADES"
  
  nodeConfig:
    # Enable node auto-upgrade within maintenance windows
    management:
      autoUpgrade: true
      autoRepair: true
```

## Node Pool with Surge Upgrades

```yaml
apiVersion: container.v1
kind: NodePool
spec:
  upgradeSettings:
    maxSurge: 1      # Add 1 node during upgrade
    maxUnavailable: 0 # Keep all original nodes during upgrade
    
  management:
    autoUpgrade: true
    autoRepair: true
    
  # Use preemptible nodes for surge capacity to reduce costs
  nodeConfig:
    preemptible: false  # Keep false for production workloads
```

## Terraform Configuration

```hcl
resource "google_container_cluster" "finserv_cluster" {
  name     = "finserv-production"
  location = "us-central1"

  # Use Regular channel for balanced updates
  release_channel {
    channel = "REGULAR"
  }

  # Disable default node pool - we'll create managed pools
  remove_default_node_pool = true
  initial_node_count       = 1

  # Maintenance window configuration
  maintenance_policy {
    recurring_window {
      start_time = "2023-01-15T02:00:00Z"
      end_time   = "2023-01-15T06:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SU"
    }
    
    # Define blackout periods
    maintenance_exclusion {
      exclusion_name = "year-end-freeze"
      start_time     = "2023-12-15T00:00:00Z"
      end_time       = "2024-01-02T00:00:00Z"
      exclusion_scope = "NO_UPGRADES"
    }
  }

  # Security and compliance features
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }
  
  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block = "10.0.0.0/28"
  }
  
  # Enable network policy for micro-segmentation
  network_policy {
    enabled = true
  }
  
  # Binary Authorization for container security
  enable_binary_authorization = true
  
  # Enable workload identity
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }
}

resource "google_container_node_pool" "primary_nodes" {
  name       = "primary-nodes"
  location   = google_container_cluster.finserv_cluster.location
  cluster    = google_container_cluster.finserv_cluster.name
  
  # Enable autoscaling
  autoscaling {
    min_node_count = 3
    max_node_count = 10
  }

  # Configure surge upgrades for zero-downtime
  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  node_config {
    machine_type = "e2-standard-4"
    disk_size_gb = 100
    disk_type    = "pd-ssd"
    
    # Security configurations
    service_account = google_service_account.gke_nodes.email
    oauth_scopes = [
      "https://www.googleapis.com/auth/logging.write",
      "https://www.googleapis.com/auth/monitoring",
      "https://www.googleapis.com/auth/devstorage.read_only"
    ]
    
    # Enable secure boot and integrity monitoring
    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }
    
    workload_metadata_config {
      mode = "GKE_METADATA"
    }
  }
}
```

## Monitoring and Alerting Setup

```yaml
# Alert for pending upgrades
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: gke-upgrade-alerts
spec:
  groups:
  - name: gke.upgrades
    rules:
    - alert: GKEUpgradeAvailable
      expr: |
        (
          kube_node_info{kubelet_version!~".*latest.*"} and
          on(node) kube_node_info offset 1d
        ) unless on(node) (
          kube_node_info{kubelet_version!~".*latest.*"} and
          on(node) kube_node_info offset 2d
        )
      for: 24h
      labels:
        severity: info
        compliance: security-patch-available
      annotations:
        summary: "GKE upgrade available for {{ $labels.node }}"
        description: "Node {{ $labels.node }} has an upgrade available"

    - alert: GKESecurityUpgradeRequired
      expr: |
        # This would be populated by your security scanning
        gke_security_patch_age_days > 30
      labels:
        severity: warning
        compliance: security-patch-overdue
      annotations:
        summary: "GKE security upgrade overdue"
```

## Upgrade Management Script

```bash
#!/bin/bash
# upgrade-manager.sh - Controlled GKE upgrade script

set -euo pipefail

PROJECT_ID="your-project-id"
CLUSTER_NAME="finserv-production"
LOCATION="us-central1"

# Check if we're in a maintenance window
check_maintenance_window() {
    local current_day=$(date +%u)  # 1-7, Monday-Sunday
    local current_hour=$(date +%H)
    
    # Sunday (7) between 2-6 AM UTC
    if [[ $current_day -eq 7 && $current_hour -ge 2 && $current_hour -lt 6 ]]; then
        return 0
    fi
    
    echo "Not in maintenance window"
    return 1
}

# Check for available upgrades
check_upgrades() {
    echo "Checking for available upgrades..."
    
    local master_version=$(gcloud container clusters describe $CLUSTER_NAME \
        --location=$LOCATION --project=$PROJECT_ID \
        --format="value(currentMasterVersion)")
    
    local available_versions=$(gcloud container get-server-config \
        --location=$LOCATION --project=$PROJECT_ID \
        --format="value(validMasterVersions[0:3])")
    
    echo "Current master version: $master_version"
    echo "Available versions: $available_versions"
}

# Perform controlled upgrade
perform_upgrade() {
    local target_version=$1
    
    echo "Starting upgrade to $target_version..."
    
    # Pre-upgrade validation
    echo "Running pre-upgrade checks..."
    kubectl get nodes -o wide
    kubectl get pods --all-namespaces | grep -v Running || true
    
    # Start the upgrade
    gcloud container clusters upgrade $CLUSTER_NAME \
        --location=$LOCATION \
        --project=$PROJECT_ID \
        --cluster-version=$target_version \
        --quiet
    
    # Monitor upgrade progress
    echo "Monitoring upgrade progress..."
    while true; do
        status=$(gcloud container operations list \
            --location=$LOCATION --project=$PROJECT_ID \
            --filter="TYPE:UPGRADE_MASTER" \
            --format="value(status)" --limit=1)
        
        if [[ "$status" == "DONE" ]]; then
            echo "Master upgrade completed"
            break
        elif [[ "$status" == "RUNNING" ]]; then
            echo "Upgrade in progress..."
            sleep 30
        else
            echo "Upgrade failed with status: $status"
            exit 1
        fi
    done
}

# Main execution
main() {
    if check_maintenance_window; then
        check_upgrades
        
        # Add your approval logic here
        read -p "Proceed with upgrade? (y/N): " confirm
        if [[ $confirm =~ ^[Yy]$ ]]; then
            # Get the latest patch version for current minor
            target_version=$(gcloud container get-server-config \
                --location=$LOCATION --project=$PROJECT_ID \
                --format="value(validMasterVersions[0])")
            
            perform_upgrade "$target_version"
        fi
    else
        echo "Outside maintenance window - only checking status"
        check_upgrades
    fi
}

main "$@"
```

## Key Security Recommendations

1. **Use REGULAR channel** - Gets security patches faster than STABLE but more stable than RAPID

2. **Enable automatic security patches** within your maintenance windows:
```bash
gcloud container clusters update $CLUSTER_NAME \
    --enable-autorepair \
    --enable-autoupgrade \
    --location=$LOCATION
```

3. **Set up security monitoring**:
```bash
# Enable GKE security posture
gcloud container clusters update $CLUSTER_NAME \
    --enable-network-policy \
    --enable-ip-alias \
    --enable-binary-authorization \
    --location=$LOCATION
```

4. **Create emergency upgrade procedures** for critical security patches:
```bash
# Emergency upgrade outside maintenance window
gcloud container clusters upgrade $CLUSTER_NAME \
    --location=$LOCATION \
    --cluster-version=LATEST \
    --quiet
```

This configuration gives you maximum control over upgrade timing while ensuring you don't fall behind on critical security updates. The maintenance windows respect your change management process, and the monitoring helps you stay aware of pending updates.
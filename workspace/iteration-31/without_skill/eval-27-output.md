For financial services with strict change windows, here's the recommended configuration to maximize upgrade control while maintaining security:

## Cluster Configuration

```yaml
# terraform/gke-cluster.tf
resource "google_container_cluster" "primary" {
  name     = "financial-cluster"
  location = var.region

  # Use STATIC version channel for maximum control
  release_channel {
    channel = "REGULAR"  # Start with REGULAR, can move to RAPID for faster patches
  }

  # Disable automatic upgrades
  cluster_autoscaling {
    auto_provisioning_defaults {
      upgrade_settings {
        max_surge       = 1
        max_unavailable = 0
        strategy        = "SURGE"
      }
    }
  }

  # Control plane maintenance window
  maintenance_policy {
    recurring_window {
      start_time = "2023-01-01T02:00:00Z"
      end_time   = "2023-01-01T06:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SU"  # Sunday 2-6 AM
    }
  }

  # Enable automatic upgrades but with exclusions
  master_auth {
    cluster_ca_certificate = ""
  }

  # Network policy for security
  network_policy {
    enabled = true
  }

  # Private cluster for security
  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block  = "10.0.0.0/28"
  }
}
```

## Node Pool with Controlled Upgrades

```yaml
resource "google_container_node_pool" "primary_nodes" {
  name       = "primary-pool"
  location   = var.region
  cluster    = google_container_cluster.primary.name
  
  # Fixed node count for predictability
  initial_node_count = 3

  # Upgrade settings
  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
    strategy        = "BLUE_GREEN"
  }

  # Management settings
  management {
    auto_repair  = true   # Keep for security patches
    auto_upgrade = false  # Manual control over upgrades
  }

  node_config {
    machine_type = "e2-standard-4"
    
    # Security configurations
    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }

    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]
  }
}
```

## Upgrade Management Script

```bash
#!/bin/bash
# scripts/controlled-upgrade.sh

set -euo pipefail

CLUSTER_NAME="financial-cluster"
REGION="us-central1"
PROJECT_ID="your-project-id"

# Function to check for available upgrades
check_available_upgrades() {
    echo "Checking available upgrades..."
    gcloud container get-server-config \
        --region=$REGION \
        --project=$PROJECT_ID \
        --format="table(channels.REGULAR.validVersions:label='Available Versions')"
}

# Function to plan upgrade
plan_upgrade() {
    local target_version=$1
    
    echo "Planning upgrade to $target_version..."
    
    # Check current version
    current_version=$(gcloud container clusters describe $CLUSTER_NAME \
        --region=$REGION \
        --project=$PROJECT_ID \
        --format="value(currentMasterVersion)")
    
    echo "Current version: $current_version"
    echo "Target version: $target_version"
    
    # Validate upgrade path
    if [[ "$target_version" < "$current_version" ]]; then
        echo "ERROR: Cannot downgrade cluster"
        exit 1
    fi
}

# Function to upgrade control plane during maintenance window
upgrade_control_plane() {
    local target_version=$1
    
    echo "Upgrading control plane to $target_version..."
    gcloud container clusters upgrade $CLUSTER_NAME \
        --region=$REGION \
        --project=$PROJECT_ID \
        --master \
        --cluster-version=$target_version \
        --quiet
}

# Function to upgrade nodes with controlled rollout
upgrade_nodes() {
    local target_version=$1
    local node_pool=$2
    
    echo "Upgrading nodes in pool $node_pool to $target_version..."
    
    # Drain nodes gracefully
    kubectl drain --ignore-daemonsets --delete-emptydir-data --force \
        $(kubectl get nodes -o name | head -1)
    
    gcloud container clusters upgrade $CLUSTER_NAME \
        --region=$REGION \
        --project=$PROJECT_ID \
        --node-pool=$node_pool \
        --cluster-version=$target_version \
        --quiet
}

# Main upgrade workflow
main() {
    local command=${1:-"check"}
    local target_version=${2:-""}
    
    case $command in
        "check")
            check_available_upgrades
            ;;
        "plan")
            plan_upgrade $target_version
            ;;
        "upgrade-master")
            upgrade_control_plane $target_version
            ;;
        "upgrade-nodes")
            upgrade_nodes $target_version "primary-pool"
            ;;
        *)
            echo "Usage: $0 {check|plan|upgrade-master|upgrade-nodes} [version]"
            exit 1
            ;;
    esac
}

main "$@"
```

## Security Monitoring and Alerting

```yaml
# monitoring/security-alerts.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: gke-security-alerts
spec:
  groups:
  - name: gke.security
    rules:
    - alert: GKEVersionBehind
      expr: |
        (time() - kube_version_info{job="kube-state-metrics"}) / 86400 > 90
      for: 1h
      labels:
        severity: warning
      annotations:
        summary: "GKE cluster version is more than 90 days old"
        description: "Cluster {{ $labels.cluster }} is running version {{ $labels.version }} which is {{ $value }} days old"

    - alert: SecurityPatchAvailable
      expr: |
        gke_security_patch_available == 1
      for: 5m
      labels:
        severity: critical
      annotations:
        summary: "Security patch available for GKE cluster"
        description: "Security patch is available for cluster {{ $labels.cluster }}"
```

## Change Management Workflow

```yaml
# .github/workflows/gke-upgrade.yml
name: GKE Upgrade Workflow

on:
  workflow_dispatch:
    inputs:
      target_version:
        description: 'Target Kubernetes version'
        required: true
      environment:
        description: 'Environment to upgrade'
        required: true
        type: choice
        options:
        - staging
        - production

jobs:
  plan-upgrade:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    
    - name: Setup gcloud
      uses: google-github-actions/setup-gcloud@v0
      with:
        service_account_key: ${{ secrets.GCP_SA_KEY }}
        project_id: ${{ secrets.GCP_PROJECT_ID }}
    
    - name: Plan Upgrade
      run: |
        ./scripts/controlled-upgrade.sh plan ${{ github.event.inputs.target_version }}
    
    - name: Security Scan
      run: |
        # Run security validation
        gcloud container images scan $IMAGE_URL

  upgrade-staging:
    needs: plan-upgrade
    if: github.event.inputs.environment == 'staging'
    runs-on: ubuntu-latest
    environment: staging
    steps:
    - name: Upgrade Control Plane
      run: |
        ./scripts/controlled-upgrade.sh upgrade-master ${{ github.event.inputs.target_version }}
    
    - name: Upgrade Nodes
      run: |
        ./scripts/controlled-upgrade.sh upgrade-nodes ${{ github.event.inputs.target_version }}

  upgrade-production:
    needs: upgrade-staging
    if: github.event.inputs.environment == 'production'
    runs-on: ubuntu-latest
    environment: production
    steps:
    - name: Production Upgrade
      run: |
        # Production upgrade with additional safeguards
        ./scripts/production-upgrade.sh ${{ github.event.inputs.target_version }}
```

## Security Best Practices

```yaml
# security/policies.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: upgrade-policies
data:
  policy.yaml: |
    # Upgrade policies for financial services
    security_requirements:
      - name: "Security patches within 72 hours"
        type: "security_patch"
        max_delay: "72h"
        severity: "critical"
      
      - name: "Regular updates within 30 days"
        type: "regular_update"
        max_delay: "720h"  # 30 days
        severity: "medium"
      
      - name: "Change window compliance"
        allowed_windows:
          - day: "sunday"
            start: "02:00"
            end: "06:00"
          - day: "saturday"
            start: "20:00" 
            end: "23:59"
    
    validation_steps:
      - pre_upgrade_backup
      - security_scan
      - compliance_check
      - rollback_plan
```

## Recommended Strategy

1. **Use REGULAR release channel** - Gets security patches quickly but allows manual timing
2. **Disable auto-upgrades** - Set `auto_upgrade = false` for full control
3. **Enable auto-repair** - Keep for security patches only
4. **Configure maintenance windows** - Align with your change windows
5. **Implement staged rollouts** - Staging → Production
6. **Monitor security alerts** - Set up alerts for available patches
7. **Document upgrade procedures** - Maintain runbooks for emergency patches

This configuration gives you maximum control while ensuring you can respond quickly to security vulnerabilities within your compliance requirements.
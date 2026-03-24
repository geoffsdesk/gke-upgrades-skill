For financial services with strict change windows, here's the recommended GKE upgrade configuration that balances security and control:

## Control Plane Configuration

```yaml
# terraform/gke-cluster.tf
resource "google_container_cluster" "primary" {
  name     = "financial-cluster"
  location = var.region

  # Disable automatic upgrades for maximum control
  release_channel {
    channel = "REGULAR"  # Stable updates, not cutting edge
  }

  # Manual control plane upgrade settings
  cluster_autoscaling {
    enabled = false
  }

  # Maintenance window during your change window
  maintenance_policy {
    daily_maintenance_window {
      start_time = "02:00"  # Adjust to your maintenance window
    }
    
    maintenance_exclusion {
      exclusion_name = "holiday-freeze"
      start_time     = "2024-12-15T00:00:00Z"
      end_time       = "2024-01-02T23:59:59Z"
      
      exclusion_options {
        scope = "NO_UPGRADES"
      }
    }
  }

  # Security-focused node configuration
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block = "172.16.0.0/28"
  }

  network_policy {
    enabled = true
  }

  # Enable security features
  enable_shielded_nodes = true
  enable_network_policy = true
}
```

## Node Pool Configuration

```yaml
resource "google_container_node_pool" "primary_nodes" {
  name       = "primary-pool"
  cluster    = google_container_cluster.primary.name
  location   = var.region

  # Manual upgrade control
  management {
    auto_repair  = true   # Keep for security patches
    auto_upgrade = false  # Manual control over upgrades
  }

  # Version pinning - update during change windows
  version = "1.28.3-gke.1286000"  # Pin to specific patch version

  node_config {
    machine_type = "e2-standard-4"
    
    # Security hardening
    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }

    # Workload Identity
    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]

    tags = ["financial-gke-node"]
  }

  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0  # Zero downtime upgrades
    
    blue_green_settings {
      standard_rollout_policy {
        batch_percentage    = 0.2    # 20% at a time
        batch_node_count    = 2      # Or specific count
        batch_soak_duration = "300s" # 5 min validation
      }
    }
  }
}
```

## Controlled Upgrade Process

Create a structured upgrade workflow:

```bash
#!/bin/bash
# scripts/controlled-upgrade.sh

set -euo pipefail

CLUSTER_NAME="financial-cluster"
ZONE="us-central1"
TARGET_VERSION=""

# Pre-upgrade validation
validate_cluster_health() {
    echo "Validating cluster health..."
    
    # Check node health
    kubectl get nodes --no-headers | awk '{print $2}' | grep -v Ready && {
        echo "ERROR: Unhealthy nodes detected"
        exit 1
    }
    
    # Check critical workloads
    kubectl get pods -n production --field-selector=status.phase!=Running && {
        echo "ERROR: Non-running pods in production"
        exit 1
    }
    
    # Check PDB compliance
    kubectl get pdb -A -o json | jq '.items[] | select(.status.currentHealthy < .status.expectedPods)'
}

# Upgrade control plane
upgrade_control_plane() {
    echo "Upgrading control plane to ${TARGET_VERSION}..."
    
    gcloud container clusters upgrade ${CLUSTER_NAME} \
        --zone=${ZONE} \
        --cluster-version=${TARGET_VERSION} \
        --quiet
        
    # Wait for upgrade completion
    while [[ $(gcloud container clusters describe ${CLUSTER_NAME} --zone=${ZONE} --format="value(status)") == "RUNNING" ]]; do
        sleep 30
        echo "Control plane upgrade in progress..."
    done
}

# Upgrade node pools with validation
upgrade_node_pools() {
    local pools=$(gcloud container node-pools list --cluster=${CLUSTER_NAME} --zone=${ZONE} --format="value(name)")
    
    for pool in $pools; do
        echo "Upgrading node pool: $pool"
        
        # Pre-pool upgrade validation
        validate_cluster_health
        
        gcloud container clusters upgrade ${CLUSTER_NAME} \
            --zone=${ZONE} \
            --node-pool=${pool} \
            --cluster-version=${TARGET_VERSION} \
            --quiet
            
        # Post-pool validation
        sleep 60
        validate_cluster_health
        
        echo "Node pool $pool upgrade completed successfully"
    done
}

# Main execution
main() {
    if [[ -z "$TARGET_VERSION" ]]; then
        echo "Please set TARGET_VERSION"
        exit 1
    fi
    
    validate_cluster_health
    upgrade_control_plane
    upgrade_node_pools
    
    echo "Cluster upgrade completed successfully"
}

main "$@"
```

## Security Monitoring & Alerting

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
    - alert: GKEVersionBehindSecurity
      expr: |
        (time() - gke_cluster_version_created_time) > (30 * 24 * 3600)
      for: 24h
      labels:
        severity: warning
        team: platform
      annotations:
        summary: "GKE cluster version is more than 30 days old"
        description: "Consider upgrading during next maintenance window"
        
    - alert: GKENodeSecurityPatch
      expr: |
        (time() - gke_node_version_created_time) > (14 * 24 * 3600)
      for: 12h
      labels:
        severity: critical
        team: platform
      annotations:
        summary: "GKE nodes missing security patches"
```

## Upgrade Planning Automation

```python
# scripts/upgrade_planner.py
import requests
import json
from datetime import datetime, timedelta

class GKEUpgradePlanner:
    def __init__(self, project_id):
        self.project_id = project_id
        
    def get_available_versions(self, location):
        """Get available GKE versions and security info"""
        # Use GKE API to get version info
        # Filter for versions with security patches
        pass
        
    def check_security_urgency(self, current_version):
        """Check if current version has security vulnerabilities"""
        # Check against CVE databases
        # Return urgency level and recommended upgrade timeline
        pass
        
    def plan_upgrade_window(self, maintenance_windows, urgency="normal"):
        """Plan upgrade timing based on urgency and available windows"""
        if urgency == "critical":
            # Find nearest maintenance window
            return self.find_emergency_window()
        else:
            # Plan for regular maintenance window
            return self.find_regular_window(maintenance_windows)
            
    def generate_upgrade_plan(self, cluster_name):
        """Generate comprehensive upgrade plan"""
        plan = {
            "cluster": cluster_name,
            "current_version": self.get_current_version(cluster_name),
            "recommended_version": self.get_recommended_version(),
            "security_patches": self.get_security_info(),
            "estimated_duration": self.estimate_upgrade_time(),
            "rollback_plan": self.generate_rollback_plan(),
            "validation_steps": self.get_validation_checklist()
        }
        return plan
```

## Key Recommendations

1. **Use REGULAR release channel** - More predictable than RAPID, more secure than STABLE
2. **Disable auto-upgrade** but enable auto-repair for security patches
3. **Pin node pool versions** and upgrade during change windows
4. **Use blue-green node pool upgrades** for zero downtime
5. **Set maintenance exclusions** for holiday freezes
6. **Monitor security patch age** with alerting
7. **Automate pre/post upgrade validation**
8. **Maintain rollback procedures**

This configuration gives you maximum control while ensuring you can respond quickly to critical security updates when needed.
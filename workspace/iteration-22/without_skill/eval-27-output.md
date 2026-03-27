For financial services with strict change windows, here's the recommended configuration that balances control with security:

## Recommended Configuration

### 1. Use Static GKE Versions with Manual Upgrades

```yaml
# terraform/gke-cluster.tf
resource "google_container_cluster" "primary" {
  name     = "production-cluster"
  location = var.region
  
  # Disable automatic upgrades for maximum control
  release_channel {
    channel = "NONE"  # Use static versioning
  }
  
  # Set specific master version
  min_master_version = "1.28.3-gke.1203001"
  
  # Disable automatic node upgrades
  node_config {
    # Node configuration
  }
  
  # Enable maintenance windows for when you DO upgrade
  maintenance_policy {
    daily_maintenance_window {
      start_time = "03:00"  # Your maintenance window
    }
  }
  
  # Enable workload identity for security
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }
  
  # Security configurations
  network_policy {
    enabled = true
  }
  
  private_cluster_config {
    enable_private_nodes   = true
    master_ipv4_cidr_block = "10.0.0.0/28"
  }
  
  # Enable security features
  enable_shielded_nodes = true
  
  database_encryption {
    state    = "ENCRYPTED"
    key_name = google_kms_crypto_key.etcd_key.id
  }
}

resource "google_container_node_pool" "primary" {
  cluster  = google_container_cluster.primary.name
  location = google_container_cluster.primary.location
  
  # Control node upgrades
  management {
    auto_repair  = true   # Keep for security patches
    auto_upgrade = false  # Manual control
  }
  
  # Set specific node version
  version = "1.28.3-gke.1203001"
  
  upgrade_settings {
    # Control upgrade rollout when you do upgrade
    max_surge       = 1
    max_unavailable = 0
    strategy        = "SURGE"
  }
  
  node_config {
    machine_type = "e2-standard-4"
    
    # Security configurations
    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }
    
    # Use least-privilege service account
    service_account = google_service_account.gke_nodes.email
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]
  }
}
```

### 2. Implement Upgrade Monitoring and Alerting

```yaml
# monitoring/upgrade-alerts.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: gke-version-alerts
spec:
  groups:
  - name: gke-upgrades
    rules:
    - alert: GKEVersionOutdated
      expr: |
        (time() - gke_cluster_created_time) / 86400 > 90
      for: 24h
      labels:
        severity: warning
        team: platform
      annotations:
        summary: "GKE cluster version is over 90 days old"
        description: "Cluster {{ $labels.cluster }} should be evaluated for upgrade"
        
    - alert: SecurityPatchAvailable
      expr: |
        gke_security_patch_available == 1
      for: 1h
      labels:
        severity: critical
        team: security
      annotations:
        summary: "Security patch available for GKE"
        description: "Critical security patch available - evaluate for emergency upgrade"
```

### 3. Create Upgrade Automation Scripts

```bash
#!/bin/bash
# scripts/controlled-upgrade.sh

set -euo pipefail

CLUSTER_NAME="${1:-}"
NEW_VERSION="${2:-}"
ENVIRONMENT="${3:-}"

if [[ -z "$CLUSTER_NAME" || -z "$NEW_VERSION" || -z "$ENVIRONMENT" ]]; then
    echo "Usage: $0 <cluster-name> <new-version> <environment>"
    exit 1
fi

# Pre-upgrade validation
validate_upgrade() {
    echo "🔍 Validating upgrade prerequisites..."
    
    # Check if version is available
    gcloud container get-server-config \
        --zone=us-central1-a \
        --format="value(validMasterVersions)" | \
        grep -q "$NEW_VERSION" || {
        echo "❌ Version $NEW_VERSION not available"
        exit 1
    }
    
    # Check cluster health
    kubectl get nodes --no-headers | \
        awk '{print $2}' | \
        grep -v "Ready" && {
        echo "❌ Cluster has unhealthy nodes"
        exit 1
    }
    
    echo "✅ Pre-upgrade validation passed"
}

# Backup critical resources
backup_cluster_state() {
    echo "💾 Backing up cluster state..."
    
    mkdir -p "backups/$(date +%Y%m%d-%H%M%S)"
    BACKUP_DIR="backups/$(date +%Y%m%d-%H%M%S)"
    
    # Backup critical namespaces
    for ns in kube-system default production staging; do
        kubectl get all -n $ns -o yaml > "$BACKUP_DIR/${ns}-backup.yaml"
    done
    
    # Backup RBAC
    kubectl get clusterroles,clusterrolebindings -o yaml > "$BACKUP_DIR/rbac-backup.yaml"
    
    echo "✅ Backup completed in $BACKUP_DIR"
}

# Staged upgrade process
upgrade_master() {
    echo "🚀 Upgrading master to $NEW_VERSION..."
    
    gcloud container clusters upgrade "$CLUSTER_NAME" \
        --master \
        --cluster-version="$NEW_VERSION" \
        --zone=us-central1-a \
        --quiet
        
    echo "✅ Master upgrade completed"
}

upgrade_nodes_by_pool() {
    echo "🔄 Upgrading node pools..."
    
    # Get all node pools
    NODE_POOLS=$(gcloud container node-pools list \
        --cluster="$CLUSTER_NAME" \
        --zone=us-central1-a \
        --format="value(name)")
    
    for pool in $NODE_POOLS; do
        echo "Upgrading node pool: $pool"
        
        gcloud container clusters upgrade "$CLUSTER_NAME" \
            --node-pool="$pool" \
            --cluster-version="$NEW_VERSION" \
            --zone=us-central1-a \
            --quiet
            
        # Wait and verify
        sleep 60
        check_cluster_health
    done
    
    echo "✅ All node pools upgraded"
}

check_cluster_health() {
    echo "🏥 Checking cluster health..."
    
    # Wait for nodes to be ready
    kubectl wait --for=condition=Ready nodes --all --timeout=300s
    
    # Check system pods
    kubectl get pods -n kube-system | grep -v Running | grep -v Completed && {
        echo "⚠️  Some system pods not running"
        kubectl get pods -n kube-system
    } || echo "✅ System pods healthy"
    
    # Run smoke tests
    run_smoke_tests
}

run_smoke_tests() {
    echo "🧪 Running post-upgrade smoke tests..."
    
    # Deploy test workload
    kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: upgrade-test
  namespace: default
spec:
  replicas: 2
  selector:
    matchLabels:
      app: upgrade-test
  template:
    metadata:
      labels:
        app: upgrade-test
    spec:
      containers:
      - name: nginx
        image: nginx:alpine
        ports:
        - containerPort: 80
EOF

    # Wait for deployment
    kubectl rollout status deployment/upgrade-test --timeout=300s
    
    # Test service connectivity
    kubectl expose deployment upgrade-test --port=80 --type=ClusterIP
    
    # Cleanup test resources
    kubectl delete deployment upgrade-test
    kubectl delete service upgrade-test
    
    echo "✅ Smoke tests passed"
}

# Main execution
main() {
    echo "🎯 Starting controlled upgrade for $CLUSTER_NAME to $NEW_VERSION"
    
    validate_upgrade
    backup_cluster_state
    
    if [[ "$ENVIRONMENT" == "production" ]]; then
        read -p "⚠️  Production upgrade - are you sure? (yes/no): " confirm
        [[ "$confirm" == "yes" ]] || exit 1
    fi
    
    upgrade_master
    upgrade_nodes_by_pool
    check_cluster_health
    
    echo "🎉 Upgrade completed successfully!"
}

main "$@"
```

### 4. Version Management Strategy

```yaml
# Create a version management file
# versions.yaml
clusters:
  production:
    current_version: "1.28.3-gke.1203001"
    target_version: "1.28.5-gke.1210002"
    last_upgraded: "2024-01-15"
    next_window: "2024-03-15"
    
  staging:
    current_version: "1.28.5-gke.1210002"
    target_version: "1.29.1-gke.1015000"
    last_upgraded: "2024-02-01"
    next_window: "2024-02-15"

upgrade_policy:
  max_age_days: 120  # Maximum days behind
  security_patch_sla: 7  # Days to apply security patches
  testing_environment_lead: 14  # Days to test in staging first
```

### 5. Change Management Integration

```python
# scripts/change_management.py
import json
import requests
from datetime import datetime, timedelta

class ChangeManagementIntegration:
    def __init__(self, servicenow_endpoint, auth_token):
        self.endpoint = servicenow_endpoint
        self.auth_token = auth_token
    
    def create_change_request(self, cluster_name, current_version, target_version):
        change_request = {
            "short_description": f"GKE Cluster Upgrade: {cluster_name}",
            "description": f"""
                Upgrading GKE cluster from {current_version} to {target_version}
                
                Risk Assessment: Medium
                Rollback Plan: Automated node pool rollback available
                Testing: Completed in staging environment
                
                Business Justification: Security and stability improvements
            """,
            "category": "Infrastructure",
            "priority": "3 - Moderate",
            "risk": "Medium",
            "implementation_plan": self.get_implementation_plan(),
            "rollback_plan": self.get_rollback_plan(),
            "requested_by": "platform-team@company.com"
        }
        
        response = requests.post(
            f"{self.endpoint}/api/now/table/change_request",
            json=change_request,
            headers={
                "Authorization": f"Bearer {self.auth_token}",
                "Content-Type": "application/json"
            }
        )
        
        return response.json()
    
    def get_implementation_plan(self):
        return """
        1. Pre-upgrade validation and backup
        2. Upgrade control plane during maintenance window
        3. Staged node pool upgrades with health checks
        4. Post-upgrade validation and smoke tests
        5. Monitor for 24 hours post-upgrade
        """
    
    def get_rollback_plan(self):
        return """
        1. Node pools can be rolled back individually
        2. Application rollback via GitOps
        3. Cluster recreation from backup if needed
        4. Estimated rollback time: 2-4 hours
        """
```

## Key Benefits of This Approach:

1. **Maximum Control**: Manual upgrades only during your windows
2. **Security Compliance**: Monitoring for security patches with SLA tracking
3. **Risk Mitigation**: Staged upgrades with health checks and rollback plans
4. **Audit Trail**: Full change management integration
5. **Flexibility**: Emergency upgrade capability for critical security issues

## Recommendations:

1. **Test in staging first** - Always upgrade staging 2+ weeks before production
2. **Monitor upgrade notifications** - Set up alerts for new versions and security patches
3. **Maintain upgrade cadence** - Don't fall more than 2-3 minor versions behind
4. **Document exceptions** - Have a process for emergency security upgrades
5. **Regular reviews** - Monthly review of cluster versions and upgrade roadmap

This configuration gives you complete control while maintaining security posture appropriate for financial services.
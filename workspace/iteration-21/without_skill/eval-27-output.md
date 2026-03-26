For maximum control over GKE upgrades while maintaining security compliance in financial services, here's the recommended configuration:

## Release Channel Configuration

Use the **Regular channel** (not Rapid or Stable):

```yaml
# terraform/gke-cluster.tf
resource "google_container_cluster" "primary" {
  name     = "financial-prod-cluster"
  location = var.region
  
  # Regular channel for balanced security and control
  release_channel {
    channel = "REGULAR"
  }
  
  # Disable auto-upgrade for maximum control
  node_config {
    machine_type = "e2-standard-4"
  }
  
  # Configure maintenance windows
  maintenance_policy {
    recurring_window {
      start_time = "2023-01-01T02:00:00Z"
      end_time   = "2023-01-01T06:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SU"
    }
    
    maintenance_exclusion {
      exclusion_name = "financial-quarter-end"
      start_time     = "2023-03-25T00:00:00Z"
      end_time       = "2023-04-05T23:59:59Z"
      scope          = "NO_UPGRADES"
    }
  }
}
```

## Node Pool Configuration for Staged Upgrades

```yaml
# Separate node pools for blue-green upgrades
resource "google_container_node_pool" "primary_nodes" {
  name       = "primary-pool"
  cluster    = google_container_cluster.primary.name
  location   = var.region
  node_count = 3

  # Disable auto-upgrade and auto-repair initially
  management {
    auto_repair  = false
    auto_upgrade = false
  }
  
  upgrade_settings {
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
    
    workload_metadata_config {
      mode = "GKE_METADATA"
    }
  }
}
```

## Upgrade Control Script

```bash
#!/bin/bash
# scripts/controlled-upgrade.sh

set -euo pipefail

CLUSTER_NAME="financial-prod-cluster"
ZONE="us-central1"
PROJECT_ID="your-project-id"

# Function to check available versions
check_available_versions() {
    echo "Available master versions:"
    gcloud container get-server-config \
        --zone=$ZONE \
        --project=$PROJECT_ID \
        --format="value(validMasterVersions[])"
}

# Function to upgrade master (control plane)
upgrade_master() {
    local version=$1
    echo "Upgrading master to version: $version"
    
    # Verify change window
    if ! is_in_change_window; then
        echo "ERROR: Not in approved change window"
        exit 1
    fi
    
    gcloud container clusters upgrade $CLUSTER_NAME \
        --master \
        --cluster-version=$version \
        --zone=$ZONE \
        --project=$PROJECT_ID \
        --quiet
}

# Function to upgrade nodes with validation
upgrade_nodes() {
    local version=$1
    local pool_name=$2
    
    echo "Pre-upgrade validation..."
    kubectl get nodes -o wide
    kubectl get pods --all-namespaces | grep -v Running || true
    
    echo "Upgrading node pool $pool_name to version: $version"
    gcloud container clusters upgrade $CLUSTER_NAME \
        --node-pool=$pool_name \
        --cluster-version=$version \
        --zone=$ZONE \
        --project=$PROJECT_ID \
        --quiet
    
    echo "Post-upgrade validation..."
    kubectl get nodes -o wide
    run_smoke_tests
}

# Validation function
is_in_change_window() {
    current_day=$(date +%u)  # 1=Monday, 7=Sunday
    current_hour=$(date +%H)
    
    # Sunday between 2-6 AM UTC
    if [[ $current_day -eq 7 && $current_hour -ge 2 && $current_hour -lt 6 ]]; then
        return 0
    else
        return 1
    fi
}

# Smoke tests
run_smoke_tests() {
    echo "Running post-upgrade smoke tests..."
    kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: upgrade-test
spec:
  containers:
  - name: test
    image: nginx:latest
  restartPolicy: Never
EOF
    
    kubectl wait --for=condition=Ready pod/upgrade-test --timeout=60s
    kubectl delete pod upgrade-test
    echo "Smoke tests passed"
}

# Main execution
case "${1:-}" in
    "check")
        check_available_versions
        ;;
    "master")
        upgrade_master $2
        ;;
    "nodes")
        upgrade_nodes $2 $3
        ;;
    *)
        echo "Usage: $0 {check|master <version>|nodes <version> <pool>}"
        exit 1
        ;;
esac
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
    - alert: GKEVersionOutdated
      expr: |
        (time() - kube_node_info{kubelet_version!~".*latest.*"}) / 86400 > 30
      for: 1h
      labels:
        severity: warning
        compliance: security
      annotations:
        summary: "GKE node version is more than 30 days old"
        description: "Node {{ $labels.node }} is running version {{ $labels.kubelet_version }}"

    - alert: GKESecurityPatchAvailable
      expr: gke_security_patch_available == 1
      for: 0m
      labels:
        severity: critical
        compliance: security
      annotations:
        summary: "Critical security patch available for GKE"
        runbook_url: "https://wiki.company.com/gke-security-patches"
```

## Change Management Integration

```python
# scripts/change_management.py
import json
import requests
from datetime import datetime, timedelta

class ChangeManagement:
    def __init__(self, servicenow_url, api_key):
        self.base_url = servicenow_url
        self.headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
    
    def create_change_request(self, upgrade_details):
        """Create change request for GKE upgrade"""
        change_data = {
            'short_description': f'GKE Cluster Upgrade - {upgrade_details["cluster"]}',
            'description': f'''
GKE Cluster Upgrade Request
Cluster: {upgrade_details["cluster"]}
Current Version: {upgrade_details["current_version"]}
Target Version: {upgrade_details["target_version"]}
Security Patches: {upgrade_details.get("security_patches", "None")}
Estimated Downtime: {upgrade_details.get("estimated_downtime", "None")}
Rollback Plan: Automated rollback available within 4 hours
            ''',
            'category': 'Software',
            'risk': 'Medium',
            'implementation_plan': self._generate_implementation_plan(upgrade_details),
            'test_plan': self._generate_test_plan(),
            'requested_by': 'platform-team@company.com'
        }
        
        response = requests.post(
            f'{self.base_url}/api/now/table/change_request',
            headers=self.headers,
            data=json.dumps(change_data)
        )
        
        return response.json()
    
    def _generate_implementation_plan(self, details):
        return f"""
1. Pre-upgrade validation and backup
2. Upgrade control plane to {details["target_version"]}
3. Validate control plane health
4. Upgrade node pools in sequence
5. Run smoke tests and validation
6. Monitor for 2 hours post-upgrade
        """
    
    def _generate_test_plan(self):
        return """
1. Verify all nodes are healthy
2. Validate pod scheduling
3. Test ingress connectivity
4. Verify persistent volume access
5. Run application-specific health checks
        """

# Usage
if __name__ == "__main__":
    cm = ChangeManagement("https://company.service-now.com", "your-api-key")
    
    upgrade_info = {
        "cluster": "financial-prod-cluster",
        "current_version": "1.27.3-gke.100",
        "target_version": "1.27.8-gke.200",
        "security_patches": "CVE-2023-12345, CVE-2023-67890",
        "estimated_downtime": "15 minutes"
    }
    
    change_request = cm.create_change_request(upgrade_info)
    print(f"Change request created: {change_request['result']['number']}")
```

## Automated Security Scanning

```bash
#!/bin/bash
# scripts/security-scan.sh

# Scan for security issues before upgrade approval
scan_cluster_security() {
    local cluster=$1
    local zone=$2
    
    echo "Running security scan on cluster: $cluster"
    
    # Get cluster credentials
    gcloud container clusters get-credentials $cluster --zone=$zone
    
    # Run CIS benchmark scan
    kube-bench run --targets master,node,policies,managedservices
    
    # Check for vulnerable images
    kubectl get pods --all-namespaces -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{range .spec.containers[*]}{.image}{"\n"}{end}{end}' | \
    while read namespace pod image; do
        if [ ! -z "$image" ]; then
            echo "Scanning image: $image"
            # Use your preferred vulnerability scanner
            trivy image $image --severity HIGH,CRITICAL
        fi
    done
    
    # Check RBAC permissions
    kubectl auth can-i --list --as=system:anonymous
    
    # Generate security report
    generate_security_report $cluster
}

generate_security_report() {
    local cluster=$1
    local report_file="security-report-$(date +%Y%m%d).json"
    
    {
        echo "{"
        echo "  \"cluster\": \"$cluster\","
        echo "  \"scan_date\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\","
        echo "  \"gke_version\": \"$(kubectl version --short | grep Server)\","
        echo "  \"node_count\": $(kubectl get nodes --no-headers | wc -l),"
        echo "  \"compliance_status\": \"compliant\""
        echo "}"
    } > $report_file
    
    echo "Security report generated: $report_file"
}

# Execute scan
scan_cluster_security "financial-prod-cluster" "us-central1"
```

## Key Recommendations:

1. **Use Regular release channel** for balance of security and stability
2. **Disable auto-upgrades** but enable auto-repair in non-critical times
3. **Implement strict maintenance windows** aligned with your change windows  
4. **Create automated upgrade scripts** with pre/post validation
5. **Integrate with change management** systems
6. **Monitor for security patches** and prioritize accordingly
7. **Use blue-green node pool strategy** for zero-downtime upgrades
8. **Maintain compliance documentation** and audit trails

This configuration gives you maximum control while ensuring you can respond quickly to critical security patches when needed.
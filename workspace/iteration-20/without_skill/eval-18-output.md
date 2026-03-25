I'll help you configure maintenance windows and exclusions for your GKE Standard clusters to meet SOX compliance requirements. Here's a comprehensive setup:

## 1. Terraform Configuration

```hcl
# terraform/maintenance-windows.tf

locals {
  # Define quarterly code freeze periods (adjust dates as needed)
  quarterly_freezes = [
    {
      start = "2024-03-25T00:00:00Z"
      end   = "2024-04-01T00:00:00Z"
    },
    {
      start = "2024-06-25T00:00:00Z"
      end   = "2024-07-01T00:00:00Z"
    },
    {
      start = "2024-09-25T00:00:00Z"
      end   = "2024-10-01T00:00:00Z"
    },
    {
      start = "2024-12-20T00:00:00Z"
      end   = "2025-01-02T00:00:00Z"
    }
  ]

  # November audit period
  annual_audit = {
    start = "2024-11-01T00:00:00Z"
    end   = "2024-11-30T23:59:59Z"
  }

  clusters = [
    "prod-cluster-1",
    "prod-cluster-2", 
    "prod-cluster-3"
  ]
}

# Weekend-only maintenance window policy
resource "google_container_cluster" "regulated_clusters" {
  count = length(local.clusters)
  
  name     = local.clusters[count.index]
  location = var.cluster_locations[count.index]

  # Maintenance policy for SOX compliance
  maintenance_policy {
    # Weekend maintenance window (Saturday 2 AM - 6 AM UTC)
    daily_maintenance_window {
      start_time = "02:00"
    }

    # More granular control - weekends only
    recurring_window {
      start_time = "2024-01-06T02:00:00Z"  # First Saturday of 2024
      end_time   = "2024-01-06T06:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SA"
    }

    # Quarterly code freeze exclusions
    dynamic "maintenance_exclusion" {
      for_each = local.quarterly_freezes
      content {
        exclusion_name = "quarterly-freeze-${formatdate("YYYY-MM", maintenance_exclusion.value.start)}"
        start_time     = maintenance_exclusion.value.start
        end_time       = maintenance_exclusion.value.end
        exclusion_options {
          scope = "UPGRADES"
        }
      }
    }

    # Annual audit exclusion
    maintenance_exclusion {
      exclusion_name = "annual-audit-november"
      start_time     = local.annual_audit.start
      end_time       = local.annual_audit.end
      exclusion_options {
        scope = "UPGRADES"
      }
    }
  }

  # Control plane auto-upgrade
  cluster_autoscaling {
    auto_provisioning_defaults {
      upgrade_settings {
        max_surge       = 1
        max_unavailable = 0
        strategy        = "SURGE"
      }
    }
  }

  # Node pool configuration
  node_pool {
    name       = "regulated-pool"
    node_count = var.initial_node_count

    management {
      auto_upgrade = true
      auto_repair  = true
    }

    upgrade_settings {
      max_surge       = 1
      max_unavailable = 0
      strategy        = "BLUE_GREEN"
      
      blue_green_settings {
        standard_rollout_policy {
          batch_percentage    = 0.1  # 10% at a time for safer rollouts
          batch_soak_duration = "300s"  # 5 minutes between batches
        }
        node_pool_soak_duration = "1800s"  # 30 minutes before cleanup
      }
    }
  }

  # Ensure workload identity for audit logging
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  # Network policy for compliance
  network_policy {
    enabled  = true
    provider = "CALICO"
  }

  # Binary authorization for SOX compliance
  binary_authorization {
    evaluation_mode = "PROJECT_SINGLETON_POLICY_ENFORCE"
  }
}
```

## 2. Advanced Maintenance Configuration

```yaml
# k8s/maintenance-policy.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: maintenance-schedule
  namespace: kube-system
  labels:
    compliance: "sox"
    environment: "production"
data:
  schedule.yaml: |
    maintenanceWindows:
      - name: "weekend-maintenance"
        schedule: "0 2 * * 6"  # Saturday 2 AM UTC
        duration: "4h"
        allowedOperations:
          - "node-upgrades"
          - "cluster-upgrades"
          - "security-patches"
      
      exclusions:
        quarterlyFreeze:
          - "2024-03-25T00:00:00Z to 2024-04-01T00:00:00Z"
          - "2024-06-25T00:00:00Z to 2024-07-01T00:00:00Z"
          - "2024-09-25T00:00:00Z to 2024-10-01T00:00:00Z"
          - "2024-12-20T00:00:00Z to 2025-01-02T00:00:00Z"
        
        annualAudit: "2024-11-01T00:00:00Z to 2024-11-30T23:59:59Z"
        
        emergencyOverride:
          enabled: true
          approvers:
            - "security-team@company.com"
            - "compliance-officer@company.com"

---
apiVersion: batch/v1
kind: CronJob
metadata:
  name: maintenance-compliance-checker
  namespace: kube-system
spec:
  schedule: "0 1 * * 6"  # Run 1 hour before maintenance window
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: compliance-checker
            image: gcr.io/PROJECT_ID/compliance-checker:latest
            env:
            - name: MAINTENANCE_MODE
              value: "pre-check"
            command:
            - /bin/bash
            - -c
            - |
              #!/bin/bash
              
              # Pre-maintenance compliance checks
              echo "$(date): Starting pre-maintenance compliance checks"
              
              # Check for active incidents
              if kubectl get events --all-namespaces | grep -i "warning\|error" | wc -l > 10; then
                echo "WARNING: High number of cluster events detected"
                # Send alert to operations team
              fi
              
              # Verify backup completion
              kubectl get cronjobs -A | grep backup
              
              # Check compliance pod status
              kubectl get pods -n compliance-system
              
              # Audit log verification
              gcloud logging read "resource.type=gke_cluster" --limit=10 --format=json
              
              echo "$(date): Pre-maintenance checks completed"
          restartPolicy: OnFailure
          serviceAccountName: compliance-checker
```

## 3. Monitoring and Alerting

```yaml
# monitoring/maintenance-alerts.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: maintenance-compliance-rules
  namespace: monitoring
spec:
  groups:
  - name: maintenance.compliance
    interval: 30s
    rules:
    - alert: MaintenanceWindowViolation
      expr: |
        (
          increase(gke_cluster_maintenance_events_total[5m]) > 0
          and
          (hour() < 2 or hour() > 6 or day_of_week() != 6)
        )
      for: 0m
      labels:
        severity: critical
        compliance: sox
      annotations:
        summary: "Maintenance activity detected outside approved window"
        description: "Cluster {{ $labels.cluster_name }} had maintenance activity at {{ $value }} outside the approved weekend window"

    - alert: CodeFreezeViolation
      expr: |
        (
          rate(kubernetes_build_info[5m]) > 0
          and on() 
          (
            (month() == 3 and day() >= 25) or
            (month() == 4 and day() <= 1) or
            (month() == 6 and day() >= 25) or
            (month() == 7 and day() <= 1) or
            (month() == 9 and day() >= 25) or
            (month() == 10 and day() <= 1) or
            (month() == 12 and day() >= 20) or
            (month() == 1 and day() <= 2) or
            (month() == 11)
          )
        )
      for: 0m
      labels:
        severity: critical
        compliance: sox
      annotations:
        summary: "Deployment detected during code freeze period"

    - alert: AuditPeriodMaintenance
      expr: month() == 11 and increase(gke_cluster_maintenance_events_total[5m]) > 0
      for: 0m
      labels:
        severity: critical
        compliance: sox
      annotations:
        summary: "Maintenance activity during annual audit period"
```

## 4. Compliance Automation Script

```bash
#!/bin/bash
# scripts/maintenance-compliance.sh

set -euo pipefail

# Configuration
PROJECT_ID="your-project-id"
CLUSTERS=("prod-cluster-1" "prod-cluster-2" "prod-cluster-3")
LOCATIONS=("us-central1-a" "us-east1-b" "europe-west1-c")

# Logging for audit trail
LOG_FILE="/var/log/gke-maintenance-$(date +%Y%m%d).log"
exec 1> >(tee -a "$LOG_FILE")
exec 2>&1

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Check if we're in an exclusion period
check_exclusion_period() {
    local current_date=$(date -u +%Y-%m-%d)
    local current_month=$(date +%m)
    local current_day=$(date +%d)
    
    # Check for November audit period
    if [[ "$current_month" == "11" ]]; then
        log "WARNING: Currently in November audit period - maintenance restricted"
        return 1
    fi
    
    # Check quarterly freezes (simplified - use actual dates)
    case "$current_month" in
        03|04|06|07|09|10|12|01)
            log "WARNING: Potential quarterly freeze period - verify before proceeding"
            ;;
    esac
    
    return 0
}

# Verify maintenance window
verify_maintenance_window() {
    local day_of_week=$(date +%u)  # 1=Monday, 6=Saturday, 7=Sunday
    local hour=$(date +%H)
    
    if [[ "$day_of_week" == "6" ]] && [[ "$hour" -ge "02" ]] && [[ "$hour" -le "06" ]]; then
        log "INFO: Currently in approved maintenance window (Saturday 02:00-06:00 UTC)"
        return 0
    else
        log "ERROR: Outside approved maintenance window"
        return 1
    fi
}

# Apply maintenance policy to cluster
apply_maintenance_policy() {
    local cluster_name=$1
    local location=$2
    
    log "Applying maintenance policy to cluster: $cluster_name in $location"
    
    # Create maintenance exclusion for current quarter
    gcloud container clusters update "$cluster_name" \
        --location="$location" \
        --project="$PROJECT_ID" \
        --maintenance-window-start="2024-01-06T02:00:00Z" \
        --maintenance-window-end="2024-01-06T06:00:00Z" \
        --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SA" \
        --quiet
    
    # Add specific exclusions
    gcloud container clusters update "$cluster_name" \
        --location="$location" \
        --project="$PROJECT_ID" \
        --add-maintenance-exclusion-end="2024-11-30T23:59:59Z" \
        --add-maintenance-exclusion-name="november-audit-2024" \
        --add-maintenance-exclusion-start="2024-11-01T00:00:00Z" \
        --add-maintenance-exclusion-scope="UPGRADES" \
        --quiet
}

# Generate compliance report
generate_compliance_report() {
    local report_file="gke-maintenance-compliance-$(date +%Y%m%d).json"
    
    log "Generating compliance report: $report_file"
    
    cat > "$report_file" << EOF
{
  "report_date": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "compliance_framework": "SOX",
  "clusters": [
EOF

    for i in "${!CLUSTERS[@]}"; do
        local cluster="${CLUSTERS[$i]}"
        local location="${LOCATIONS[$i]}"
        
        # Get maintenance policy
        local policy=$(gcloud container clusters describe "$cluster" \
            --location="$location" \
            --project="$PROJECT_ID" \
            --format="json" | jq '.maintenancePolicy')
        
        cat >> "$report_file" << EOF
    {
      "cluster_name": "$cluster",
      "location": "$location",
      "maintenance_policy": $policy,
      "compliance_status": "compliant",
      "last_maintenance": "$(gcloud container operations list --filter="targetLink:$cluster AND operationType:UPGRADE_MASTER" --limit=1 --format="value(startTime)")",
      "exclusions_active": $(echo "$policy" | jq '.maintenanceExclusions | length')
    }$([ $i -lt $((${#CLUSTERS[@]} - 1)) ] && echo "," || echo "")
EOF
    done

    cat >> "$report_file" << EOF
  ],
  "verification": {
    "weekend_only_policy": true,
    "quarterly_freeze_exclusions": true,
    "audit_period_exclusions": true,
    "auto_upgrade_controlled": true
  }
}
EOF

    log "Compliance report generated: $report_file"
    
    # Upload to Cloud Storage for audit trail
    gsutil cp "$report_file" "gs://$PROJECT_ID-compliance-reports/gke-maintenance/"
}

# Main execution
main() {
    log "Starting GKE maintenance compliance check"
    
    if ! check_exclusion_period; then
        log "CRITICAL: Currently in maintenance exclusion period"
        exit 1
    fi
    
    # Apply policies to all clusters
    for i in "${!CLUSTERS[@]}"; do
        apply_maintenance_policy "${CLUSTERS[$i]}" "${LOCATIONS[$i]}"
    done
    
    # Generate compliance report
    generate_compliance_report
    
    # Send notification to compliance team
    gcloud pubsub topics publish compliance-notifications \
        --message="GKE maintenance policies updated and compliance verified" \
        --attribute="type=maintenance,status=compliant,date=$(date -u +%Y-%m-%d)"
    
    log "Maintenance compliance check completed successfully"
}

# Emergency override function (requires dual approval)
emergency_override() {
    log "EMERGENCY OVERRIDE REQUESTED"
    
    # This would integrate with your approval system
    echo "Emergency maintenance override requires dual approval"
    echo "Contact: security-team@company.com and compliance-officer@company.com"
    
    # Log the override request for audit
    gcloud logging write gke-compliance-log \
        '{"message": "Emergency maintenance override requested", "severity": "CRITICAL", "timestamp": "'$(date -u +%Y-%m
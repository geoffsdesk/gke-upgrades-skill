I'll help you configure maintenance windows and exclusions for your GKE Standard clusters to meet SOX compliance requirements. Here's a comprehensive setup:

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
  description = "GCP Region"
  type        = string
  default     = "us-central1"
}

# Current year for maintenance exclusions
locals {
  current_year = formatdate("YYYY", timestamp())
  next_year    = tostring(tonumber(local.current_year) + 1)
}

# main.tf
resource "google_container_cluster" "clusters" {
  for_each = toset(var.cluster_names)
  
  name     = each.value
  location = var.region
  project  = var.project_id

  # Maintenance policy with weekend-only windows
  maintenance_policy {
    recurring_window {
      start_time = "2024-01-06T02:00:00Z"  # Saturday 2 AM UTC
      end_time   = "2024-01-07T06:00:00Z"  # Sunday 6 AM UTC
      recurrence = "FREQ=WEEKLY"
    }
    
    # Q1 Code Freeze (March)
    maintenance_exclusion {
      exclusion_name = "Q1-code-freeze-${local.current_year}"
      start_time     = "${local.current_year}-03-01T00:00:00Z"
      end_time       = "${local.current_year}-03-31T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    # Q2 Code Freeze (June)
    maintenance_exclusion {
      exclusion_name = "Q2-code-freeze-${local.current_year}"
      start_time     = "${local.current_year}-06-01T00:00:00Z"
      end_time       = "${local.current_year}-06-30T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    # Q3 Code Freeze (September)
    maintenance_exclusion {
      exclusion_name = "Q3-code-freeze-${local.current_year}"
      start_time     = "${local.current_year}-09-01T00:00:00Z"
      end_time       = "${local.current_year}-09-30T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    # Q4 Code Freeze & Annual Audit (November-December)
    maintenance_exclusion {
      exclusion_name = "Q4-code-freeze-annual-audit-${local.current_year}"
      start_time     = "${local.current_year}-11-01T00:00:00Z"
      end_time       = "${local.current_year}-12-31T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }
  }

  # Enable auto-upgrade for node pools (will respect maintenance windows)
  node_pool {
    name = "default-pool"
    
    management {
      auto_repair  = true
      auto_upgrade = true
    }

    upgrade_settings {
      strategy        = "SURGE"
      max_surge       = 1
      max_unavailable = 0
    }
  }

  # Release channel for controlled updates
  release_channel {
    channel = "REGULAR"  # Use STABLE for even more conservative updates
  }

  # Network and security settings
  network_policy {
    enabled = true
  }

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  tags = ["sox-compliant", "regulated-environment"]
}
```

## 2. gcloud Commands for Existing Clusters

If you need to update existing clusters:

```bash
#!/bin/bash
# update-maintenance-windows.sh

CLUSTERS=("prod-cluster" "staging-cluster" "dev-cluster")
PROJECT_ID="your-project-id"
REGION="us-central1"
CURRENT_YEAR=$(date +%Y)

for cluster in "${CLUSTERS[@]}"; do
  echo "Updating maintenance policy for $cluster..."
  
  # Set maintenance window (Saturdays 2 AM - Sundays 6 AM UTC)
  gcloud container clusters update $cluster \
    --project=$PROJECT_ID \
    --region=$REGION \
    --maintenance-window-start "2024-01-06T02:00:00Z" \
    --maintenance-window-end "2024-01-07T06:00:00Z" \
    --maintenance-window-recurrence "FREQ=WEEKLY"
  
  # Add quarterly code freeze exclusions
  gcloud container clusters update $cluster \
    --project=$PROJECT_ID \
    --region=$REGION \
    --add-maintenance-exclusion-end "${CURRENT_YEAR}-03-31T23:59:59Z" \
    --add-maintenance-exclusion-name "Q1-code-freeze-${CURRENT_YEAR}" \
    --add-maintenance-exclusion-scope "ALL_UPGRADES" \
    --add-maintenance-exclusion-start "${CURRENT_YEAR}-03-01T00:00:00Z"
  
  gcloud container clusters update $cluster \
    --project=$PROJECT_ID \
    --region=$REGION \
    --add-maintenance-exclusion-end "${CURRENT_YEAR}-06-30T23:59:59Z" \
    --add-maintenance-exclusion-name "Q2-code-freeze-${CURRENT_YEAR}" \
    --add-maintenance-exclusion-scope "ALL_UPGRADES" \
    --add-maintenance-exclusion-start "${CURRENT_YEAR}-06-01T00:00:00Z"
  
  gcloud container clusters update $cluster \
    --project=$PROJECT_ID \
    --region=$REGION \
    --add-maintenance-exclusion-end "${CURRENT_YEAR}-09-30T23:59:59Z" \
    --add-maintenance-exclusion-name "Q3-code-freeze-${CURRENT_YEAR}" \
    --add-maintenance-exclusion-scope "ALL_UPGRADES" \
    --add-maintenance-exclusion-start "${CURRENT_YEAR}-09-01T00:00:00Z"
  
  # Extended Q4 exclusion for code freeze + annual audit
  gcloud container clusters update $cluster \
    --project=$PROJECT_ID \
    --region=$REGION \
    --add-maintenance-exclusion-end "${CURRENT_YEAR}-12-31T23:59:59Z" \
    --add-maintenance-exclusion-name "Q4-code-freeze-annual-audit-${CURRENT_YEAR}" \
    --add-maintenance-exclusion-scope "ALL_UPGRADES" \
    --add-maintenance-exclusion-start "${CURRENT_YEAR}-11-01T00:00:00Z"
done
```

## 3. SOX Compliance Monitoring Script

```bash
#!/bin/bash
# sox-compliance-check.sh

PROJECT_ID="your-project-id"
REGION="us-central1"
CLUSTERS=("prod-cluster" "staging-cluster" "dev-cluster")

echo "SOX Compliance Check - $(date)"
echo "================================"

for cluster in "${CLUSTERS[@]}"; do
  echo "Checking cluster: $cluster"
  
  # Get maintenance policy
  gcloud container clusters describe $cluster \
    --project=$PROJECT_ID \
    --region=$REGION \
    --format="yaml(maintenancePolicy)" > "/tmp/${cluster}-maintenance.yaml"
  
  # Check for maintenance exclusions
  exclusions=$(gcloud container clusters describe $cluster \
    --project=$PROJECT_ID \
    --region=$REGION \
    --format="value(maintenancePolicy.maintenanceExclusions[].exclusionName)")
  
  echo "  Active maintenance exclusions:"
  if [ -z "$exclusions" ]; then
    echo "    WARNING: No maintenance exclusions found!"
  else
    echo "$exclusions" | while read exclusion; do
      echo "    - $exclusion"
    done
  fi
  
  echo ""
done
```

## 4. Annual Maintenance Exclusion Update Script

```bash
#!/bin/bash
# annual-exclusion-update.sh
# Run this script in January to update exclusions for the new year

PROJECT_ID="your-project-id"
REGION="us-central1"
CLUSTERS=("prod-cluster" "staging-cluster" "dev-cluster")
CURRENT_YEAR=$(date +%Y)
LAST_YEAR=$((CURRENT_YEAR - 1))

for cluster in "${CLUSTERS[@]}"; do
  echo "Updating annual exclusions for $cluster..."
  
  # Remove last year's exclusions
  for quarter in "Q1" "Q2" "Q3" "Q4"; do
    gcloud container clusters update $cluster \
      --project=$PROJECT_ID \
      --region=$REGION \
      --remove-maintenance-exclusion "${quarter}-code-freeze-${LAST_YEAR}" \
      --quiet || true
  done
  
  # Remove last year's audit exclusion
  gcloud container clusters update $cluster \
    --project=$PROJECT_ID \
    --region=$REGION \
    --remove-maintenance-exclusion "Q4-code-freeze-annual-audit-${LAST_YEAR}" \
    --quiet || true
  
  # Add this year's exclusions
  # Q1 through Q4 exclusions (same as in the initial script)
  # ... (repeat the add-maintenance-exclusion commands from above with CURRENT_YEAR)
done
```

## 5. Monitoring and Alerting Configuration

```yaml
# monitoring-policy.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: maintenance-monitoring
data:
  policy.yaml: |
    displayName: "GKE Maintenance Compliance Monitoring"
    conditions:
      - displayName: "Unscheduled GKE Upgrade"
        conditionThreshold:
          filter: 'resource.type="gke_cluster" AND protoPayload.methodName="google.container.v1.ClusterManager.UpdateCluster"'
          comparison: COMPARISON_GREATER_THAN
          thresholdValue: 0
        documentation:
          content: "An unscheduled GKE upgrade was detected during a maintenance exclusion period"
    alertPolicy:
      notificationChannels:
        - "projects/PROJECT_ID/notificationChannels/NOTIFICATION_CHANNEL_ID"
```

## 6. Best Practices for SOX Compliance

```bash
# Create a compliance report
cat << 'EOF' > compliance-report.sh
#!/bin/bash
# Generate SOX compliance report

PROJECT_ID="your-project-id"
DATE=$(date +%Y%m%d)
REPORT_FILE="gke-compliance-report-${DATE}.txt"

{
  echo "GKE SOX Compliance Report - $(date)"
  echo "======================================="
  echo ""
  
  for cluster in prod-cluster staging-cluster dev-cluster; do
    echo "CLUSTER: $cluster"
    echo "----------------"
    
    # Maintenance windows
    echo "Maintenance Windows:"
    gcloud container clusters describe $cluster \
      --region=us-central1 \
      --format="table(maintenancePolicy.window.recurringWindow.window.startTime, maintenancePolicy.window.recurringWindow.window.endTime)" \
      --project=$PROJECT_ID
    
    # Exclusions
    echo ""
    echo "Maintenance Exclusions:"
    gcloud container clusters describe $cluster \
      --region=us-central1 \
      --format="table(maintenancePolicy.maintenanceExclusions[].exclusionName, maintenancePolicy.maintenanceExclusions[].startTime, maintenancePolicy.maintenanceExclusions[].endTime)" \
      --project=$PROJECT_ID
    
    echo ""
    echo "----------------------------------------"
    echo ""
  done
} > "$REPORT_FILE"

echo "Compliance report generated: $REPORT_FILE"
EOF

chmod +x compliance-report.sh
```

## Key Features of This Setup:

1. **Weekend-Only Maintenance**: All upgrades restricted to Saturday 2 AM - Sunday 6 AM UTC
2. **Quarterly Code Freezes**: Complete upgrade exclusions for March, June, September
3. **Extended November Freeze**: Covers both Q4 code freeze and annual audit period
4. **SOX Compliance**: All changes are logged and auditable
5. **Automated Management**: Scripts for annual updates and compliance checking

## Next Steps:

1. Adjust the timezone in maintenance windows to match your business hours
2. Set up monitoring alerts for any maintenance activities
3. Create a change management process for emergency updates during exclusion periods
4. Schedule the annual exclusion update script to run automatically each January

This configuration ensures your GKE clusters remain compliant with SOX requirements while maintaining security through controlled, scheduled updates.
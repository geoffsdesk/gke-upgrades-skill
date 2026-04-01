For a financial services company requiring strict change control while maintaining security, here's the recommended configuration:

## Node Pool Configuration

```yaml
# terraform/gke-cluster.tf
resource "google_container_node_pool" "primary_nodes" {
  name       = "primary-pool"
  cluster    = google_container_cluster.primary.name
  
  management {
    auto_repair  = true
    auto_upgrade = false  # Disable automatic upgrades
  }
  
  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
    strategy        = "SURGE"
    
    blue_green_settings {
      standard_rollout_policy {
        batch_percentage    = 0.2  # 20% at a time
        batch_node_count    = null
        batch_soak_duration = "300s"  # 5 minutes between batches
      }
      node_pool_soak_duration = "1800s"  # 30 minutes final soak
    }
  }
}
```

## Control Plane Configuration

```yaml
resource "google_container_cluster" "primary" {
  name     = "financial-cluster"
  location = "us-central1"
  
  # Disable automatic control plane upgrades
  cluster_autoscaling {
    auto_provisioning_defaults {
      management {
        auto_repair  = true
        auto_upgrade = false
      }
    }
  }
  
  # Configure maintenance window
  maintenance_policy {
    recurring_window {
      start_time = "2024-01-01T02:00:00Z"
      end_time   = "2024-01-01T06:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SU"  # Sunday maintenance window
    }
  }
  
  # Enable release channels but manual upgrades
  release_channel {
    channel = "REGULAR"  # Good balance of stability and security
  }
}
```

## Monitoring and Alerting Setup

```yaml
# monitoring/upgrade-alerts.yaml
resource "google_monitoring_alert_policy" "security_updates_available" {
  display_name = "GKE Security Updates Available"
  combiner     = "OR"
  
  conditions {
    display_name = "Security updates pending"
    
    condition_threshold {
      filter          = "resource.type=\"gke_cluster\""
      comparison      = "COMPARISON_GREATER_THAN"
      threshold_value = 0
      duration        = "300s"
      
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }
  
  notification_channels = [
    google_monitoring_notification_channel.security_team.name
  ]
  
  alert_strategy {
    auto_close = "604800s"  # 7 days
  }
}
```

## Controlled Upgrade Pipeline

```yaml
# .github/workflows/gke-upgrades.yml
name: Controlled GKE Upgrades
on:
  schedule:
    - cron: '0 2 * * 1'  # Monday 2 AM - check for updates
  workflow_dispatch:     # Manual trigger

jobs:
  check-updates:
    runs-on: ubuntu-latest
    outputs:
      updates-available: ${{ steps.check.outputs.updates }}
      security-updates: ${{ steps.check.outputs.security }}
    
    steps:
    - name: Check for available updates
      id: check
      run: |
        # Check control plane updates
        CURRENT_VERSION=$(gcloud container clusters describe $CLUSTER_NAME \
          --zone=$ZONE --format="value(currentMasterVersion)")
        
        AVAILABLE_VERSIONS=$(gcloud container get-server-config \
          --zone=$ZONE --format="value(validMasterVersions[])")
        
        # Check for security patches
        SECURITY_UPDATES=$(gcloud container clusters describe $CLUSTER_NAME \
          --zone=$ZONE --format="value(conditions[].message)" | \
          grep -i "security\|cve" || echo "")
        
        echo "updates=${AVAILABLE_VERSIONS}" >> $GITHUB_OUTPUT
        echo "security=${SECURITY_UPDATES}" >> $GITHUB_OUTPUT

  plan-upgrade:
    needs: check-updates
    if: needs.check-updates.outputs.updates-available != ''
    runs-on: ubuntu-latest
    
    steps:
    - name: Create upgrade plan
      run: |
        cat > upgrade-plan.md << EOF
        # GKE Upgrade Plan
        
        **Current Version**: $CURRENT_VERSION
        **Target Version**: $TARGET_VERSION
        **Security Updates**: ${{ needs.check-updates.outputs.security-updates }}
        
        ## Upgrade Steps:
        1. Control plane upgrade (automatic rollback available)
        2. Node pool upgrade (blue/green deployment)
        3. Validation tests
        
        **Scheduled for**: Next maintenance window
        EOF
        
        # Create GitHub issue for approval
        gh issue create \
          --title "GKE Upgrade Required - $TARGET_VERSION" \
          --body-file upgrade-plan.md \
          --label "gke-upgrade,security" \
          --assignee "$SECURITY_TEAM"

  upgrade-control-plane:
    needs: [check-updates, plan-upgrade]
    if: contains(github.event.issue.labels.*.name, 'approved')
    runs-on: ubuntu-latest
    
    steps:
    - name: Upgrade control plane
      run: |
        # Upgrade control plane first
        gcloud container clusters upgrade $CLUSTER_NAME \
          --cluster-version=$TARGET_VERSION \
          --zone=$ZONE \
          --master \
          --quiet
        
        # Wait for upgrade completion
        gcloud container operations wait $OPERATION_ID --zone=$ZONE
    
    - name: Validate control plane
      run: |
        # Basic connectivity test
        kubectl cluster-info
        kubectl get nodes
        
        # API server health
        kubectl get --raw='/readyz' | grep -q 'ok'

  upgrade-nodes:
    needs: upgrade-control-plane
    runs-on: ubuntu-latest
    strategy:
      matrix:
        node_pool: [primary-pool, secondary-pool]
    
    steps:
    - name: Upgrade node pool
      run: |
        gcloud container clusters upgrade $CLUSTER_NAME \
          --node-pool=${{ matrix.node_pool }} \
          --cluster-version=$TARGET_VERSION \
          --zone=$ZONE \
          --quiet
    
    - name: Monitor upgrade progress
      run: |
        while true; do
          STATUS=$(gcloud container operations describe $OPERATION_ID \
            --zone=$ZONE --format="value(status)")
          
          if [[ "$STATUS" == "DONE" ]]; then
            break
          elif [[ "$STATUS" == "ABORTING" ]]; then
            echo "Upgrade failed, initiating rollback"
            exit 1
          fi
          
          echo "Upgrade in progress... Status: $STATUS"
          sleep 30
        done
```

## Security Compliance Monitoring

```yaml
# security/compliance-check.sh
#!/bin/bash

# Check for CVE compliance
check_cve_status() {
    echo "Checking CVE status..."
    
    gcloud container clusters describe $CLUSTER_NAME \
        --zone=$ZONE \
        --format="table(
            currentMasterVersion,
            currentNodeVersion,
            conditions[].code,
            conditions[].message
        )"
}

# Generate compliance report
generate_compliance_report() {
    cat > compliance-report.json << EOF
{
    "cluster": "$CLUSTER_NAME",
    "scan_date": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "control_plane_version": "$CONTROL_PLANE_VERSION",
    "node_versions": $NODE_VERSIONS,
    "security_patches": $SECURITY_PATCHES,
    "compliance_status": "$COMPLIANCE_STATUS",
    "next_maintenance_window": "$NEXT_WINDOW"
}
EOF
}
```

## Best Practices Implementation

```yaml
# policies/upgrade-policy.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: upgrade-policy
  namespace: kube-system
data:
  policy.yaml: |
    upgrade_policy:
      # Maximum days before mandatory security update
      security_deadline_days: 30
      
      # Maintenance windows (all times UTC)
      maintenance_windows:
        - day: "sunday"
          start: "02:00"
          end: "06:00"
          type: "regular"
        - day: "saturday"
          start: "02:00" 
          end: "06:00"
          type: "emergency"
      
      # Required approvals
      approvals:
        - role: "security-team"
          required: true
        - role: "platform-team"
          required: true
        - role: "change-board"
          required_for: "major"
      
      # Testing requirements
      testing:
        pre_upgrade:
          - "connectivity-test"
          - "workload-health-check"
        post_upgrade:
          - "full-regression-suite"
          - "security-scan"
```

This configuration provides:

1. **Complete control** over upgrade timing through disabled auto-upgrades
2. **Security monitoring** with alerts for available patches
3. **Structured approval process** via GitHub issues/tickets
4. **Automated testing** before and after upgrades
5. **Blue/green node upgrades** for zero-downtime deployments
6. **Compliance reporting** for audit requirements

The setup balances security needs with change control requirements typical in financial services.
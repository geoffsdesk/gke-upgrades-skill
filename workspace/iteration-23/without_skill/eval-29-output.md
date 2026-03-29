Here's the exact configuration for your GKE cluster maintenance exclusions and policies:

## 1. Cluster Configuration with Maintenance Policy

```yaml
# terraform/gke-cluster.tf
resource "google_container_cluster" "main" {
  name     = "your-cluster-name"
  location = "us-central1"

  # Disable automatic upgrades - require explicit approval
  release_channel {
    channel = "REGULAR"  # or "RAPID" or "STABLE"
  }

  # Maintenance policy with exclusions
  maintenance_policy {
    # Daily maintenance window (adjust timezone as needed)
    daily_maintenance_window {
      start_time = "03:00"  # 3 AM in cluster's timezone
    }

    # Quarterly code freeze in June
    maintenance_exclusion {
      exclusion_name = "june-code-freeze"
      start_time     = "2024-06-01T00:00:00Z"
      end_time       = "2024-06-30T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    # Black Friday/Cyber Monday exclusion (extended period)
    maintenance_exclusion {
      exclusion_name = "black-friday-cyber-monday"
      start_time     = "2024-11-20T00:00:00Z"
      end_time       = "2024-12-03T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }
  }

  # Node auto-upgrade and auto-repair settings
  node_config {
    # ... other node config
  }

  # Disable automatic node upgrades
  node_pool {
    name = "default-pool"
    
    management {
      auto_repair  = true   # Keep auto-repair for security
      auto_upgrade = false  # Disable auto-upgrade for control
    }
    
    upgrade_settings {
      strategy      = "SURGE"
      max_surge     = 1
      max_unavailable = 0
    }
  }
}
```

## 2. Recurring Annual Exclusions Script

Since Terraform maintenance exclusions need absolute dates, create this script to update them annually:

```bash
#!/bin/bash
# scripts/update-maintenance-exclusions.sh

CLUSTER_NAME="your-cluster-name"
ZONE="us-central1"
CURRENT_YEAR=$(date +%Y)
NEXT_YEAR=$((CURRENT_YEAR + 1))

echo "Updating maintenance exclusions for $CURRENT_YEAR and $NEXT_YEAR"

# Remove old exclusions
gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --remove-maintenance-exclusion-name="june-code-freeze" \
    --quiet

gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --remove-maintenance-exclusion-name="black-friday-cyber-monday" \
    --quiet

# Add current year exclusions
gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --add-maintenance-exclusion-name="june-code-freeze" \
    --add-maintenance-exclusion-start="${CURRENT_YEAR}-06-01T00:00:00Z" \
    --add-maintenance-exclusion-end="${CURRENT_YEAR}-06-30T23:59:59Z" \
    --add-maintenance-exclusion-scope="ALL_UPGRADES"

gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --add-maintenance-exclusion-name="black-friday-cyber-monday" \
    --add-maintenance-exclusion-start="${CURRENT_YEAR}-11-20T00:00:00Z" \
    --add-maintenance-exclusion-end="${CURRENT_YEAR}-12-03T23:59:59Z" \
    --add-maintenance-exclusion-scope="ALL_UPGRADES"

echo "Maintenance exclusions updated successfully"
```

## 3. Disable Automatic Minor Version Upgrades

```bash
# For existing clusters - disable auto-upgrades completely
gcloud container clusters update your-cluster-name \
    --zone=us-central1 \
    --no-enable-autoupgrade

# For node pools specifically
gcloud container node-pools update default-pool \
    --cluster=your-cluster-name \
    --zone=us-central1 \
    --no-enable-autoupgrade
```

## 4. Manual Upgrade Process Script

```bash
#!/bin/bash
# scripts/manual-upgrade.sh

CLUSTER_NAME="your-cluster-name"
ZONE="us-central1"

echo "Current cluster version:"
gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="value(currentMasterVersion)"

echo "Available master versions:"
gcloud container get-server-config --zone=$ZONE --format="value(validMasterVersions[0:5])"

echo "Available node versions:"
gcloud container get-server-config --zone=$ZONE --format="value(validNodeVersions[0:5])"

read -p "Enter the master version to upgrade to: " MASTER_VERSION
read -p "Enter the node version to upgrade to: " NODE_VERSION

# Upgrade master first
echo "Upgrading master to $MASTER_VERSION..."
gcloud container clusters upgrade $CLUSTER_NAME \
    --zone=$ZONE \
    --master \
    --cluster-version=$MASTER_VERSION

# Upgrade nodes
echo "Upgrading nodes to $NODE_VERSION..."
gcloud container clusters upgrade $CLUSTER_NAME \
    --zone=$ZONE \
    --node-pool=default-pool \
    --cluster-version=$NODE_VERSION
```

## 5. Monitoring and Alerts

```yaml
# monitoring/maintenance-alerts.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: gke-maintenance-alerts
spec:
  groups:
  - name: gke.maintenance
    rules:
    - alert: GKEVersionOutdated
      expr: |
        (
          kube_node_info{kubelet_version!~"v1\\.(2[6-9]|[3-9][0-9])\\..*"}
        ) > 0
      for: 7d
      labels:
        severity: warning
      annotations:
        summary: "GKE nodes running outdated Kubernetes version"
        description: "Cluster has nodes running Kubernetes version {{ $labels.kubelet_version }} which may need updating"
```

## 6. Calendar Reminder Setup

```bash
# scripts/setup-calendar-reminders.sh

# Add to your CI/CD pipeline or cron
# Run this script on January 1st each year

cat << EOF > maintenance-calendar.ics
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Your Company//GKE Maintenance//EN

BEGIN:VEVENT
UID:june-code-freeze@yourcompany.com
DTSTART:$(date -d "June 1" +%Y%m%d)T000000Z
DTEND:$(date -d "June 30" +%Y%m%d)T235959Z
SUMMARY:GKE Maintenance Exclusion - June Code Freeze
DESCRIPTION:No GKE upgrades allowed during quarterly code freeze
RRULE:FREQ=YEARLY
END:VEVENT

BEGIN:VEVENT
UID:black-friday-exclusion@yourcompany.com
DTSTART:$(date -d "November 20" +%Y%m%d)T000000Z
DTEND:$(date -d "December 3" +%Y%m%d)T235959Z
SUMMARY:GKE Maintenance Exclusion - Black Friday/Cyber Monday
DESCRIPTION:No GKE upgrades allowed during peak shopping season
RRULE:FREQ=YEARLY
END:VEVENT

END:VCALENDAR
EOF
```

## 7. Validation Commands

```bash
# Check current maintenance policy
gcloud container clusters describe your-cluster-name \
    --zone=us-central1 \
    --format="yaml(maintenancePolicy)"

# Check if auto-upgrade is disabled
gcloud container clusters describe your-cluster-name \
    --zone=us-central1 \
    --format="value(nodePools[].management.autoUpgrade)"

# List active maintenance exclusions
gcloud container clusters describe your-cluster-name \
    --zone=us-central1 \
    --format="table(maintenancePolicy.window.maintenanceExclusions[].exclusionName,maintenancePolicy.window.maintenanceExclusions[].startTime,maintenancePolicy.window.maintenanceExclusions[].endTime)"
```

## Key Points:

1. **Auto-upgrades disabled**: Requires explicit approval for all upgrades
2. **June exclusion**: Covers entire month for quarterly code freeze
3. **November/December exclusion**: Extended period covering Black Friday through Cyber Monday
4. **Annual script**: Updates exclusion dates yearly since they require absolute timestamps
5. **Monitoring**: Alerts when versions become outdated
6. **Manual process**: Controlled upgrade script for when you're ready

Remember to:
- Run the annual exclusion update script each January
- Adjust timezone in maintenance windows as needed
- Test the manual upgrade process in a dev environment first
- Set up calendar reminders for maintenance planning
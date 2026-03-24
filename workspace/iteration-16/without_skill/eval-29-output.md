I'll help you set up maintenance exclusions for your GKE clusters to handle your specific requirements. Here's the exact configuration:

## 1. Terraform Configuration

```hcl
resource "google_container_cluster" "primary" {
  name     = "your-cluster-name"
  location = "us-central1"
  
  # Disable automatic upgrades for control plane and nodes
  release_channel {
    channel = "REGULAR" # or "STABLE" - avoid "RAPID"
  }

  # Control plane maintenance policy
  maintenance_policy {
    # Quarterly code freeze in June (entire month)
    recurring_window {
      start_time = "2024-06-01T00:00:00Z"
      end_time   = "2024-07-01T00:00:00Z"
      recurrence = "FREQ=YEARLY;BYMONTH=6"
    }
  }

  # Node pool configuration
  node_pool {
    name = "default-pool"
    
    management {
      auto_repair  = true
      auto_upgrade = false  # Disable automatic minor version upgrades
    }

    upgrade_settings {
      strategy = "SURGE"
      max_surge = 1
      max_unavailable = 0
    }
  }

  # Additional maintenance exclusions
  maintenance_policy {
    # Black Friday period exclusion (November 20-30)
    recurring_window {
      start_time = "2024-11-20T00:00:00Z"
      end_time   = "2024-12-01T00:00:00Z"
      recurrence = "FREQ=YEARLY;BYMONTH=11;BYMONTHDAY=20"
    }
  }
}
```

## 2. gcloud CLI Configuration

```bash
# Set maintenance exclusions for June code freeze
gcloud container clusters update YOUR_CLUSTER_NAME \
  --zone=YOUR_ZONE \
  --add-maintenance-exclusion-name=june-code-freeze \
  --add-maintenance-exclusion-start=2024-06-01T00:00:00Z \
  --add-maintenance-exclusion-end=2024-07-01T00:00:00Z \
  --add-maintenance-exclusion-scope=NO_UPGRADES

# Set maintenance exclusions for Black Friday/Cyber Monday
gcloud container clusters update YOUR_CLUSTER_NAME \
  --zone=YOUR_ZONE \
  --add-maintenance-exclusion-name=black-friday-period \
  --add-maintenance-exclusion-start=2024-11-20T00:00:00Z \
  --add-maintenance-exclusion-end=2024-12-01T00:00:00Z \
  --add-maintenance-exclusion-scope=NO_UPGRADES

# Disable automatic node upgrades (for manual control)
gcloud container clusters update YOUR_CLUSTER_NAME \
  --zone=YOUR_ZONE \
  --no-enable-autoupgrade

# Set maintenance window for when upgrades ARE allowed (e.g., Sunday 2-6 AM)
gcloud container clusters update YOUR_CLUSTER_NAME \
  --zone=YOUR_ZONE \
  --maintenance-window-start=2024-01-07T02:00:00Z \
  --maintenance-window-end=2024-01-07T06:00:00Z \
  --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SU"
```

## 3. Complete YAML Configuration (for GitOps)

```yaml
# maintenance-policy.yaml
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerCluster
metadata:
  name: your-cluster-name
spec:
  location: us-central1
  releaseChannel:
    channel: REGULAR
  maintenancePolicy:
    window:
      recurringWindow:
        window:
          startTime: "2024-01-07T02:00:00Z"
          endTime: "2024-01-07T06:00:00Z"
        recurrence: "FREQ=WEEKLY;BYDAY=SU"
    maintenanceExclusions:
      june-code-freeze:
        exclusionName: "june-code-freeze"
        startTime: "2024-06-01T00:00:00Z"
        endTime: "2024-07-01T00:00:00Z"
        exclusionOptions:
          scope: NO_UPGRADES
      black-friday-exclusion:
        exclusionName: "black-friday-exclusion"
        startTime: "2024-11-20T00:00:00Z"
        endTime: "2024-12-01T00:00:00Z"
        exclusionOptions:
          scope: NO_UPGRADES
  nodePools:
  - name: default-pool
    management:
      autoRepair: true
      autoUpgrade: false
    upgradeSettings:
      strategy: SURGE
      maxSurge: 1
      maxUnavailable: 0
```

## 4. Monitoring and Alerting Script

```bash
#!/bin/bash
# check-pending-upgrades.sh

CLUSTER_NAME="your-cluster-name"
ZONE="your-zone"

# Check for available upgrades
MASTER_VERSION=$(gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="value(currentMasterVersion)")
AVAILABLE_VERSIONS=$(gcloud container get-server-config --zone=$ZONE --format="value(validMasterVersions[0])")

if [ "$MASTER_VERSION" != "$AVAILABLE_VERSIONS" ]; then
    echo "⚠️  Upgrade available: Current=$MASTER_VERSION, Latest=$AVAILABLE_VERSIONS"
    # Send to your alerting system (Slack, PagerDuty, etc.)
    curl -X POST -H 'Content-type: application/json' \
        --data '{"text":"GKE Cluster upgrade available: '$CLUSTER_NAME'"}' \
        YOUR_SLACK_WEBHOOK_URL
fi
```

## 5. Manual Upgrade Commands (for when you're ready)

```bash
# Check available versions
gcloud container get-server-config --zone=YOUR_ZONE

# Upgrade control plane
gcloud container clusters upgrade YOUR_CLUSTER_NAME \
  --zone=YOUR_ZONE \
  --cluster-version=VERSION_NUMBER \
  --master

# Upgrade specific node pool
gcloud container clusters upgrade YOUR_CLUSTER_NAME \
  --zone=YOUR_ZONE \
  --node-pool=default-pool \
  --cluster-version=VERSION_NUMBER
```

## 6. Additional Recommendations

```bash
# Set up notification channels for maintenance events
gcloud alpha container clusters update YOUR_CLUSTER_NAME \
  --zone=YOUR_ZONE \
  --notification-config-pubsub-topic=projects/YOUR_PROJECT/topics/gke-maintenance

# Enable workload identity for secure upgrades
gcloud container clusters update YOUR_CLUSTER_NAME \
  --zone=YOUR_ZONE \
  --workload-pool=YOUR_PROJECT.svc.id.goog
```

## Key Points:

1. **June Exclusion**: Blocks all maintenance for the entire month
2. **November Exclusion**: Blocks maintenance from Nov 20-30 (covering Black Friday/Cyber Monday)
3. **Manual Upgrades**: Auto-upgrade disabled, requiring explicit approval
4. **Maintenance Window**: Set to Sundays 2-6 AM when upgrades are permitted
5. **Monitoring**: Script to alert you of pending upgrades

Remember to:
- Update the years in the timestamps annually
- Test upgrades in staging first
- Monitor the GKE release notes for critical security patches
- Set up proper backup procedures before manual upgrades

This configuration gives you complete control over when maintenance occurs while protecting your critical business periods.
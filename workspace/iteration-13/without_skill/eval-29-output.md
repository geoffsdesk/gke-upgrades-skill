Here's the exact configuration for your GKE maintenance exclusions and policies:

## 1. Cluster Configuration with Maintenance Policies

```yaml
# cluster-config.yaml
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerCluster
metadata:
  name: your-cluster-name
  namespace: your-namespace
spec:
  location: your-region
  
  # Maintenance policy configuration
  maintenancePolicy:
    # Daily maintenance window (required)
    dailyMaintenanceWindow:
      startTime: "02:00"  # 2 AM in your timezone
    
    # Maintenance exclusions
    maintenanceExclusions:
      # June code freeze exclusion
      - name: "june-code-freeze"
        startTime: "2024-06-01T00:00:00Z"
        endTime: "2024-06-30T23:59:59Z"
        exclusionOptions:
          scope: "ALL_UPGRADES"
      
      # Black Friday/Cyber Monday exclusion
      - name: "black-friday-cyber-monday"
        startTime: "2024-11-20T00:00:00Z"
        endTime: "2024-12-03T23:59:59Z"
        exclusionOptions:
          scope: "ALL_UPGRADES"
    
    # Recurring maintenance exclusions for future years
    recurringWindow:
      # June exclusion (recurring)
      - recurrence: "FREQ=YEARLY;BYMONTH=6"
        window:
          startTime: "2025-06-01T00:00:00Z"
          endTime: "2025-06-30T23:59:59Z"
        maintenanceExclusionOptions:
          scope: "ALL_UPGRADES"
      
      # November exclusion (recurring)  
      - recurrence: "FREQ=YEARLY;BYMONTH=11"
        window:
          startTime: "2025-11-20T00:00:00Z"
          endTime: "2025-12-03T23:59:59Z"
        maintenanceExclusionOptions:
          scope: "ALL_UPGRADES"

  # Release channel configuration (REGULAR recommended for controlled updates)
  releaseChannel:
    channel: "REGULAR"
  
  # Node auto-upgrade disabled for manual control
  nodeConfig:
    oauthScopes:
      - "https://www.googleapis.com/auth/cloud-platform"
  
  # Disable automatic node upgrades
  nodePool:
    - name: default-pool
      management:
        autoUpgrade: false
        autoRepair: true  # Keep repair enabled for security
```

## 2. Terraform Configuration

```hcl
# main.tf
resource "google_container_cluster" "primary" {
  name     = "your-cluster-name"
  location = "your-region"

  # Release channel for controlled updates
  release_channel {
    channel = "REGULAR"
  }

  # Maintenance policy
  maintenance_policy {
    daily_maintenance_window {
      start_time = "02:00"
    }

    # June code freeze exclusion
    maintenance_exclusion {
      exclusion_name = "june-code-freeze"
      start_time     = "2024-06-01T00:00:00Z"
      end_time       = "2024-06-30T23:59:59Z"
      
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    # Black Friday/Cyber Monday exclusion
    maintenance_exclusion {
      exclusion_name = "black-friday-cyber-monday"
      start_time     = "2024-11-20T00:00:00Z"
      end_time       = "2024-12-03T23:59:59Z"
      
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    # Recurring June exclusion
    recurring_window {
      recurrence = "FREQ=YEARLY;BYMONTH=6"
      
      start_time = "2025-06-01T00:00:00Z"
      end_time   = "2025-06-30T23:59:59Z"
      
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    # Recurring November/December exclusion
    recurring_window {
      recurrence = "FREQ=YEARLY;BYMONTH=11"
      
      start_time = "2025-11-20T00:00:00Z"
      end_time   = "2025-12-03T23:59:59Z"
      
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }
  }

  # Default node pool with controlled upgrades
  node_pool {
    name = "default-pool"
    
    management {
      auto_upgrade = false
      auto_repair  = true
    }
    
    node_config {
      machine_type = "e2-medium"
      
      oauth_scopes = [
        "https://www.googleapis.com/auth/cloud-platform"
      ]
    }
  }
}
```

## 3. gcloud Commands for Existing Clusters

```bash
#!/bin/bash

# Set variables
CLUSTER_NAME="your-cluster-name"
REGION="your-region"
PROJECT_ID="your-project-id"

# Add June code freeze exclusion
gcloud container clusters update $CLUSTER_NAME \
  --region=$REGION \
  --project=$PROJECT_ID \
  --add-maintenance-exclusion-name="june-code-freeze" \
  --add-maintenance-exclusion-start="2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end="2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope="all-upgrades"

# Add Black Friday/Cyber Monday exclusion
gcloud container clusters update $CLUSTER_NAME \
  --region=$REGION \
  --project=$PROJECT_ID \
  --add-maintenance-exclusion-name="black-friday-cyber-monday" \
  --add-maintenance-exclusion-start="2024-11-20T00:00:00Z" \
  --add-maintenance-exclusion-end="2024-12-03T23:59:59Z" \
  --add-maintenance-exclusion-scope="all-upgrades"

# Disable auto-upgrade for all node pools
gcloud container node-pools update default-pool \
  --cluster=$CLUSTER_NAME \
  --region=$REGION \
  --project=$PROJECT_ID \
  --no-enable-autoupgrade

# Set maintenance window
gcloud container clusters update $CLUSTER_NAME \
  --region=$REGION \
  --project=$PROJECT_ID \
  --maintenance-window-start="02:00" \
  --maintenance-window-end="06:00" \
  --maintenance-window-recurrence="FREQ=DAILY"
```

## 4. Annual Maintenance Script

```bash
#!/bin/bash
# annual-maintenance-update.sh

CLUSTER_NAME="your-cluster-name"
REGION="your-region"
PROJECT_ID="your-project-id"
CURRENT_YEAR=$(date +%Y)
NEXT_YEAR=$((CURRENT_YEAR + 1))

# Add next year's exclusions
echo "Adding maintenance exclusions for $NEXT_YEAR..."

# June exclusion for next year
gcloud container clusters update $CLUSTER_NAME \
  --region=$REGION \
  --project=$PROJECT_ID \
  --add-maintenance-exclusion-name="june-code-freeze-$NEXT_YEAR" \
  --add-maintenance-exclusion-start="${NEXT_YEAR}-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end="${NEXT_YEAR}-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope="all-upgrades"

# Black Friday/Cyber Monday exclusion for next year
gcloud container clusters update $CLUSTER_NAME \
  --region=$REGION \
  --project=$PROJECT_ID \
  --add-maintenance-exclusion-name="black-friday-cyber-monday-$NEXT_YEAR" \
  --add-maintenance-exclusion-start="${NEXT_YEAR}-11-20T00:00:00Z" \
  --add-maintenance-exclusion-end="${NEXT_YEAR}-12-03T23:59:59Z" \
  --add-maintenance-exclusion-scope="all-upgrades"

echo "Maintenance exclusions for $NEXT_YEAR added successfully!"
```

## 5. Monitoring and Alerting

```yaml
# maintenance-alert-policy.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: gke-maintenance-alerts
spec:
  groups:
  - name: gke-maintenance
    rules:
    - alert: MaintenanceExclusionExpiring
      expr: |
        (gke_maintenance_exclusion_end_time - time()) < 86400
      for: 0m
      labels:
        severity: warning
      annotations:
        summary: "GKE maintenance exclusion expiring soon"
        description: "Maintenance exclusion {{ $labels.exclusion_name }} expires in less than 24 hours"
    
    - alert: PendingNodeUpgrades
      expr: |
        gke_node_pool_upgrade_available > 0
      for: 5m
      labels:
        severity: info
      annotations:
        summary: "GKE node pool upgrades available"
        description: "Node pool {{ $labels.node_pool }} has upgrades available"
```

## Key Configuration Points:

1. **ALL_UPGRADES scope** prevents both minor and patch version upgrades during exclusions
2. **Auto-upgrade disabled** on node pools requires manual approval for all upgrades
3. **REGULAR release channel** provides controlled update timing
4. **Recurring exclusions** automatically apply to future years
5. **Maintenance window** set to low-traffic hours (2-6 AM)

## Important Notes:

- Update the `CURRENT_YEAR` variables in scripts annually
- Test exclusions before critical periods
- Monitor for security patches that may need emergency application
- Keep auto-repair enabled for node health
- Review and manually approve all upgrades outside exclusion periods

This configuration ensures no automatic upgrades during your critical business periods while maintaining cluster security through controlled manual updates.
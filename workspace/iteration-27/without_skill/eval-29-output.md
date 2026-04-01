Here's the exact configuration for your GKE maintenance exclusions and policies:

## 1. Cluster Configuration with Maintenance Policy

```yaml
# cluster-maintenance-policy.yaml
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerCluster
metadata:
  name: your-cluster-name
  namespace: your-namespace
spec:
  location: us-central1-a
  maintenancePolicy:
    # Recurring maintenance window
    recurringWindow:
      recurrence: "FREQ=WEEKLY;BYDAY=SA"
      window:
        startTime: "2024-01-06T09:00:00Z"  # Saturday 9 AM UTC
        endTime: "2024-01-06T17:00:00Z"    # Saturday 5 PM UTC
    
    # Maintenance exclusions
    maintenanceExclusion:
    # June code freeze (entire month)
    - exclusionName: "quarterly-code-freeze-june"
      startTime: "2024-06-01T00:00:00Z"
      endTime: "2024-06-30T23:59:59Z"
      exclusionOptions:
        scope: "NO_UPGRADES"
    
    # Black Friday/Cyber Monday exclusion
    - exclusionName: "black-friday-cyber-monday"
      startTime: "2024-11-25T00:00:00Z"  # Week before Black Friday
      endTime: "2024-12-02T23:59:59Z"    # Week after Cyber Monday
      exclusionOptions:
        scope: "NO_UPGRADES"
    
    # Additional exclusions for subsequent years
    - exclusionName: "quarterly-code-freeze-june-2025"
      startTime: "2025-06-01T00:00:00Z"
      endTime: "2025-06-30T23:59:59Z"
      exclusionOptions:
        scope: "NO_UPGRADES"
    
    - exclusionName: "black-friday-cyber-monday-2025"
      startTime: "2025-11-24T00:00:00Z"
      endTime: "2025-12-01T23:59:59Z"
      exclusionOptions:
        scope: "NO_UPGRADES"
  
  # Release channel configuration for controlled upgrades
  releaseChannel:
    channel: "STABLE"  # Use STABLE instead of RAPID for more predictable updates
  
  # Node auto-upgrade and auto-repair settings
  nodeConfig:
    # Additional node configuration
  
  # Disable automatic minor version upgrades
  nodePool:
  - name: default-pool
    management:
      autoUpgrade: false  # Prevents automatic minor version upgrades
      autoRepair: true    # Keep auto-repair enabled for node health
```

## 2. Terraform Configuration

```hcl
# main.tf
resource "google_container_cluster" "primary" {
  name     = "your-cluster-name"
  location = "us-central1-a"

  # Release channel for controlled updates
  release_channel {
    channel = "STABLE"
  }

  # Maintenance policy
  maintenance_policy {
    # Maintenance window: Saturdays 9 AM - 5 PM UTC
    recurring_window {
      start_time = "2024-01-06T09:00:00Z"
      end_time   = "2024-01-06T17:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SA"
    }

    # June code freeze exclusion
    maintenance_exclusion {
      exclusion_name = "quarterly-code-freeze-june-2024"
      start_time     = "2024-06-01T00:00:00Z"
      end_time       = "2024-06-30T23:59:59Z"
      
      exclusion_options {
        scope = "NO_UPGRADES"
      }
    }

    # Black Friday/Cyber Monday exclusion
    maintenance_exclusion {
      exclusion_name = "black-friday-cyber-monday-2024"
      start_time     = "2024-11-25T00:00:00Z"
      end_time       = "2024-12-02T23:59:59Z"
      
      exclusion_options {
        scope = "NO_UPGRADES"
      }
    }

    # 2025 exclusions
    maintenance_exclusion {
      exclusion_name = "quarterly-code-freeze-june-2025"
      start_time     = "2025-06-01T00:00:00Z"
      end_time       = "2025-06-30T23:59:59Z"
      
      exclusion_options {
        scope = "NO_UPGRADES"
      }
    }

    maintenance_exclusion {
      exclusion_name = "black-friday-cyber-monday-2025"
      start_time     = "2025-11-24T00:00:00Z"
      end_time       = "2025-12-01T23:59:59Z"
      
      exclusion_options {
        scope = "NO_UPGRADES"
      }
    }
  }

  # Node pool with controlled upgrades
  node_pool {
    name = "default-pool"
    
    management {
      auto_upgrade = false  # Disable automatic minor version upgrades
      auto_repair  = true   # Keep auto-repair for node health
    }
    
    node_config {
      machine_type = "e2-medium"
      
      oauth_scopes = [
        "https://www.googleapis.com/auth/logging.write",
        "https://www.googleapis.com/auth/monitoring",
      ]
    }
  }
}
```

## 3. gcloud Commands

```bash
# Create cluster with maintenance policy
gcloud container clusters create your-cluster-name \
    --zone=us-central1-a \
    --release-channel=stable \
    --maintenance-window-start="2024-01-06T09:00:00Z" \
    --maintenance-window-end="2024-01-06T17:00:00Z" \
    --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SA" \
    --no-enable-autoupgrade

# Add maintenance exclusions
gcloud container clusters update your-cluster-name \
    --zone=us-central1-a \
    --add-maintenance-exclusion-name="quarterly-code-freeze-june-2024" \
    --add-maintenance-exclusion-start="2024-06-01T00:00:00Z" \
    --add-maintenance-exclusion-end="2024-06-30T23:59:59Z" \
    --add-maintenance-exclusion-scope="no-upgrades"

gcloud container clusters update your-cluster-name \
    --zone=us-central1-a \
    --add-maintenance-exclusion-name="black-friday-cyber-monday-2024" \
    --add-maintenance-exclusion-start="2024-11-25T00:00:00Z" \
    --add-maintenance-exclusion-end="2024-12-02T23:59:59Z" \
    --add-maintenance-exclusion-scope="no-upgrades"
```

## 4. Node Pool Configuration for Existing Clusters

```bash
# Disable auto-upgrade on existing node pools
gcloud container node-pools update default-pool \
    --cluster=your-cluster-name \
    --zone=us-central1-a \
    --no-enable-autoupgrade

# Verify settings
gcloud container clusters describe your-cluster-name \
    --zone=us-central1-a \
    --format="value(maintenancePolicy)"
```

## 5. Annual Maintenance Script

Create a script to add next year's exclusions:

```bash
#!/bin/bash
# update-maintenance-exclusions.sh

CLUSTER_NAME="your-cluster-name"
ZONE="us-central1-a"
YEAR=$(date -d "+1 year" +%Y)

# Add next year's June exclusion
gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --add-maintenance-exclusion-name="quarterly-code-freeze-june-$YEAR" \
    --add-maintenance-exclusion-start="$YEAR-06-01T00:00:00Z" \
    --add-maintenance-exclusion-end="$YEAR-06-30T23:59:59Z" \
    --add-maintenance-exclusion-scope="no-upgrades"

# Calculate Black Friday date for next year (fourth Thursday of November + 1 day)
BLACK_FRIDAY=$(python3 -c "
import datetime
year = $YEAR
nov = datetime.date(year, 11, 1)
first_thursday = nov + datetime.timedelta(days=(3-nov.weekday())%7)
fourth_thursday = first_thursday + datetime.timedelta(days=21)
black_friday = fourth_thursday + datetime.timedelta(days=1)
exclusion_start = black_friday - datetime.timedelta(days=7)
exclusion_end = black_friday + datetime.timedelta(days=7)
print(f'{exclusion_start.isoformat()}T00:00:00Z {exclusion_end.isoformat()}T23:59:59Z')
")

START_DATE=$(echo $BLACK_FRIDAY | cut -d' ' -f1)
END_DATE=$(echo $BLACK_FRIDAY | cut -d' ' -f2)

# Add next year's Black Friday exclusion
gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --add-maintenance-exclusion-name="black-friday-cyber-monday-$YEAR" \
    --add-maintenance-exclusion-start="$START_DATE" \
    --add-maintenance-exclusion-end="$END_DATE" \
    --add-maintenance-exclusion-scope="no-upgrades"
```

## Key Configuration Points:

1. **Maintenance Window**: Saturdays 9 AM - 5 PM UTC (adjust timezone as needed)
2. **Release Channel**: Set to STABLE for more predictable updates
3. **Auto-upgrade**: Disabled on node pools to require explicit approval
4. **Exclusion Scope**: `NO_UPGRADES` prevents all version upgrades during exclusion periods
5. **Auto-repair**: Kept enabled for node health while disabling auto-upgrade

This configuration ensures no automatic minor version upgrades occur, and maintenance is blocked during your critical business periods.
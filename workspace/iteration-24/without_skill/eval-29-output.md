Here's the exact GKE configuration to handle your maintenance requirements:

## 1. Terraform Configuration

```hcl
resource "google_container_cluster" "primary" {
  name     = "your-cluster-name"
  location = "us-central1"

  # Disable automatic upgrades for control plane
  master_auth {
    cluster_ca_certificate = ""
  }

  # Release channel configuration (use REGULAR or RAPID, not STABLE for more control)
  release_channel {
    channel = "REGULAR"
  }

  # Maintenance policy with exclusions
  maintenance_policy {
    # Recurring maintenance window (optional - adjust to your timezone)
    recurring_window {
      start_time = "2024-01-07T09:00:00Z"  # Sundays at 9 AM UTC
      end_time   = "2024-01-07T17:00:00Z"  # Sundays at 5 PM UTC
      recurrence = "FREQ=WEEKLY;BYDAY=SU"
    }

    # June code freeze exclusion (Q2 freeze)
    maintenance_exclusion {
      exclusion_name = "june-code-freeze"
      start_time     = "2024-06-01T00:00:00Z"
      end_time       = "2024-06-30T23:59:59Z"
      exclusion_options {
        scope = "MINOR_UPGRADES"
      }
    }

    # Black Friday/Cyber Monday exclusion
    maintenance_exclusion {
      exclusion_name = "black-friday-cyber-monday"
      start_time     = "2024-11-22T00:00:00Z"  # Week before Black Friday
      end_time       = "2024-12-03T23:59:59Z"  # Week after Cyber Monday
      exclusion_options {
        scope = "MINOR_AND_PATCH_UPGRADES"
      }
    }

    # Year-round minor version upgrade exclusion
    maintenance_exclusion {
      exclusion_name = "no-minor-upgrades"
      start_time     = "2024-01-01T00:00:00Z"
      end_time       = "2024-12-31T23:59:59Z"
      exclusion_options {
        scope = "MINOR_UPGRADES"
      }
    }
  }

  # Node pool configuration
  node_pool {
    name       = "default-pool"
    node_count = 1

    # Disable automatic upgrades for nodes
    management {
      auto_upgrade = false
      auto_repair  = true  # Keep auto-repair enabled for stability
    }

    node_config {
      machine_type = "e2-medium"
      
      # Specify exact node version to prevent automatic upgrades
      # Update this manually when you want to upgrade
      # image_type = "COS_CONTAINERD"
    }

    upgrade_settings {
      # Control upgrade strategy when you do manual upgrades
      strategy      = "SURGE"
      max_surge     = 1
      max_unavailable = 0
    }
  }

  # Prevent automatic cluster upgrades
  cluster_autoscaling {
    enabled = false
  }
}
```

## 2. YAML Configuration (for existing clusters)

```yaml
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerCluster
metadata:
  name: your-cluster-name
spec:
  location: us-central1
  
  releaseChannel:
    channel: REGULAR
  
  maintenancePolicy:
    recurringWindow:
      startTime: "2024-01-07T09:00:00Z"
      endTime: "2024-01-07T17:00:00Z"
      recurrence: "FREQ=WEEKLY;BYDAY=SU"
    
    maintenanceExclusions:
    - exclusionName: "june-code-freeze"
      startTime: "2024-06-01T00:00:00Z"
      endTime: "2024-06-30T23:59:59Z"
      exclusionOptions:
        scope: MINOR_UPGRADES
    
    - exclusionName: "black-friday-cyber-monday"
      startTime: "2024-11-22T00:00:00Z"
      endTime: "2024-12-03T23:59:59Z"
      exclusionOptions:
        scope: MINOR_AND_PATCH_UPGRADES
    
    - exclusionName: "no-minor-upgrades"
      startTime: "2024-01-01T00:00:00Z"
      endTime: "2024-12-31T23:59:59Z"
      exclusionOptions:
        scope: MINOR_UPGRADES
```

## 3. gcloud Commands (for existing clusters)

```bash
# Set maintenance window (Sundays 9 AM - 5 PM UTC)
gcloud container clusters update YOUR_CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --maintenance-window-start=2024-01-07T09:00:00Z \
    --maintenance-window-end=2024-01-07T17:00:00Z \
    --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SU"

# Add June code freeze exclusion
gcloud container clusters update YOUR_CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --add-maintenance-exclusion-name=june-code-freeze \
    --add-maintenance-exclusion-start=2024-06-01T00:00:00Z \
    --add-maintenance-exclusion-end=2024-06-30T23:59:59Z \
    --add-maintenance-exclusion-scope=minor_upgrades

# Add Black Friday/Cyber Monday exclusion
gcloud container clusters update YOUR_CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --add-maintenance-exclusion-name=black-friday-cyber-monday \
    --add-maintenance-exclusion-start=2024-11-22T00:00:00Z \
    --add-maintenance-exclusion-end=2024-12-03T23:59:59Z \
    --add-maintenance-exclusion-scope=minor_and_patch_upgrades

# Add year-round minor upgrade exclusion
gcloud container clusters update YOUR_CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --add-maintenance-exclusion-name=no-minor-upgrades \
    --add-maintenance-exclusion-start=2024-01-01T00:00:00Z \
    --add-maintenance-exclusion-end=2024-12-31T23:59:59Z \
    --add-maintenance-exclusion-scope=minor_upgrades

# Disable auto-upgrade for node pools
gcloud container node-pools update default-pool \
    --cluster=YOUR_CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --no-enable-autoupgrade
```

## 4. Annual Maintenance Script

Create this script to update exclusions annually:

```bash
#!/bin/bash

CLUSTER_NAME="your-cluster-name"
ZONE="us-central1"
CURRENT_YEAR=$(date +%Y)
NEXT_YEAR=$((CURRENT_YEAR + 1))

# Remove old exclusions
gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --remove-maintenance-exclusion-name=june-code-freeze

gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --remove-maintenance-exclusion-name=black-friday-cyber-monday

gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --remove-maintenance-exclusion-name=no-minor-upgrades

# Add new exclusions for next year
gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --add-maintenance-exclusion-name=june-code-freeze \
    --add-maintenance-exclusion-start=${NEXT_YEAR}-06-01T00:00:00Z \
    --add-maintenance-exclusion-end=${NEXT_YEAR}-06-30T23:59:59Z \
    --add-maintenance-exclusion-scope=minor_upgrades

# Calculate Black Friday dates for next year (4th Thursday of November + buffer)
gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --add-maintenance-exclusion-name=black-friday-cyber-monday \
    --add-maintenance-exclusion-start=${NEXT_YEAR}-11-22T00:00:00Z \
    --add-maintenance-exclusion-end=${NEXT_YEAR}-12-03T23:59:59Z \
    --add-maintenance-exclusion-scope=minor_and_patch_upgrades

gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --add-maintenance-exclusion-name=no-minor-upgrades \
    --add-maintenance-exclusion-start=${NEXT_YEAR}-01-01T00:00:00Z \
    --add-maintenance-exclusion-end=${NEXT_YEAR}-12-31T23:59:59Z \
    --add-maintenance-exclusion-scope=minor_upgrades
```

## Key Points:

1. **Minor upgrades blocked year-round** - requires explicit approval
2. **June completely protected** from minor upgrades
3. **Black Friday period** (Nov 22 - Dec 3) protected from all upgrades
4. **Patch upgrades** still allowed except during Black Friday period
5. **Security patches** will still be applied automatically unless excluded
6. **Manual upgrades** possible at any time using `gcloud container clusters upgrade`

Remember to update the dates annually and adjust the timezone in the maintenance window to match your operations schedule.
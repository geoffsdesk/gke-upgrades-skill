Here's the exact configuration for your GKE maintenance exclusions and upgrade settings:

## 1. Cluster Configuration with Maintenance Policy

```yaml
# cluster-maintenance-config.yaml
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerCluster
metadata:
  name: your-cluster-name
  namespace: your-project-namespace
spec:
  location: your-region-or-zone
  
  # Disable automatic minor version upgrades
  releaseChannel:
    channel: "REGULAR"  # or "RAPID" or "STABLE"
  
  # Node auto-upgrade settings
  nodeConfig:
    oauthScopes:
      - "https://www.googleapis.com/auth/cloud-platform"
  
  # Maintenance policy with exclusions
  maintenancePolicy:
    # Daily maintenance window (when maintenance CAN happen)
    dailyMaintenanceWindow:
      startTime: "02:00"  # 2 AM in your cluster's timezone
    
    # Maintenance exclusions
    maintenanceExclusion:
      - exclusionName: "june-code-freeze"
        startTime: "2024-06-01T00:00:00Z"
        endTime: "2024-06-30T23:59:59Z"
        exclusionOptions:
          scope: "NO_UPGRADES"
      
      - exclusionName: "black-friday-cyber-monday"
        startTime: "2024-11-25T00:00:00Z"  # Adjust dates as needed
        endTime: "2024-12-02T23:59:59Z"
        exclusionOptions:
          scope: "NO_UPGRADES"
  
  # Disable automatic minor version upgrades
  nodePool:
    - name: default-pool
      management:
        autoUpgrade: false  # Prevent automatic minor version upgrades
        autoRepair: true    # Keep auto-repair enabled for security
```

## 2. Terraform Configuration

```hcl
# main.tf
resource "google_container_cluster" "primary" {
  name     = "your-cluster-name"
  location = "your-region"

  # Disable automatic upgrades for minor versions
  release_channel {
    channel = "REGULAR"
  }

  # Remove default node pool
  remove_default_node_pool = true
  initial_node_count       = 1

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
        scope = "NO_UPGRADES"
      }
    }

    # Black Friday/Cyber Monday exclusion
    maintenance_exclusion {
      exclusion_name = "black-friday-cyber-monday"
      start_time     = "2024-11-25T00:00:00Z"
      end_time       = "2024-12-02T23:59:59Z"
      
      exclusion_options {
        scope = "NO_UPGRADES"
      }
    }
  }
}

# Separate node pool with controlled upgrades
resource "google_container_node_pool" "primary_nodes" {
  name       = "main-node-pool"
  location   = "your-region"
  cluster    = google_container_cluster.primary.name
  node_count = 1

  # Disable automatic minor version upgrades
  management {
    auto_repair  = true
    auto_upgrade = false  # This prevents automatic minor version upgrades
  }

  node_config {
    preemptible  = false
    machine_type = "e2-medium"

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]
  }

  # Upgrade settings
  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
  }
}
```

## 3. gcloud Commands for Existing Clusters

```bash
# Update maintenance policy for existing cluster
gcloud container clusters update your-cluster-name \
    --zone=your-zone \
    --maintenance-window-start="02:00" \
    --maintenance-window-end="06:00" \
    --maintenance-window-recurrence="FREQ=DAILY"

# Add June code freeze exclusion
gcloud container clusters update your-cluster-name \
    --zone=your-zone \
    --add-maintenance-exclusion-name="june-code-freeze" \
    --add-maintenance-exclusion-start="2024-06-01T00:00:00Z" \
    --add-maintenance-exclusion-end="2024-06-30T23:59:59Z" \
    --add-maintenance-exclusion-scope="NO_UPGRADES"

# Add Black Friday/Cyber Monday exclusion
gcloud container clusters update your-cluster-name \
    --zone=your-zone \
    --add-maintenance-exclusion-name="black-friday-cyber-monday" \
    --add-maintenance-exclusion-start="2024-11-25T00:00:00Z" \
    --add-maintenance-exclusion-end="2024-12-02T23:59:59Z" \
    --add-maintenance-exclusion-scope="NO_UPGRADES"

# Disable auto-upgrade for node pools
gcloud container node-pools update default-pool \
    --cluster=your-cluster-name \
    --zone=your-zone \
    --no-enable-autoupgrade
```

## 4. Annual Maintenance Exclusion Script

Create a script to automatically set up exclusions for future years:

```bash
#!/bin/bash
# update-annual-exclusions.sh

CLUSTER_NAME="your-cluster-name"
ZONE="your-zone"
YEAR=$(date +%Y)

# Remove old exclusions (if they exist)
gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --remove-maintenance-exclusion-name="june-code-freeze" || true

gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --remove-maintenance-exclusion-name="black-friday-cyber-monday" || true

# Add current year exclusions
# June code freeze
gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --add-maintenance-exclusion-name="june-code-freeze" \
    --add-maintenance-exclusion-start="${YEAR}-06-01T00:00:00Z" \
    --add-maintenance-exclusion-end="${YEAR}-06-30T23:59:59Z" \
    --add-maintenance-exclusion-scope="NO_UPGRADES"

# Black Friday/Cyber Monday (adjust dates based on actual dates)
# This example uses last Thursday of November + 1 week
gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --add-maintenance-exclusion-name="black-friday-cyber-monday" \
    --add-maintenance-exclusion-start="${YEAR}-11-25T00:00:00Z" \
    --add-maintenance-exclusion-end="${YEAR}-12-02T23:59:59Z" \
    --add-maintenance-exclusion-scope="NO_UPGRADES"

echo "Updated maintenance exclusions for year $YEAR"
```

## 5. Verification Commands

```bash
# Check current maintenance policy
gcloud container clusters describe your-cluster-name \
    --zone=your-zone \
    --format="yaml(maintenancePolicy)"

# Check node pool auto-upgrade status
gcloud container node-pools describe default-pool \
    --cluster=your-cluster-name \
    --zone=your-zone \
    --format="yaml(management)"

# List all maintenance exclusions
gcloud container clusters describe your-cluster-name \
    --zone=your-zone \
    --format="table(maintenancePolicy.window.maintenanceExclusions[].exclusionName,maintenancePolicy.window.maintenanceExclusions[].startTime,maintenancePolicy.window.maintenanceExclusions[].endTime)"
```

## Key Points:

1. **Minor Version Upgrades**: Setting `auto_upgrade: false` on node pools prevents automatic minor version upgrades
2. **Maintenance Exclusions**: `NO_UPGRADES` scope blocks all upgrades during specified periods
3. **Security Updates**: Auto-repair remains enabled for critical security patches
4. **Manual Control**: You'll need to manually trigger upgrades outside exclusion periods
5. **Annual Updates**: Run the script annually to update exclusion dates

This configuration ensures no automatic upgrades during your critical periods while maintaining security through auto-repair functionality.
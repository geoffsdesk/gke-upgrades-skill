Here's the exact GKE maintenance configuration to handle your requirements:

## 1. Terraform Configuration

```hcl
resource "google_container_cluster" "primary" {
  name     = "your-cluster-name"
  location = "us-central1"
  
  # Disable automatic minor version upgrades
  node_version = "1.27.8-gke.1067004"  # Pin to specific version
  min_master_version = "1.27.8-gke.1067004"
  
  # Enable maintenance policy
  maintenance_policy {
    # Define maintenance window (adjust timezone as needed)
    daily_maintenance_window {
      start_time = "02:00"  # 2 AM in cluster's timezone
    }
    
    # Maintenance exclusions
    maintenance_exclusion {
      exclusion_name = "june-code-freeze"
      start_time     = "2024-06-01T00:00:00Z"
      end_time       = "2024-06-30T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }
    
    maintenance_exclusion {
      exclusion_name = "black-friday-cyber-monday"
      start_time     = "2024-11-15T00:00:00Z"
      end_time       = "2024-12-05T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }
    
    # Add recurring exclusions for future years
    maintenance_exclusion {
      exclusion_name = "june-code-freeze-2025"
      start_time     = "2025-06-01T00:00:00Z"
      end_time       = "2025-06-30T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }
    
    maintenance_exclusion {
      exclusion_name = "black-friday-cyber-monday-2025"
      start_time     = "2025-11-15T00:00:00Z"
      end_time       = "2025-12-05T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }
  }
  
  # Disable automatic upgrades at cluster level
  cluster_autoscaling {
    enabled = false
  }
  
  # Configure release channel to REGULAR but disable auto-upgrades
  release_channel {
    channel = "REGULAR"
  }
}

# Node pool configuration with disabled auto-upgrades
resource "google_container_node_pool" "primary_nodes" {
  name       = "main-pool"
  location   = "us-central1"
  cluster    = google_container_cluster.primary.name
  
  # Pin node version
  version = "1.27.8-gke.1067004"
  
  # Disable automatic upgrades and repairs during exclusion periods
  management {
    auto_repair  = true
    auto_upgrade = false  # Critical: Prevents automatic minor version upgrades
  }
  
  node_config {
    preemptible  = false
    machine_type = "e2-medium"
    
    oauth_scopes = [
      "https://www.googleapis.com/auth/logging.write",
      "https://www.googleapis.com/auth/monitoring",
    ]
  }
}
```

## 2. gcloud CLI Configuration

```bash
#!/bin/bash

# Set variables
CLUSTER_NAME="your-cluster-name"
ZONE="us-central1"
PROJECT_ID="your-project-id"

# Create maintenance exclusions
gcloud container clusters update $CLUSTER_NAME \
  --zone=$ZONE \
  --project=$PROJECT_ID \
  --maintenance-window-start="02:00" \
  --maintenance-window-end="06:00" \
  --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SA,SU"

# Add June code freeze exclusion (2024)
gcloud container clusters update $CLUSTER_NAME \
  --zone=$ZONE \
  --project=$PROJECT_ID \
  --add-maintenance-exclusion-end="2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-name="june-code-freeze-2024" \
  --add-maintenance-exclusion-start="2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-scope="ALL_UPGRADES"

# Add Black Friday/Cyber Monday exclusion (2024)
gcloud container clusters update $CLUSTER_NAME \
  --zone=$ZONE \
  --project=$PROJECT_ID \
  --add-maintenance-exclusion-end="2024-12-05T23:59:59Z" \
  --add-maintenance-exclusion-name="black-friday-cyber-monday-2024" \
  --add-maintenance-exclusion-start="2024-11-15T00:00:00Z" \
  --add-maintenance-exclusion-scope="ALL_UPGRADES"

# Disable automatic node upgrades
gcloud container node-pools update main-pool \
  --cluster=$CLUSTER_NAME \
  --zone=$ZONE \
  --project=$PROJECT_ID \
  --no-enable-autoupgrade
```

## 3. YAML Configuration for GitOps

```yaml
# maintenance-policy.yaml
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerCluster
metadata:
  name: your-cluster-name
  namespace: your-namespace
spec:
  location: us-central1
  maintenancePolicy:
    dailyMaintenanceWindow:
      startTime: "02:00"
    maintenanceExclusions:
    - exclusionName: "june-code-freeze-2024"
      startTime: "2024-06-01T00:00:00Z"
      endTime: "2024-06-30T23:59:59Z"
      exclusionOptions:
        scope: "ALL_UPGRADES"
    - exclusionName: "black-friday-cyber-monday-2024" 
      startTime: "2024-11-15T00:00:00Z"
      endTime: "2024-12-05T23:59:59Z"
      exclusionOptions:
        scope: "ALL_UPGRADES"
    - exclusionName: "june-code-freeze-2025"
      startTime: "2025-06-01T00:00:00Z" 
      endTime: "2025-06-30T23:59:59Z"
      exclusionOptions:
        scope: "ALL_UPGRADES"
    - exclusionName: "black-friday-cyber-monday-2025"
      startTime: "2025-11-15T00:00:00Z"
      endTime: "2025-12-05T23:59:59Z"
      exclusionOptions:
        scope: "ALL_UPGRADES"
  releaseChannel:
    channel: "REGULAR"
  nodeConfig:
    management:
      autoRepair: true
      autoUpgrade: false
```

## 4. Monitoring Script

Create this script to manage yearly exclusions:

```bash
#!/bin/bash
# maintenance-exclusion-manager.sh

CLUSTER_NAME="your-cluster-name"
ZONE="us-central1" 
PROJECT_ID="your-project-id"
CURRENT_YEAR=$(date +%Y)
NEXT_YEAR=$((CURRENT_YEAR + 1))

# Function to add yearly exclusions
add_yearly_exclusions() {
  local year=$1
  
  echo "Adding maintenance exclusions for year: $year"
  
  # June code freeze
  gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --add-maintenance-exclusion-end="${year}-06-30T23:59:59Z" \
    --add-maintenance-exclusion-name="june-code-freeze-${year}" \
    --add-maintenance-exclusion-start="${year}-06-01T00:00:00Z" \
    --add-maintenance-exclusion-scope="ALL_UPGRADES"
    
  # Black Friday/Cyber Monday
  gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --add-maintenance-exclusion-end="${year}-12-05T23:59:59Z" \
    --add-maintenance-exclusion-name="black-friday-cyber-monday-${year}" \
    --add-maintenance-exclusion-start="${year}-11-15T00:00:00Z" \
    --add-maintenance-exclusion-scope="ALL_UPGRADES"
}

# Add exclusions for next year (run this annually)
add_yearly_exclusions $NEXT_YEAR

# Verify exclusions
echo "Current maintenance exclusions:"
gcloud container clusters describe $CLUSTER_NAME \
  --zone=$ZONE \
  --project=$PROJECT_ID \
  --format="value(maintenancePolicy.maintenanceExclusions[].exclusionName,maintenancePolicy.maintenanceExclusions[].startTime,maintenancePolicy.maintenanceExclusions[].endTime)"
```

## Key Points:

1. **No Automatic Minor Upgrades**: `auto_upgrade = false` prevents any automatic minor version upgrades
2. **Maintenance Exclusions**: Block ALL upgrades during June and November 15 - December 5
3. **Manual Control**: You must explicitly upgrade versions using `gcloud` or Terraform
4. **Recurring Setup**: Add exclusions for future years annually

## Manual Upgrade Process:

When you're ready to upgrade:

```bash
# Check available versions
gcloud container get-server-config --zone=us-central1

# Upgrade master
gcloud container clusters upgrade $CLUSTER_NAME --zone=$ZONE --master --cluster-version=NEW_VERSION

# Upgrade nodes  
gcloud container clusters upgrade $CLUSTER_NAME --zone=$ZONE --node-pool=main-pool
```

This configuration ensures complete control over when upgrades happen while protecting your critical business periods.
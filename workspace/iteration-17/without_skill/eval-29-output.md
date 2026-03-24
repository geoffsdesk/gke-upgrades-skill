I'll provide you with the exact GKE maintenance exclusion configuration for your requirements. Here are multiple approaches:

## 1. Terraform Configuration

```hcl
resource "google_container_cluster" "primary" {
  name     = "your-cluster-name"
  location = "us-central1"
  
  # Disable automatic minor version upgrades
  node_version = "1.28.3-gke.1286000"  # Pin to specific version
  min_master_version = "1.28.3-gke.1286000"
  
  # Release channel - use RAPID, REGULAR, or STABLE based on your needs
  release_channel {
    channel = "REGULAR"
  }

  # Maintenance policy with exclusions
  maintenance_policy {
    # Quarterly code freeze in June (entire month)
    maintenance_exclusion {
      exclusion_name = "june-code-freeze"
      start_time     = "2024-06-01T00:00:00Z"
      end_time       = "2024-07-01T00:00:00Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }
    
    # Black Friday/Cyber Monday exclusion (extended period)
    maintenance_exclusion {
      exclusion_name = "black-friday-cyber-monday"
      start_time     = "2024-11-15T00:00:00Z"
      end_time       = "2024-12-03T00:00:00Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    # Recurring maintenance window (optional - limits when updates can occur)
    daily_maintenance_window {
      start_time = "03:00"  # 3 AM in cluster's timezone
    }
    
    # Alternative: Use recurring window instead of daily
    # recurring_window {
    #   start_time = "2024-01-01T03:00:00Z"
    #   end_time   = "2024-01-01T07:00:00Z"
    #   recurrence = "FREQ=WEEKLY;BYDAY=SU"  # Sundays 3-7 AM
    # }
  }

  # Node pool configuration with version pinning
  node_pool {
    name       = "default-pool"
    node_count = 1
    
    # Pin node version
    version = "1.28.3-gke.1286000"

    management {
      auto_repair  = true
      auto_upgrade = false  # Disable automatic upgrades
    }

    node_config {
      machine_type = "e2-medium"
      oauth_scopes = [
        "https://www.googleapis.com/auth/cloud-platform"
      ]
    }
  }

  # Remove default node pool
  remove_default_node_pool = true
  initial_node_count       = 1
}

# Separate node pool resource for more control
resource "google_container_node_pool" "primary_nodes" {
  name       = "primary-node-pool"
  location   = "us-central1"
  cluster    = google_container_cluster.primary.name
  node_count = 3

  # Pin node version
  version = "1.28.3-gke.1286000"

  management {
    auto_repair  = true
    auto_upgrade = false  # Explicitly disable auto-upgrades
  }

  node_config {
    preemptible  = false
    machine_type = "e2-standard-2"

    oauth_scopes = [
      "https://www.googleapis.com/auth/logging.write",
      "https://www.googleapis.com/auth/monitoring",
      "https://www.googleapis.com/auth/cloud-platform"
    ]
  }
}
```

## 2. gcloud Commands

```bash
# Create cluster with maintenance exclusions
gcloud container clusters create your-cluster-name \
    --zone=us-central1-a \
    --release-channel=regular \
    --cluster-version=1.28.3-gke.1286000 \
    --maintenance-window-start=2024-01-01T03:00:00Z \
    --maintenance-window-end=2024-01-01T07:00:00Z \
    --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SU" \
    --enable-autorepair \
    --no-enable-autoupgrade

# Add June code freeze exclusion
gcloud container clusters update your-cluster-name \
    --zone=us-central1-a \
    --add-maintenance-exclusion-end=2024-07-01T00:00:00Z \
    --add-maintenance-exclusion-name=june-code-freeze \
    --add-maintenance-exclusion-scope=all-upgrades \
    --add-maintenance-exclusion-start=2024-06-01T00:00:00Z

# Add Black Friday/Cyber Monday exclusion
gcloud container clusters update your-cluster-name \
    --zone=us-central1-a \
    --add-maintenance-exclusion-end=2024-12-03T00:00:00Z \
    --add-maintenance-exclusion-name=black-friday-cyber-monday \
    --add-maintenance-exclusion-scope=all-upgrades \
    --add-maintenance-exclusion-start=2024-11-15T00:00:00Z

# Disable auto-upgrade on node pools
gcloud container node-pools update default-pool \
    --cluster=your-cluster-name \
    --zone=us-central1-a \
    --no-enable-autoupgrade
```

## 3. YAML Configuration (for GitOps)

```yaml
# config-connector-cluster.yaml
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerCluster
metadata:
  name: your-cluster-name
  namespace: your-project-id
spec:
  location: us-central1-a
  releaseChannel:
    channel: REGULAR
  initialNodeCount: 1
  removeDefaultNodePool: true
  minMasterVersion: "1.28.3-gke.1286000"
  
  maintenancePolicy:
    dailyMaintenanceWindow:
      startTime: "03:00"
    
    maintenanceExclusions:
    - exclusionName: "june-code-freeze"
      startTime: "2024-06-01T00:00:00Z"
      endTime: "2024-07-01T00:00:00Z"
      exclusionOptions:
        scope: "ALL_UPGRADES"
    
    - exclusionName: "black-friday-cyber-monday"
      startTime: "2024-11-15T00:00:00Z"
      endTime: "2024-12-03T00:00:00Z"
      exclusionOptions:
        scope: "ALL_UPGRADES"

---
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerNodePool
metadata:
  name: primary-node-pool
  namespace: your-project-id
spec:
  clusterRef:
    name: your-cluster-name
  location: us-central1-a
  nodeCount: 3
  version: "1.28.3-gke.1286000"
  
  management:
    autoRepair: true
    autoUpgrade: false
  
  nodeConfig:
    machineType: e2-standard-2
    oauthScopes:
    - "https://www.googleapis.com/auth/cloud-platform"
```

## 4. Automation Script for Annual Updates

```bash
#!/bin/bash
# update-maintenance-exclusions.sh

CLUSTER_NAME="your-cluster-name"
ZONE="us-central1-a"
CURRENT_YEAR=$(date +%Y)
NEXT_YEAR=$((CURRENT_YEAR + 1))

# Remove old exclusions
gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --remove-maintenance-exclusion-name=june-code-freeze \
    --remove-maintenance-exclusion-name=black-friday-cyber-monday

# Add new exclusions for current year
gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --add-maintenance-exclusion-end=${CURRENT_YEAR}-07-01T00:00:00Z \
    --add-maintenance-exclusion-name=june-code-freeze \
    --add-maintenance-exclusion-scope=all-upgrades \
    --add-maintenance-exclusion-start=${CURRENT_YEAR}-06-01T00:00:00Z

gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --add-maintenance-exclusion-end=${CURRENT_YEAR}-12-03T00:00:00Z \
    --add-maintenance-exclusion-name=black-friday-cyber-monday \
    --add-maintenance-exclusion-scope=all-upgrades \
    --add-maintenance-exclusion-start=${CURRENT_YEAR}-11-15T00:00:00Z

echo "Maintenance exclusions updated for year $CURRENT_YEAR"
```

## Key Points:

1. **Auto-upgrade disabled**: Set `auto_upgrade = false` on node pools and pin specific versions
2. **Exclusion scopes**: Use `ALL_UPGRADES` to block both master and node upgrades
3. **Recurring maintenance**: Schedule maintenance windows during low-traffic periods
4. **Version pinning**: Explicitly set cluster and node versions to prevent automatic updates
5. **Annual updates**: Create a script to update exclusion dates yearly

## Verification Commands:

```bash
# Check current maintenance policy
gcloud container clusters describe your-cluster-name --zone=us-central1-a --format="value(maintenancePolicy)"

# List all maintenance exclusions
gcloud container clusters describe your-cluster-name --zone=us-central1-a --format="table(maintenancePolicy.maintenanceExclusions[].exclusionName,maintenancePolicy.maintenanceExclusions[].startTime,maintenancePolicy.maintenanceExclusions[].endTime)"

# Check node pool auto-upgrade status
gcloud container node-pools describe default-pool --cluster=your-cluster-name --zone=us-central1-a --format="value(management.autoUpgrade)"
```

This configuration ensures that no automatic upgrades occur during your critical business periods and requires explicit approval for all version changes.
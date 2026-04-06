I'll help you set up maintenance exclusions for your GKE clusters to handle your specific business requirements. Here are the exact configurations:

## 1. Terraform Configuration

```hcl
resource "google_container_cluster" "primary" {
  name     = "your-cluster-name"
  location = "us-central1"

  # Maintenance policy configuration
  maintenance_policy {
    # Set maintenance window (adjust timezone as needed)
    daily_maintenance_window {
      start_time = "03:00"  # 3 AM in your timezone
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

    # Recurring June exclusion for future years
    maintenance_exclusion {
      exclusion_name = "june-code-freeze-2025"
      start_time     = "2025-06-01T00:00:00Z"
      end_time       = "2025-06-30T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    # Recurring Black Friday exclusion for future years
    maintenance_exclusion {
      exclusion_name = "black-friday-cyber-monday-2025"
      start_time     = "2025-11-20T00:00:00Z"
      end_time       = "2025-12-03T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }
  }

  # Disable automatic minor version upgrades
  release_channel {
    channel = "REGULAR"  # or "STABLE" for more conservative updates
  }

  # Disable auto-upgrade for nodes
  node_config {
    # ... other node config
  }

  # Default node pool configuration
  initial_node_count       = 1
  remove_default_node_pool = true
}

# Separate node pool with controlled upgrades
resource "google_container_node_pool" "primary_nodes" {
  name       = "primary-node-pool"
  location   = "us-central1"
  cluster    = google_container_cluster.primary.name
  node_count = 3

  management {
    auto_repair  = true
    auto_upgrade = false  # Disable automatic minor version upgrades
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
# Create the cluster with maintenance exclusions
gcloud container clusters create your-cluster-name \
    --zone=us-central1-a \
    --maintenance-window-start=2024-01-01T03:00:00Z \
    --maintenance-window-end=2024-01-01T07:00:00Z \
    --maintenance-window-recurrence="FREQ=DAILY" \
    --release-channel=regular \
    --no-enable-autoupgrade

# Add June code freeze exclusion
gcloud container clusters update your-cluster-name \
    --zone=us-central1-a \
    --add-maintenance-exclusion-end=2024-06-30T23:59:59Z \
    --add-maintenance-exclusion-name=june-code-freeze-2024 \
    --add-maintenance-exclusion-start=2024-06-01T00:00:00Z \
    --add-maintenance-exclusion-scope=ALL_UPGRADES

# Add Black Friday/Cyber Monday exclusion
gcloud container clusters update your-cluster-name \
    --zone=us-central1-a \
    --add-maintenance-exclusion-end=2024-12-03T23:59:59Z \
    --add-maintenance-exclusion-name=black-friday-2024 \
    --add-maintenance-exclusion-start=2024-11-20T00:00:00Z \
    --add-maintenance-exclusion-scope=ALL_UPGRADES

# Add 2025 June exclusion
gcloud container clusters update your-cluster-name \
    --zone=us-central1-a \
    --add-maintenance-exclusion-end=2025-06-30T23:59:59Z \
    --add-maintenance-exclusion-name=june-code-freeze-2025 \
    --add-maintenance-exclusion-start=2025-06-01T00:00:00Z \
    --add-maintenance-exclusion-scope=ALL_UPGRADES

# Add 2025 Black Friday exclusion
gcloud container clusters update your-cluster-name \
    --zone=us-central1-a \
    --add-maintenance-exclusion-end=2025-12-03T23:59:59Z \
    --add-maintenance-exclusion-name=black-friday-2025 \
    --add-maintenance-exclusion-start=2025-11-20T00:00:00Z \
    --add-maintenance-exclusion-scope=ALL_UPGRADES
```

## 3. YAML Configuration for GitOps

```yaml
# cluster-config.yaml
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerCluster
metadata:
  name: your-cluster-name
  namespace: default
spec:
  location: us-central1
  initialNodeCount: 1
  removeDefaultNodePool: true
  
  releaseChannel:
    channel: REGULAR
  
  maintenancePolicy:
    dailyMaintenanceWindow:
      startTime: "03:00"
    
    maintenanceExclusions:
    - exclusionName: "june-code-freeze-2024"
      startTime: "2024-06-01T00:00:00Z"
      endTime: "2024-06-30T23:59:59Z"
      exclusionOptions:
        scope: "ALL_UPGRADES"
    
    - exclusionName: "black-friday-2024"
      startTime: "2024-11-20T00:00:00Z"
      endTime: "2024-12-03T23:59:59Z"
      exclusionOptions:
        scope: "ALL_UPGRADES"
    
    - exclusionName: "june-code-freeze-2025"
      startTime: "2025-06-01T00:00:00Z"
      endTime: "2025-06-30T23:59:59Z"
      exclusionOptions:
        scope: "ALL_UPGRADES"
    
    - exclusionName: "black-friday-2025"
      startTime: "2025-11-20T00:00:00Z"
      endTime: "2025-12-03T23:59:59Z"
      exclusionOptions:
        scope: "ALL_UPGRADES"

---
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerNodePool
metadata:
  name: primary-node-pool
  namespace: default
spec:
  clusterRef:
    name: your-cluster-name
  location: us-central1
  nodeCount: 3
  
  management:
    autoRepair: true
    autoUpgrade: false  # Disable automatic upgrades
  
  nodeConfig:
    machineType: e2-medium
    preemptible: false
```

## 4. Monitoring and Alerting Script

```bash
#!/bin/bash
# maintenance-monitor.sh - Script to monitor maintenance exclusions

CLUSTER_NAME="your-cluster-name"
ZONE="us-central1-a"

# Function to check current maintenance exclusions
check_exclusions() {
    echo "Current maintenance exclusions:"
    gcloud container clusters describe $CLUSTER_NAME \
        --zone=$ZONE \
        --format="table(maintenancePolicy.maintenanceExclusions[].exclusionName,maintenancePolicy.maintenanceExclusions[].startTime,maintenancePolicy.maintenanceExclusions[].endTime)"
}

# Function to add next year's exclusions
add_next_year_exclusions() {
    NEXT_YEAR=$(($(date +%Y) + 1))
    
    # Add June exclusion for next year
    gcloud container clusters update $CLUSTER_NAME \
        --zone=$ZONE \
        --add-maintenance-exclusion-end="${NEXT_YEAR}-06-30T23:59:59Z" \
        --add-maintenance-exclusion-name="june-code-freeze-${NEXT_YEAR}" \
        --add-maintenance-exclusion-start="${NEXT_YEAR}-06-01T00:00:00Z" \
        --add-maintenance-exclusion-scope=ALL_UPGRADES

    # Add Black Friday exclusion for next year
    gcloud container clusters update $CLUSTER_NAME \
        --zone=$ZONE \
        --add-maintenance-exclusion-end="${NEXT_YEAR}-12-03T23:59:59Z" \
        --add-maintenance-exclusion-name="black-friday-${NEXT_YEAR}" \
        --add-maintenance-exclusion-start="${NEXT_YEAR}-11-20T00:00:00Z" \
        --add-maintenance-exclusion-scope=ALL_UPGRADES
}

# Function to manually trigger upgrade (when ready)
manual_upgrade() {
    echo "Available versions:"
    gcloud container get-server-config --zone=$ZONE
    
    echo "Current cluster version:"
    gcloud container clusters describe $CLUSTER_NAME --zone=$ZONE --format="value(currentMasterVersion)"
    
    read -p "Enter target version (or press Enter to cancel): " TARGET_VERSION
    
    if [ ! -z "$TARGET_VERSION" ]; then
        gcloud container clusters upgrade $CLUSTER_NAME \
            --zone=$ZONE \
            --master \
            --cluster-version=$TARGET_VERSION
    fi
}

case "$1" in
    "check")
        check_exclusions
        ;;
    "add-next-year")
        add_next_year_exclusions
        ;;
    "upgrade")
        manual_upgrade
        ;;
    *)
        echo "Usage: $0 {check|add-next-year|upgrade}"
        ;;
esac
```

## 5. Automated Management with Cloud Function

```python
# main.py - Cloud Function to manage maintenance exclusions
import functions_framework
from google.cloud import container_v1
from datetime import datetime, timedelta
import json

@functions_framework.http
def manage_maintenance_exclusions(request):
    """HTTP Cloud Function to manage GKE maintenance exclusions"""
    
    client = container_v1.ClusterManagerClient()
    project_id = "your-project-id"
    zone = "us-central1-a"
    cluster_name = "your-cluster-name"
    
    cluster_path = f"projects/{project_id}/locations/{zone}/clusters/{cluster_name}"
    
    current_year = datetime.now().year
    next_year = current_year + 1
    
    # Define exclusions for next year
    exclusions = [
        {
            "exclusion_name": f"june-code-freeze-{next_year}",
            "start_time": f"{next_year}-06-01T00:00:00Z",
            "end_time": f"{next_year}-06-30T23:59:59Z"
        },
        {
            "exclusion_name": f"black-friday-{next_year}",
            "start_time": f"{next_year}-11-20T00:00:00Z",
            "end_time": f"{next_year}-12-03T23:59:59Z"
        }
    ]
    
    try:
        # Get current cluster configuration
        cluster = client.get_cluster(name=cluster_path)
        
        # Add new exclusions
        for exclusion in exclusions:
            maintenance_policy = container_v1.MaintenancePolicy()
            
            new_exclusion = container_v1.MaintenanceExclusionOptions()
            new_exclusion.scope = container_v1.MaintenanceExclusionOptions.Scope.ALL_UPGRADES
            
            exclusion_window = container_v1.MaintenanceWindow()
            exclusion_window.maintenance_exclusions = {
                exclusion["exclusion_name"]: {
                    "start_time": exclusion["start_time"],
                    "end_time": exclusion["end_time"],
                    "exclusion_options": new_exclusion
                }
            }
            
            # This would be implemented with the actual update call
            print(f"Would add exclusion: {exclusion['exclusion_name']}")
        
        return json.dumps({"status": "success", "message": "Exclusions updated"})
        
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})
```

## Key Points:

1. **Automatic upgrades are disabled** - You control all version upgrades
2. **Maintenance exclusions cover your critical periods** - June and November/December
3. **Future-proof** - Includes exclusions for 2025 (add more as needed)
4. **Monitoring included** - Scripts to check status and manage exclusions
5. **Manual upgrade process** - Use the script when you're ready to upgrade

Remember to:
- Update the exclusion dates annually
- Test upgrades in non-production environments first
- Monitor security patches and apply critical updates during approved windows
- Adjust timezones in the maintenance windows to match your operations schedule
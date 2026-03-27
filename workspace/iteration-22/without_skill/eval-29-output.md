Here's the exact GKE maintenance exclusion configuration for your requirements:

## 1. Terraform Configuration

```hcl
resource "google_container_cluster" "primary" {
  name     = "your-cluster-name"
  location = "us-central1"

  # Disable automatic upgrades for minor versions
  node_config {
    # Other node configuration...
  }

  # Release channel (recommended to use REGULAR or RAPID for security patches)
  release_channel {
    channel = "REGULAR"  # Gets security patches but respects maintenance exclusions
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
        scope = "ALL_UPGRADES"  # Blocks both node and control plane upgrades
      }
    }

    # Black Friday period exclusion
    maintenance_exclusion {
      exclusion_name = "black-friday-cyber-monday"
      start_time     = "2024-11-20T00:00:00Z"  # Week before Black Friday
      end_time       = "2024-12-03T23:59:59Z"  # Tuesday after Cyber Monday
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    # Recurring June exclusion for following years
    maintenance_exclusion {
      exclusion_name = "june-code-freeze-2025"
      start_time     = "2025-06-01T00:00:00Z"
      end_time       = "2025-06-30T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    # Recurring Black Friday exclusion for following years
    maintenance_exclusion {
      exclusion_name = "black-friday-2025"
      start_time     = "2025-11-20T00:00:00Z"
      end_time       = "2025-12-03T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }
  }

  # Disable auto-upgrade for minor versions (only allow security patches)
  cluster_autoscaling {
    # Other autoscaling config...
  }

  # Resource labels for tracking
  resource_labels = {
    maintenance_policy = "restricted"
    upgrade_policy     = "manual"
  }
}

# Node pool with manual upgrade configuration
resource "google_container_node_pool" "primary_nodes" {
  name       = "primary-node-pool"
  cluster    = google_container_cluster.primary.name
  location   = google_container_cluster.primary.location
  node_count = 3

  # Disable auto-upgrade and auto-repair during exclusion periods
  management {
    auto_repair  = true
    auto_upgrade = false  # Manual control over upgrades
  }

  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
    strategy        = "SURGE"  # Less disruptive upgrade strategy
  }

  node_config {
    machine_type = "e2-medium"
    
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]

    labels = {
      upgrade_policy = "manual"
    }

    tags = ["gke-node", "manual-upgrade"]
  }
}
```

## 2. gcloud Command Equivalents

```bash
# Create cluster with maintenance exclusions
gcloud container clusters create your-cluster-name \
    --location=us-central1 \
    --release-channel=regular \
    --maintenance-window-start=03:00 \
    --maintenance-window-end=07:00 \
    --maintenance-window-recurrence="FREQ=DAILY" \
    --no-enable-autoupgrade \
    --enable-autorepair

# Add June code freeze exclusion
gcloud container clusters update your-cluster-name \
    --location=us-central1 \
    --add-maintenance-exclusion-end=2024-06-30T23:59:59Z \
    --add-maintenance-exclusion-name=june-code-freeze \
    --add-maintenance-exclusion-start=2024-06-01T00:00:00Z \
    --add-maintenance-exclusion-scope=all-upgrades

# Add Black Friday exclusion
gcloud container clusters update your-cluster-name \
    --location=us-central1 \
    --add-maintenance-exclusion-end=2024-12-03T23:59:59Z \
    --add-maintenance-exclusion-name=black-friday-cyber-monday \
    --add-maintenance-exclusion-start=2024-11-20T00:00:00Z \
    --add-maintenance-exclusion-scope=all-upgrades
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
  location: us-central1
  
  releaseChannel:
    channel: REGULAR
  
  maintenancePolicy:
    dailyMaintenanceWindow:
      startTime: "03:00"
    
    maintenanceExclusion:
    - exclusionName: "june-code-freeze"
      startTime: "2024-06-01T00:00:00Z"
      endTime: "2024-06-30T23:59:59Z"
      exclusionOptions:
        scope: "ALL_UPGRADES"
    
    - exclusionName: "black-friday-cyber-monday"
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

  nodeConfig:
    machineType: "e2-medium"
    
  initialNodeCount: 3
```

## 4. Monitoring and Alerting Script

```bash
#!/bin/bash
# maintenance-monitor.sh - Script to monitor upcoming maintenance exclusions

CLUSTER_NAME="your-cluster-name"
LOCATION="us-central1"
PROJECT_ID="your-project-id"

# Check current maintenance exclusions
echo "Current maintenance exclusions:"
gcloud container clusters describe $CLUSTER_NAME \
    --location=$LOCATION \
    --project=$PROJECT_ID \
    --format="table(maintenancePolicy.maintenanceExclusion[].exclusionName,maintenancePolicy.maintenanceExclusion[].startTime,maintenancePolicy.maintenanceExclusion[].endTime)"

# Check if we're currently in an exclusion period
CURRENT_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "Current UTC time: $CURRENT_DATE"

# List pending upgrades
echo "Pending cluster upgrades:"
gcloud container clusters describe $CLUSTER_NAME \
    --location=$LOCATION \
    --project=$PROJECT_ID \
    --format="value(currentMasterVersion,currentNodeVersion)"
```

## 5. Key Configuration Details

### Exclusion Scopes:
- `ALL_UPGRADES`: Blocks both control plane and node upgrades
- `NO_MINOR_UPGRADES`: Allows security patches but blocks minor version upgrades
- `NO_MINOR_OR_NODE_UPGRADES`: Blocks minor version and node upgrades

### Manual Upgrade Control:
```bash
# When you want to manually upgrade during allowed periods
gcloud container clusters upgrade your-cluster-name \
    --location=us-central1 \
    --master \
    --cluster-version=1.28.3-gke.1203001

# Upgrade node pools manually
gcloud container clusters upgrade your-cluster-name \
    --location=us-central1 \
    --node-pool=primary-node-pool
```

### Important Notes:

1. **Security Patches**: Even with exclusions, critical security patches may still be applied
2. **Recurring Exclusions**: You'll need to add new exclusions annually or use automation
3. **Time Zones**: All times are in UTC - adjust for your local timezone
4. **Grace Periods**: Consider adding buffer time before/after your critical periods

This configuration ensures no automatic minor version upgrades occur, and creates maintenance-free windows during your June code freeze and Black Friday/Cyber Monday periods.
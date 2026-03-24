Here's the exact configuration for your GKE maintenance exclusions and upgrade policies:

## 1. Terraform Configuration

```hcl
resource "google_container_cluster" "main" {
  name     = "production-cluster"
  location = "us-central1"
  
  # Disable automatic node upgrades - require explicit approval
  node_config {
    # ... other node config
  }
  
  # Control plane maintenance policy
  maintenance_policy {
    # Recurring maintenance window (outside business hours)
    recurring_window {
      start_time = "2024-01-07T02:00:00Z"  # Sunday 2 AM UTC
      end_time   = "2024-01-07T06:00:00Z"  # Sunday 6 AM UTC
      recurrence = "FREQ=WEEKLY;BYDAY=SU"
    }
    
    # June quarterly code freeze exclusion
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
      start_time     = "2024-11-20T00:00:00Z"  # Week before through week after
      end_time       = "2024-12-05T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }
    
    # Repeat exclusions for future years
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
      start_time     = "2025-11-20T00:00:00Z"
      end_time       = "2025-12-05T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }
  }
  
  # Disable automatic minor version upgrades
  release_channel {
    channel = "REGULAR"  # or "STABLE" for more conservative updates
  }
  
  # Node pool with manual upgrade control
  node_pool {
    name       = "primary-pool"
    node_count = 3
    
    management {
      auto_repair  = true
      auto_upgrade = false  # Disable automatic node upgrades
    }
    
    upgrade_settings {
      max_surge       = 1
      max_unavailable = 0
      strategy        = "SURGE"  # Blue-green style upgrades
    }
    
    node_config {
      machine_type = "e2-standard-4"
      # ... other node config
    }
  }
}
```

## 2. gcloud Command Configuration

```bash
# Set maintenance window (Sundays 2-6 AM UTC)
gcloud container clusters update production-cluster \
    --location=us-central1 \
    --maintenance-window-start="2024-01-07T02:00:00Z" \
    --maintenance-window-end="2024-01-07T06:00:00Z" \
    --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SU"

# Add June code freeze exclusion
gcloud container clusters update production-cluster \
    --location=us-central1 \
    --add-maintenance-exclusion-end="2024-06-30T23:59:59Z" \
    --add-maintenance-exclusion-name="june-code-freeze" \
    --add-maintenance-exclusion-start="2024-06-01T00:00:00Z" \
    --add-maintenance-exclusion-scope="ALL_UPGRADES"

# Add Black Friday/Cyber Monday exclusion
gcloud container clusters update production-cluster \
    --location=us-central1 \
    --add-maintenance-exclusion-end="2024-12-05T23:59:59Z" \
    --add-maintenance-exclusion-name="black-friday-cyber-monday" \
    --add-maintenance-exclusion-start="2024-11-20T00:00:00Z" \
    --add-maintenance-exclusion-scope="ALL_UPGRADES"

# Disable automatic node upgrades
gcloud container node-pools update primary-pool \
    --cluster=production-cluster \
    --location=us-central1 \
    --no-enable-autoupgrade
```

## 3. YAML Manifest (if using Config Connector)

```yaml
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerCluster
metadata:
  name: production-cluster
  namespace: config-control
spec:
  location: us-central1
  
  maintenancePolicy:
    recurringWindow:
      startTime: "2024-01-07T02:00:00Z"
      endTime: "2024-01-07T06:00:00Z"
      recurrence: "FREQ=WEEKLY;BYDAY=SU"
    
    maintenanceExclusions:
    - exclusionName: "june-code-freeze"
      startTime: "2024-06-01T00:00:00Z"
      endTime: "2024-06-30T23:59:59Z"
      exclusionOptions:
        scope: "ALL_UPGRADES"
    
    - exclusionName: "black-friday-cyber-monday"
      startTime: "2024-11-20T00:00:00Z"
      endTime: "2024-12-05T23:59:59Z"
      exclusionOptions:
        scope: "ALL_UPGRADES"
  
  releaseChannel:
    channel: "REGULAR"
  
  nodePools:
  - name: primary-pool
    initialNodeCount: 3
    management:
      autoRepair: true
      autoUpgrade: false
    upgradeSettings:
      maxSurge: 1
      maxUnavailable: 0
      strategy: "SURGE"
```

## 4. Automation Script for Annual Exclusions

```bash
#!/bin/bash
# update-maintenance-exclusions.sh

CLUSTER_NAME="production-cluster"
LOCATION="us-central1"
CURRENT_YEAR=$(date +%Y)
NEXT_YEAR=$((CURRENT_YEAR + 1))

# Function to add yearly exclusions
add_yearly_exclusions() {
    local year=$1
    
    # June code freeze
    gcloud container clusters update $CLUSTER_NAME \
        --location=$LOCATION \
        --add-maintenance-exclusion-end="${year}-06-30T23:59:59Z" \
        --add-maintenance-exclusion-name="june-code-freeze-${year}" \
        --add-maintenance-exclusion-start="${year}-06-01T00:00:00Z" \
        --add-maintenance-exclusion-scope="ALL_UPGRADES"
    
    # Black Friday/Cyber Monday
    gcloud container clusters update $CLUSTER_NAME \
        --location=$LOCATION \
        --add-maintenance-exclusion-end="${year}-12-05T23:59:59Z" \
        --add-maintenance-exclusion-name="black-friday-cyber-monday-${year}" \
        --add-maintenance-exclusion-start="${year}-11-20T00:00:00Z" \
        --add-maintenance-exclusion-scope="ALL_UPGRADES"
}

# Add exclusions for next year
add_yearly_exclusions $NEXT_YEAR

echo "Added maintenance exclusions for $NEXT_YEAR"
```

## 5. Manual Upgrade Process

When you're ready to perform upgrades:

```bash
# Check available versions
gcloud container get-server-config --location=us-central1

# Upgrade control plane first
gcloud container clusters upgrade production-cluster \
    --location=us-central1 \
    --master \
    --cluster-version=1.28.3-gke.1203001

# Then upgrade node pools
gcloud container clusters upgrade production-cluster \
    --location=us-central1 \
    --node-pool=primary-pool \
    --cluster-version=1.28.3-gke.1203001
```

## 6. Monitoring and Alerts

```bash
# Check current maintenance exclusions
gcloud container clusters describe production-cluster \
    --location=us-central1 \
    --format="value(maintenancePolicy.maintenanceExclusions[].exclusionName,maintenancePolicy.maintenanceExclusions[].startTime,maintenancePolicy.maintenanceExclusions[].endTime)"

# Set up alerting for pending upgrades
gcloud alpha monitoring policies create --policy-from-file=maintenance-alerts.yaml
```

## Key Configuration Points:

1. **Maintenance Window**: Sundays 2-6 AM UTC (adjust timezone as needed)
2. **June Exclusion**: Entire month blocked for quarterly freeze
3. **November Exclusion**: Extended period covering Black Friday rush
4. **Auto-upgrade**: Disabled for both control plane minor versions and nodes
5. **Upgrade Strategy**: Surge strategy for zero-downtime node upgrades

This configuration ensures no automatic upgrades during your critical periods while maintaining security patches during allowed maintenance windows.
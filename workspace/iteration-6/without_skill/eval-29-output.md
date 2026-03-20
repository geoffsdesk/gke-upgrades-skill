I'll help you set up maintenance exclusions for your GKE clusters to handle your specific requirements. Here's the exact configuration:

## 1. Terraform Configuration

```hcl
resource "google_container_cluster" "primary" {
  name     = "your-cluster-name"
  location = "us-central1"
  
  # Disable automatic minor version upgrades
  release_channel {
    channel = "REGULAR"  # or "RAPID", "STABLE"
  }
  
  # Node auto-upgrade disabled for manual control
  node_config {
    # Other node configuration...
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
    
    # Block minor version upgrades year-round
    maintenance_exclusion {
      exclusion_name = "block-minor-upgrades-2024"
      start_time     = "2024-01-01T00:00:00Z"
      end_time       = "2024-12-31T23:59:59Z"
      exclusion_options {
        scope = "MINOR_UPGRADES"
      }
    }
  }
  
  # Explicitly disable node auto-upgrade
  node_pool {
    name       = "default-pool"
    node_count = 3
    
    management {
      auto_repair  = true
      auto_upgrade = false  # Disable automatic upgrades
    }
    
    node_config {
      machine_type = "e2-medium"
      # Other node configuration...
    }
  }
}
```

## 2. gcloud CLI Configuration

```bash
# Create the cluster with maintenance policy
gcloud container clusters create your-cluster-name \
  --zone=us-central1-a \
  --maintenance-window-start=2024-01-01T03:00:00Z \
  --maintenance-window-end=2024-01-01T07:00:00Z \
  --maintenance-window-recurrence="FREQ=DAILY" \
  --no-enable-autoupgrade

# Add June code freeze exclusion
gcloud container clusters update your-cluster-name \
  --zone=us-central1-a \
  --add-maintenance-exclusion-end=2024-06-30T23:59:59Z \
  --add-maintenance-exclusion-name=june-code-freeze \
  --add-maintenance-exclusion-start=2024-06-01T00:00:00Z \
  --add-maintenance-exclusion-scope=all-upgrades

# Add Black Friday/Cyber Monday exclusion
gcloud container clusters update your-cluster-name \
  --zone=us-central1-a \
  --add-maintenance-exclusion-end=2024-12-03T23:59:59Z \
  --add-maintenance-exclusion-name=black-friday-cyber-monday \
  --add-maintenance-exclusion-start=2024-11-20T00:00:00Z \
  --add-maintenance-exclusion-scope=all-upgrades

# Add year-round minor upgrade block
gcloud container clusters update your-cluster-name \
  --zone=us-central1-a \
  --add-maintenance-exclusion-end=2024-12-31T23:59:59Z \
  --add-maintenance-exclusion-name=block-minor-upgrades-2024 \
  --add-maintenance-exclusion-start=2024-01-01T00:00:00Z \
  --add-maintenance-exclusion-scope=minor-upgrades
```

## 3. YAML Configuration (for GitOps)

```yaml
# config-connector-cluster.yaml
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerCluster
metadata:
  name: your-cluster-name
spec:
  location: us-central1
  releaseChannel:
    channel: REGULAR
  maintenancePolicy:
    dailyMaintenanceWindow:
      startTime: "03:00"
    maintenanceExclusions:
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
    - exclusionName: "block-minor-upgrades-2024"
      startTime: "2024-01-01T00:00:00Z"
      endTime: "2024-12-31T23:59:59Z"
      exclusionOptions:
        scope: "MINOR_UPGRADES"
  nodePool:
  - name: default-pool
    initialNodeCount: 3
    management:
      autoRepair: true
      autoUpgrade: false
```

## 4. Automation Script for Annual Updates

```bash
#!/bin/bash
# update-maintenance-exclusions.sh

CLUSTER_NAME="your-cluster-name"
ZONE="us-central1-a"
CURRENT_YEAR=$(date +%Y)
NEXT_YEAR=$((CURRENT_YEAR + 1))

# Remove old year's exclusions
gcloud container clusters update $CLUSTER_NAME \
  --zone=$ZONE \
  --remove-maintenance-exclusion-name=block-minor-upgrades-$CURRENT_YEAR

gcloud container clusters update $CLUSTER_NAME \
  --zone=$ZONE \
  --remove-maintenance-exclusion-name=june-code-freeze-$CURRENT_YEAR \
  2>/dev/null || true

gcloud container clusters update $CLUSTER_NAME \
  --zone=$ZONE \
  --remove-maintenance-exclusion-name=black-friday-cyber-monday-$CURRENT_YEAR \
  2>/dev/null || true

# Add next year's exclusions
gcloud container clusters update $CLUSTER_NAME \
  --zone=$ZONE \
  --add-maintenance-exclusion-end=${NEXT_YEAR}-06-30T23:59:59Z \
  --add-maintenance-exclusion-name=june-code-freeze-$NEXT_YEAR \
  --add-maintenance-exclusion-start=${NEXT_YEAR}-06-01T00:00:00Z \
  --add-maintenance-exclusion-scope=all-upgrades

gcloud container clusters update $CLUSTER_NAME \
  --zone=$ZONE \
  --add-maintenance-exclusion-end=${NEXT_YEAR}-12-03T23:59:59Z \
  --add-maintenance-exclusion-name=black-friday-cyber-monday-$NEXT_YEAR \
  --add-maintenance-exclusion-start=${NEXT_YEAR}-11-20T00:00:00Z \
  --add-maintenance-exclusion-scope=all-upgrades

gcloud container clusters update $CLUSTER_NAME \
  --zone=$ZONE \
  --add-maintenance-exclusion-end=${NEXT_YEAR}-12-31T23:59:59Z \
  --add-maintenance-exclusion-name=block-minor-upgrades-$NEXT_YEAR \
  --add-maintenance-exclusion-start=${NEXT_YEAR}-01-01T00:00:00Z \
  --add-maintenance-exclusion-scope=minor-upgrades
```

## 5. Monitoring and Alerting

```bash
# Check current maintenance exclusions
gcloud container clusters describe your-cluster-name \
  --zone=us-central1-a \
  --format="value(maintenancePolicy.window.maintenanceExclusions[])"

# List upcoming maintenance events
gcloud container operations list \
  --filter="operationType=UPGRADE_MASTER OR operationType=UPGRADE_NODES" \
  --format="table(name,operationType,status,startTime,endTime)"
```

## Key Points:

1. **June Code Freeze**: Complete maintenance blackout for the entire month
2. **Black Friday/Cyber Monday**: Extended exclusion from Nov 20 to Dec 3
3. **Minor Version Control**: Year-round blocking of automatic minor upgrades
4. **Manual Control**: All node pools have `auto_upgrade = false`
5. **Security Updates**: Only security patches and node repairs are allowed during exclusions

## Important Notes:

- Update the years in exclusions annually
- Security patches may still be applied during exclusions
- Test this configuration in a development environment first
- Monitor GKE release notes for critical security updates that might require emergency upgrades
- Consider setting up alerts for when exclusions are about to expire

This configuration gives you complete control over when upgrades happen while maintaining security through automatic repairs.
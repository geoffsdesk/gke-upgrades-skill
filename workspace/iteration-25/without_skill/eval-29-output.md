Here's the exact configuration for your GKE maintenance exclusions and upgrade policies:

## 1. Cluster Configuration with Maintenance Policy

```yaml
# cluster-maintenance-policy.yaml
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerCluster
metadata:
  name: your-cluster-name
  namespace: your-namespace
spec:
  location: us-central1-a  # Replace with your zone/region
  
  # Release channel (recommended for controlled upgrades)
  releaseChannel:
    channel: "REGULAR"  # or "RAPID" or "STABLE"
  
  # Maintenance policy with exclusions
  maintenancePolicy:
    dailyMaintenanceWindow:
      startTime: "02:00"  # 2 AM in cluster's timezone
    
    # Maintenance exclusions
    maintenanceExclusions:
      - name: "q2-code-freeze"
        startTime: "2024-06-01T00:00:00Z"
        endTime: "2024-06-30T23:59:59Z"
        exclusionOptions:
          scope: "NO_UPGRADES"  # Blocks all upgrades
      
      - name: "black-friday-period"
        startTime: "2024-11-25T00:00:00Z"
        endTime: "2024-12-02T23:59:59Z"
        exclusionOptions:
          scope: "NO_UPGRADES"
      
      # Add recurring exclusions for future years
      - name: "q2-code-freeze-2025"
        startTime: "2025-06-01T00:00:00Z"
        endTime: "2025-06-30T23:59:59Z"
        exclusionOptions:
          scope: "NO_UPGRADES"
      
      - name: "black-friday-period-2025"
        startTime: "2025-11-24T00:00:00Z"
        endTime: "2025-12-01T23:59:59Z"
        exclusionOptions:
          scope: "NO_UPGRADES"

  # Node pool auto-upgrade disabled for manual control
  nodePool:
    - name: default-pool
      management:
        autoUpgrade: false  # Disable automatic node upgrades
        autoRepair: true    # Keep auto-repair enabled for stability
```

## 2. Terraform Configuration

```hcl
# main.tf
resource "google_container_cluster" "primary" {
  name     = "your-cluster-name"
  location = "us-central1-a"

  # Release channel for controlled updates
  release_channel {
    channel = "REGULAR"
  }

  # Maintenance policy
  maintenance_policy {
    daily_maintenance_window {
      start_time = "02:00"
    }

    # Quarterly code freeze exclusions
    maintenance_exclusion {
      exclusion_name = "q2-code-freeze-2024"
      start_time     = "2024-06-01T00:00:00Z"
      end_time       = "2024-06-30T23:59:59Z"
      
      exclusion_options {
        scope = "NO_UPGRADES"
      }
    }

    maintenance_exclusion {
      exclusion_name = "q2-code-freeze-2025"
      start_time     = "2025-06-01T00:00:00Z"
      end_time       = "2025-06-30T23:59:59Z"
      
      exclusion_options {
        scope = "NO_UPGRADES"
      }
    }

    # Black Friday/Cyber Monday exclusions
    maintenance_exclusion {
      exclusion_name = "black-friday-2024"
      start_time     = "2024-11-25T00:00:00Z"
      end_time       = "2024-12-02T23:59:59Z"
      
      exclusion_options {
        scope = "NO_UPGRADES"
      }
    }

    maintenance_exclusion {
      exclusion_name = "black-friday-2025"
      start_time     = "2025-11-24T00:00:00Z"
      end_time       = "2025-12-01T23:59:59Z"
      
      exclusion_options {
        scope = "NO_UPGRADES"
      }
    }
  }

  # Disable automatic upgrades on node pools
  node_pool {
    name = "default-pool"
    
    management {
      auto_upgrade = false
      auto_repair  = true
    }
    
    # Other node pool configuration...
  }
}
```

## 3. gcloud CLI Commands

```bash
# Create maintenance exclusions
gcloud container clusters update your-cluster-name \
    --zone=us-central1-a \
    --add-maintenance-exclusion-name=q2-code-freeze-2024 \
    --add-maintenance-exclusion-start=2024-06-01T00:00:00Z \
    --add-maintenance-exclusion-end=2024-06-30T23:59:59Z \
    --add-maintenance-exclusion-scope=no-upgrades

gcloud container clusters update your-cluster-name \
    --zone=us-central1-a \
    --add-maintenance-exclusion-name=black-friday-2024 \
    --add-maintenance-exclusion-start=2024-11-25T00:00:00Z \
    --add-maintenance-exclusion-end=2024-12-02T23:59:59Z \
    --add-maintenance-exclusion-scope=no-upgrades

# Set daily maintenance window
gcloud container clusters update your-cluster-name \
    --zone=us-central1-a \
    --maintenance-window-start=02:00 \
    --maintenance-window-end=06:00

# Disable node auto-upgrade
gcloud container node-pools update default-pool \
    --cluster=your-cluster-name \
    --zone=us-central1-a \
    --no-enable-autoupgrade
```

## 4. Automation Script for Annual Exclusions

```bash
#!/bin/bash
# update-maintenance-exclusions.sh

CLUSTER_NAME="your-cluster-name"
ZONE="us-central1-a"
CURRENT_YEAR=$(date +%Y)
NEXT_YEAR=$((CURRENT_YEAR + 1))

# Add next year's Q2 code freeze
gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --add-maintenance-exclusion-name=q2-code-freeze-$NEXT_YEAR \
    --add-maintenance-exclusion-start=${NEXT_YEAR}-06-01T00:00:00Z \
    --add-maintenance-exclusion-end=${NEXT_YEAR}-06-30T23:59:59Z \
    --add-maintenance-exclusion-scope=no-upgrades

# Calculate Black Friday date for next year (4th Thursday of November)
# Black Friday exclusion period
gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --add-maintenance-exclusion-name=black-friday-$NEXT_YEAR \
    --add-maintenance-exclusion-start=${NEXT_YEAR}-11-24T00:00:00Z \
    --add-maintenance-exclusion-end=${NEXT_YEAR}-12-01T23:59:59Z \
    --add-maintenance-exclusion-scope=no-upgrades

echo "Maintenance exclusions updated for $NEXT_YEAR"
```

## 5. Monitoring and Alerts

```yaml
# maintenance-alert-policy.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: gke-maintenance-alerts
spec:
  groups:
  - name: gke.maintenance
    rules:
    - alert: GKEUpgradeAvailable
      expr: |
        gke_cluster_upgrade_available == 1
      for: 24h
      labels:
        severity: info
      annotations:
        summary: "GKE cluster upgrade available"
        description: "Cluster {{ $labels.cluster_name }} has upgrades available. Manual intervention required."
    
    - alert: GKEMaintenanceExclusionExpiring
      expr: |
        (gke_maintenance_exclusion_end_time - time()) < 604800  # 7 days
      labels:
        severity: warning
      annotations:
        summary: "GKE maintenance exclusion expiring soon"
        description: "Maintenance exclusion {{ $labels.exclusion_name }} expires in less than 7 days"
```

## 6. Manual Upgrade Process

```bash
#!/bin/bash
# manual-upgrade.sh

CLUSTER_NAME="your-cluster-name"
ZONE="us-central1-a"

# Check available versions
echo "Available master versions:"
gcloud container get-server-config --zone=$ZONE --format="value(validMasterVersions[0:5])"

echo "Available node versions:"
gcloud container get-server-config --zone=$ZONE --format="value(validNodeVersions[0:5])"

# Upgrade master first
echo "Upgrading master to specified version..."
gcloud container clusters upgrade $CLUSTER_NAME \
    --zone=$ZONE \
    --master \
    --cluster-version=1.28.3-gke.1203001  # Replace with desired version

# Wait for master upgrade completion
echo "Waiting for master upgrade to complete..."
gcloud container operations wait $(gcloud container operations list --filter="targetId:$CLUSTER_NAME AND operationType:UPGRADE_MASTER" --format="value(name)" | head -1) --zone=$ZONE

# Upgrade nodes
echo "Upgrading node pools..."
gcloud container clusters upgrade $CLUSTER_NAME \
    --zone=$ZONE \
    --node-pool=default-pool

echo "Upgrade completed successfully!"
```

## Key Points:

1. **Maintenance Exclusions**: Set for June (Q2 freeze) and Black Friday week
2. **Auto-upgrade Disabled**: Prevents automatic minor version upgrades
3. **Release Channel**: Use REGULAR for balanced stability and features
4. **Maintenance Window**: Set to 2-6 AM to minimize impact
5. **Auto-repair Enabled**: Keeps nodes healthy while preventing upgrades

Remember to:
- Update exclusion dates annually
- Monitor for available upgrades during non-exclusion periods
- Test upgrades in staging environments first
- Set up alerts for when exclusions are about to expire
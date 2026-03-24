Here's the exact GKE maintenance exclusion configuration for your requirements:

## 1. Terraform Configuration

```hcl
resource "google_container_cluster" "primary" {
  name     = "your-cluster-name"
  location = "us-central1"
  
  # Disable automatic upgrades for control plane and nodes
  release_channel {
    channel = "REGULAR"  # or "STABLE"/"RAPID" based on your preference
  }
  
  # Control plane maintenance policy
  maintenance_policy {
    # Quarterly code freeze in June
    recurring_window {
      start_time = "2024-06-01T00:00:00Z"
      end_time   = "2024-06-30T23:59:59Z"
      recurrence = "FREQ=YEARLY;BYMONTH=6"
    }
    
    # Black Friday/Cyber Monday exclusion (Nov 20-30)
    recurring_window {
      start_time = "2024-11-20T00:00:00Z"
      end_time   = "2024-11-30T23:59:59Z"
      recurrence = "FREQ=YEARLY;BYMONTH=11;BYMONTHDAY=20,21,22,23,24,25,26,27,28,29,30"
    }
    
    # Daily maintenance window (outside exclusions)
    daily_maintenance_window {
      start_time = "03:00"  # 3 AM in cluster's timezone
    }
  }
  
  # Disable automatic node upgrades
  node_config {
    # Node configuration
  }
}

resource "google_container_node_pool" "primary_nodes" {
  cluster  = google_container_cluster.primary.name
  location = "us-central1"
  
  # Disable automatic upgrades and repairs during exclusions
  management {
    auto_upgrade = false  # Prevents minor version upgrades
    auto_repair  = true   # Keep auto-repair enabled for stability
  }
  
  upgrade_settings {
    strategy      = "SURGE"
    max_surge     = 1
    max_unavailable = 0
  }
}
```

## 2. gcloud CLI Configuration

```bash
# Set maintenance exclusions for June code freeze
gcloud container clusters update your-cluster-name \
  --location=us-central1 \
  --add-maintenance-exclusion-name=june-code-freeze \
  --add-maintenance-exclusion-start=2024-06-01T00:00:00Z \
  --add-maintenance-exclusion-end=2024-06-30T23:59:59Z

# Set maintenance exclusion for Black Friday/Cyber Monday
gcloud container clusters update your-cluster-name \
  --location=us-central1 \
  --add-maintenance-exclusion-name=black-friday-cyber-monday \
  --add-maintenance-exclusion-start=2024-11-20T00:00:00Z \
  --add-maintenance-exclusion-end=2024-11-30T23:59:59Z

# Disable automatic node upgrades
gcloud container node-pools update default-pool \
  --cluster=your-cluster-name \
  --location=us-central1 \
  --no-enable-autoupgrade

# Set daily maintenance window
gcloud container clusters update your-cluster-name \
  --location=us-central1 \
  --maintenance-window-start=2024-01-01T03:00:00Z \
  --maintenance-window-end=2024-01-01T07:00:00Z \
  --maintenance-window-recurrence="FREQ=DAILY"
```

## 3. YAML Configuration (for GitOps)

```yaml
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
    recurringWindow:
      - startTime: "2024-06-01T00:00:00Z"
        endTime: "2024-06-30T23:59:59Z"
        recurrence: "FREQ=YEARLY;BYMONTH=6"
      - startTime: "2024-11-20T00:00:00Z"
        endTime: "2024-11-30T23:59:59Z"
        recurrence: "FREQ=YEARLY;BYMONTH=11;BYMONTHDAY=20,21,22,23,24,25,26,27,28,29,30"
    dailyMaintenanceWindow:
      startTime: "03:00"
---
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerNodePool
metadata:
  name: primary-nodes
  namespace: your-project-id
spec:
  clusterRef:
    name: your-cluster-name
  location: us-central1
  management:
    autoUpgrade: false
    autoRepair: true
  upgradeSettings:
    strategy: SURGE
    maxSurge: 1
    maxUnavailable: 0
```

## 4. Additional Recommendations

### Manual Upgrade Script
```bash
#!/bin/bash
# manual-upgrade.sh - For controlled upgrades outside exclusion periods

CLUSTER_NAME="your-cluster-name"
LOCATION="us-central1"

# Check available versions
echo "Available master versions:"
gcloud container get-server-config --location=$LOCATION --format="value(validMasterVersions)"

# Upgrade master (only when you approve)
echo "Current master version:"
gcloud container clusters describe $CLUSTER_NAME --location=$LOCATION --format="value(currentMasterVersion)"

# Uncomment to upgrade master
# gcloud container clusters upgrade $CLUSTER_NAME --location=$LOCATION --master --cluster-version=1.28.3-gke.1286000

# Upgrade nodes (only when you approve)
echo "Current node versions:"
gcloud container node-pools list --cluster=$CLUSTER_NAME --location=$LOCATION --format="table(name,version)"

# Uncomment to upgrade specific node pool
# gcloud container clusters upgrade $CLUSTER_NAME --location=$LOCATION --node-pool=default-pool
```

### Monitoring Script
```bash
#!/bin/bash
# check-maintenance-schedule.sh - Monitor upcoming maintenance

CLUSTER_NAME="your-cluster-name"
LOCATION="us-central1"

# Check maintenance exclusions
gcloud container clusters describe $CLUSTER_NAME \
  --location=$LOCATION \
  --format="table(maintenancePolicy.window.recurringWindow.window.startTime,maintenancePolicy.window.recurringWindow.window.endTime)"

# Check for pending upgrades
gcloud container clusters describe $CLUSTER_NAME \
  --location=$LOCATION \
  --format="value(currentMasterVersion,currentNodeVersion)"
```

## Key Configuration Points:

1. **June Code Freeze**: Complete maintenance exclusion for entire month
2. **Black Friday/Cyber Monday**: Exclusion from Nov 20-30 annually
3. **No Auto Minor Upgrades**: `auto_upgrade = false` prevents automatic version upgrades
4. **Manual Control**: All upgrades require explicit approval and execution
5. **Auto-repair Enabled**: Keeps nodes healthy while preventing version changes
6. **Maintenance Window**: 3-7 AM daily window for security patches (outside exclusions)

This configuration ensures maintenance only happens when you explicitly allow it, while maintaining cluster security and stability.
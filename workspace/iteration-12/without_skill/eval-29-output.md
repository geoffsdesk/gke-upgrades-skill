I'll help you set up maintenance exclusions for your GKE clusters to handle your specific requirements. Here's the exact configuration:

## 1. Terraform Configuration

```hcl
resource "google_container_cluster" "primary" {
  name     = "your-cluster-name"
  location = "us-central1"

  # Disable automatic minor version upgrades
  node_config {
    # Node configuration
  }

  # Maintenance policy configuration
  maintenance_policy {
    # Set maintenance window (adjust timezone as needed)
    daily_maintenance_window {
      start_time = "03:00"  # 3 AM local time
    }

    # Quarterly code freeze in June
    maintenance_exclusion {
      exclusion_name = "quarterly-code-freeze-june"
      start_time     = "2024-06-01T00:00:00Z"
      end_time       = "2024-06-30T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    # Black Friday period exclusion
    maintenance_exclusion {
      exclusion_name = "black-friday-cyber-monday"
      start_time     = "2024-11-15T00:00:00Z"  # Start before Black Friday
      end_time       = "2024-12-03T23:59:59Z"  # End after Cyber Monday
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    # Recurring June exclusion for future years
    maintenance_exclusion {
      exclusion_name = "quarterly-code-freeze-june-2025"
      start_time     = "2025-06-01T00:00:00Z"
      end_time       = "2025-06-30T23:59:59Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    # Recurring November exclusion for future years
    maintenance_exclusion {
      exclusion_name = "black-friday-cyber-monday-2025"
      start_time     = "2025-11-15T00:00:00Z"
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

  # Prevent automatic minor version upgrades
  min_master_version = "1.28.3-gke.1286000"  # Pin to specific version
}

# Node pool with upgrade controls
resource "google_container_node_pool" "primary_nodes" {
  cluster    = google_container_cluster.primary.name
  location   = google_container_cluster.primary.location
  
  # Disable automatic upgrades for nodes
  management {
    auto_upgrade = false
    auto_repair  = true  # Keep auto-repair enabled for stability
  }

  upgrade_settings {
    # Control upgrade strategy
    max_surge       = 1
    max_unavailable = 0
    strategy        = "SURGE"
  }
}
```

## 2. gcloud CLI Commands

```bash
# Create cluster with maintenance exclusions
gcloud container clusters create your-cluster-name \
    --zone=us-central1-a \
    --maintenance-window-start="2024-01-01T03:00:00Z" \
    --maintenance-window-end="2024-01-01T07:00:00Z" \
    --maintenance-window-recurrence="FREQ=DAILY" \
    --no-enable-autoupgrade \
    --release-channel=regular

# Add June code freeze exclusion
gcloud container clusters update your-cluster-name \
    --zone=us-central1-a \
    --add-maintenance-exclusion-end="2024-06-30T23:59:59Z" \
    --add-maintenance-exclusion-name="quarterly-code-freeze-june-2024" \
    --add-maintenance-exclusion-scope="ALL_UPGRADES" \
    --add-maintenance-exclusion-start="2024-06-01T00:00:00Z"

# Add Black Friday/Cyber Monday exclusion
gcloud container clusters update your-cluster-name \
    --zone=us-central1-a \
    --add-maintenance-exclusion-end="2024-12-03T23:59:59Z" \
    --add-maintenance-exclusion-name="black-friday-cyber-monday-2024" \
    --add-maintenance-exclusion-scope="ALL_UPGRADES" \
    --add-maintenance-exclusion-start="2024-11-15T00:00:00Z"

# Disable automatic node upgrades
gcloud container node-pools update default-pool \
    --cluster=your-cluster-name \
    --zone=us-central1-a \
    --no-enable-autoupgrade
```

## 3. YAML Configuration for GitOps

```yaml
# maintenance-exclusions.yaml
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerCluster
metadata:
  name: your-cluster-name
spec:
  location: us-central1-a
  maintenancePolicy:
    dailyMaintenanceWindow:
      startTime: "03:00"
    maintenanceExclusions:
    - exclusionName: "quarterly-code-freeze-june-2024"
      startTime: "2024-06-01T00:00:00Z"
      endTime: "2024-06-30T23:59:59Z"
      exclusionOptions:
        scope: "ALL_UPGRADES"
    - exclusionName: "black-friday-cyber-monday-2024"
      startTime: "2024-11-15T00:00:00Z"
      endTime: "2024-12-03T23:59:59Z"
      exclusionOptions:
        scope: "ALL_UPGRADES"
    - exclusionName: "quarterly-code-freeze-june-2025"
      startTime: "2025-06-01T00:00:00Z"
      endTime: "2025-06-30T23:59:59Z"
      exclusionOptions:
        scope: "ALL_UPGRADES"
    - exclusionName: "black-friday-cyber-monday-2025"
      startTime: "2025-11-15T00:00:00Z"
      endTime: "2025-12-03T23:59:59Z"
      exclusionOptions:
        scope: "ALL_UPGRADES"
  releaseChannel:
    channel: "REGULAR"
  nodeConfig:
    machineType: "e2-medium"
```

## 4. Automation Script for Annual Updates

```bash
#!/bin/bash
# update-maintenance-exclusions.sh

CLUSTER_NAME="your-cluster-name"
ZONE="us-central1-a"
CURRENT_YEAR=$(date +%Y)
NEXT_YEAR=$((CURRENT_YEAR + 1))

# Add next year's June exclusion
gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --add-maintenance-exclusion-end="${NEXT_YEAR}-06-30T23:59:59Z" \
    --add-maintenance-exclusion-name="quarterly-code-freeze-june-${NEXT_YEAR}" \
    --add-maintenance-exclusion-scope="ALL_UPGRADES" \
    --add-maintenance-exclusion-start="${NEXT_YEAR}-06-01T00:00:00Z"

# Add next year's Black Friday exclusion
gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --add-maintenance-exclusion-end="${NEXT_YEAR}-12-03T23:59:59Z" \
    --add-maintenance-exclusion-name="black-friday-cyber-monday-${NEXT_YEAR}" \
    --add-maintenance-exclusion-scope="ALL_UPGRADES" \
    --add-maintenance-exclusion-start="${NEXT_YEAR}-11-15T00:00:00Z"

echo "Added maintenance exclusions for ${NEXT_YEAR}"
```

## 5. Monitoring and Alerting

```bash
# Check current maintenance exclusions
gcloud container clusters describe your-cluster-name \
    --zone=us-central1-a \
    --format="value(maintenancePolicy.maintenanceExclusions[].exclusionName,maintenancePolicy.maintenanceExclusions[].startTime,maintenancePolicy.maintenanceExclusions[].endTime)"

# Remove expired exclusions (run after each period)
gcloud container clusters update your-cluster-name \
    --zone=us-central1-a \
    --remove-maintenance-exclusion-name="quarterly-code-freeze-june-2024"
```

## Key Points:

1. **Minor Version Control**: Set `auto_upgrade = false` on node pools and avoid using `--enable-autoupgrade`
2. **Exclusion Scope**: Use `"ALL_UPGRADES"` to block both master and node upgrades
3. **Timing**: Black Friday exclusion starts Nov 15th and ends Dec 3rd to cover the entire period
4. **Recurring Setup**: You'll need to add future year exclusions manually or via automation
5. **Manual Upgrades**: With auto-upgrade disabled, you control when upgrades happen

Remember to:
- Update the years in exclusions annually
- Remove expired exclusions to keep the configuration clean
- Test upgrades in staging environments before applying to production
- Monitor GKE release notes for security patches that might need immediate attention
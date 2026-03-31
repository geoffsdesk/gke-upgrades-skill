Here's the exact GKE maintenance exclusion configuration for your requirements:

## 1. Terraform Configuration

```hcl
resource "google_container_cluster" "primary" {
  name     = "your-cluster-name"
  location = "us-central1-a"
  
  # Disable automatic upgrades for explicit control
  node_config {
    # Node configuration
  }

  # Maintenance policy with exclusions
  maintenance_policy {
    # Disable automatic minor version upgrades
    recurring_window {
      start_time = "2024-01-01T09:00:00Z"
      end_time   = "2024-01-01T17:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SA,SU"
    }

    # June code freeze exclusion
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
  }

  # Disable auto-upgrade and auto-repair for explicit control
  cluster_autoscaling {
    auto_provisioning_defaults {
      upgrade_settings {
        strategy = "SURGE"
        max_surge = 1
        max_unavailable = 0
      }
    }
  }
}

# Node pool with disabled auto-upgrades
resource "google_container_node_pool" "primary_nodes" {
  name       = "primary-node-pool"
  cluster    = google_container_cluster.primary.name
  location   = google_container_cluster.primary.location
  
  # Disable automatic upgrades
  management {
    auto_repair  = true
    auto_upgrade = false  # Explicitly disable auto-upgrades
  }

  upgrade_settings {
    strategy = "SURGE"
    max_surge = 1
    max_unavailable = 0
  }
}
```

## 2. gcloud CLI Commands

```bash
# Create cluster with maintenance exclusions
gcloud container clusters create your-cluster-name \
    --zone=us-central1-a \
    --maintenance-window-start="2024-01-01T09:00:00Z" \
    --maintenance-window-end="2024-01-01T17:00:00Z" \
    --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SA,SU" \
    --enable-autorepair \
    --no-enable-autoupgrade

# Add June code freeze exclusion
gcloud container clusters update your-cluster-name \
    --zone=us-central1-a \
    --add-maintenance-exclusion-name="june-code-freeze-2024" \
    --add-maintenance-exclusion-start="2024-06-01T00:00:00Z" \
    --add-maintenance-exclusion-end="2024-06-30T23:59:59Z" \
    --add-maintenance-exclusion-scope="ALL_UPGRADES"

# Add Black Friday/Cyber Monday exclusion
gcloud container clusters update your-cluster-name \
    --zone=us-central1-a \
    --add-maintenance-exclusion-name="black-friday-cyber-monday-2024" \
    --add-maintenance-exclusion-start="2024-11-20T00:00:00Z" \
    --add-maintenance-exclusion-end="2024-12-03T23:59:59Z" \
    --add-maintenance-exclusion-scope="ALL_UPGRADES"
```

## 3. YAML Configuration for Existing Clusters

```yaml
# maintenance-policy.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: maintenance-exclusions
  namespace: kube-system
data:
  policy: |
    maintenancePolicy:
      window:
        recurringWindow:
          window:
            startTime: "2024-01-01T09:00:00Z"
            endTime: "2024-01-01T17:00:00Z"
          recurrence: "FREQ=WEEKLY;BYDAY=SA,SU"
      maintenanceExclusions:
        june-code-freeze-2024:
          startTime: "2024-06-01T00:00:00Z"
          endTime: "2024-06-30T23:59:59Z"
          exclusionOptions:
            scope: ALL_UPGRADES
        black-friday-cyber-monday-2024:
          startTime: "2024-11-20T00:00:00Z"
          endTime: "2024-12-03T23:59:59Z"
          exclusionOptions:
            scope: ALL_UPGRADES
```

## 4. Annual Maintenance Script

Create this script to automatically update exclusions yearly:

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
    --remove-maintenance-exclusion-name="june-code-freeze-$CURRENT_YEAR" \
    --remove-maintenance-exclusion-name="black-friday-cyber-monday-$CURRENT_YEAR"

# Add next year's exclusions
gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --add-maintenance-exclusion-name="june-code-freeze-$NEXT_YEAR" \
    --add-maintenance-exclusion-start="${NEXT_YEAR}-06-01T00:00:00Z" \
    --add-maintenance-exclusion-end="${NEXT_YEAR}-06-30T23:59:59Z" \
    --add-maintenance-exclusion-scope="ALL_UPGRADES"

gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --add-maintenance-exclusion-name="black-friday-cyber-monday-$NEXT_YEAR" \
    --add-maintenance-exclusion-start="${NEXT_YEAR}-11-20T00:00:00Z" \
    --add-maintenance-exclusion-end="${NEXT_YEAR}-12-03T23:59:59Z" \
    --add-maintenance-exclusion-scope="ALL_UPGRADES"
```

## 5. Verification Commands

```bash
# Check current maintenance policy
gcloud container clusters describe your-cluster-name \
    --zone=us-central1-a \
    --format="yaml(maintenancePolicy)"

# List all maintenance exclusions
gcloud container clusters describe your-cluster-name \
    --zone=us-central1-a \
    --format="table(maintenancePolicy.maintenanceExclusions[].exclusionName,maintenancePolicy.maintenanceExclusions[].startTime,maintenancePolicy.maintenanceExclusions[].endTime)"

# Check node pool upgrade settings
gcloud container node-pools describe primary-node-pool \
    --cluster=your-cluster-name \
    --zone=us-central1-a \
    --format="yaml(management)"
```

## Key Points:

1. **Auto-upgrades disabled**: `auto_upgrade = false` prevents any automatic minor version upgrades
2. **Maintenance windows**: Set to weekends only (Saturday/Sunday) during business hours
3. **Complete exclusions**: `ALL_UPGRADES` scope blocks both node and control plane upgrades
4. **Flexible dates**: Black Friday exclusion covers extended period (Nov 20 - Dec 3)
5. **Manual control**: All upgrades require explicit approval via `gcloud` or console

Remember to run the annual script or manually update exclusion dates each year, and always test upgrades in a staging environment first.
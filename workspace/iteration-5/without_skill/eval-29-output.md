I'll help you set up maintenance exclusions for your GKE clusters to handle your specific requirements. Here's the exact configuration:

## 1. Terraform Configuration

```hcl
resource "google_container_cluster" "primary" {
  name     = "your-cluster-name"
  location = "us-central1"
  
  # Disable automatic upgrades for minor versions
  node_config {
    # Node configuration here
  }

  # Maintenance policy with exclusions
  maintenance_policy {
    # Allow maintenance on weekends only during normal periods
    recurring_window {
      start_time = "2023-01-07T09:00:00Z"  # Saturday 9 AM UTC
      end_time   = "2023-01-07T17:00:00Z"  # Saturday 5 PM UTC
      recurrence = "FREQ=WEEKLY;BYDAY=SA"
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
    channel = "REGULAR"  # or "STABLE" for even more control
  }

  # Disable automatic node upgrades
  node_pool {
    name       = "default-pool"
    node_count = 1

    management {
      auto_repair  = true
      auto_upgrade = false  # Disable automatic upgrades
    }

    upgrade_settings {
      strategy      = "SURGE"
      max_surge     = 1
      max_unavailable = 0
    }

    node_config {
      machine_type = "e2-medium"
      
      oauth_scopes = [
        "https://www.googleapis.com/auth/cloud-platform"
      ]
    }
  }
}
```

## 2. gcloud CLI Configuration

```bash
# Create the cluster with maintenance policy
gcloud container clusters create your-cluster-name \
  --zone us-central1-a \
  --maintenance-window-start "2023-01-07T09:00:00Z" \
  --maintenance-window-end "2023-01-07T17:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA" \
  --release-channel regular \
  --enable-autorepair \
  --no-enable-autoupgrade

# Add maintenance exclusions
gcloud container clusters update your-cluster-name \
  --zone us-central1-a \
  --add-maintenance-exclusion-name june-code-freeze \
  --add-maintenance-exclusion-start "2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end "2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope ALL_UPGRADES

gcloud container clusters update your-cluster-name \
  --zone us-central1-a \
  --add-maintenance-exclusion-name black-friday-cyber-monday \
  --add-maintenance-exclusion-start "2024-11-20T00:00:00Z" \
  --add-maintenance-exclusion-end "2024-12-03T23:59:59Z" \
  --add-maintenance-exclusion-scope ALL_UPGRADES
```

## 3. YAML Configuration for Existing Clusters

```yaml
# maintenance-policy.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: maintenance-exclusions-config
data:
  policy: |
    maintenancePolicy:
      window:
        recurringWindow:
          window:
            startTime: "2023-01-07T09:00:00Z"
            endTime: "2023-01-07T17:00:00Z"
          recurrence: "FREQ=WEEKLY;BYDAY=SA"
      maintenanceExclusions:
        june-code-freeze-2024:
          startTime: "2024-06-01T00:00:00Z"
          endTime: "2024-06-30T23:59:59Z"
          exclusionOptions:
            scope: "ALL_UPGRADES"
        black-friday-cyber-monday-2024:
          startTime: "2024-11-20T00:00:00Z"
          endTime: "2024-12-03T23:59:59Z"
          exclusionOptions:
            scope: "ALL_UPGRADES"
        june-code-freeze-2025:
          startTime: "2025-06-01T00:00:00Z"
          endTime: "2025-06-30T23:59:59Z"
          exclusionOptions:
            scope: "ALL_UPGRADES"
        black-friday-cyber-monday-2025:
          startTime: "2025-11-20T00:00:00Z"
          endTime: "2025-12-03T23:59:59Z"
          exclusionOptions:
            scope: "ALL_UPGRADES"
```

## 4. Script to Manage Annual Exclusions

```bash
#!/bin/bash
# update-maintenance-exclusions.sh

CLUSTER_NAME="your-cluster-name"
ZONE="us-central1-a"
CURRENT_YEAR=$(date +%Y)
NEXT_YEAR=$((CURRENT_YEAR + 1))

# Function to add exclusions for a given year
add_exclusions_for_year() {
  local year=$1
  
  echo "Adding maintenance exclusions for $year..."
  
  # June code freeze
  gcloud container clusters update $CLUSTER_NAME \
    --zone $ZONE \
    --add-maintenance-exclusion-name "june-code-freeze-$year" \
    --add-maintenance-exclusion-start "${year}-06-01T00:00:00Z" \
    --add-maintenance-exclusion-end "${year}-06-30T23:59:59Z" \
    --add-maintenance-exclusion-scope "ALL_UPGRADES"
  
  # Black Friday/Cyber Monday
  gcloud container clusters update $CLUSTER_NAME \
    --zone $ZONE \
    --add-maintenance-exclusion-name "black-friday-cyber-monday-$year" \
    --add-maintenance-exclusion-start "${year}-11-20T00:00:00Z" \
    --add-maintenance-exclusion-end "${year}-12-03T23:59:59Z" \
    --add-maintenance-exclusion-scope "ALL_UPGRADES"
}

# Add exclusions for current and next year
add_exclusions_for_year $CURRENT_YEAR
add_exclusions_for_year $NEXT_YEAR

echo "Maintenance exclusions updated successfully!"
```

## 5. Verification Commands

```bash
# Check current maintenance policy
gcloud container clusters describe your-cluster-name \
  --zone us-central1-a \
  --format="yaml(maintenancePolicy)"

# List all maintenance exclusions
gcloud container clusters describe your-cluster-name \
  --zone us-central1-a \
  --format="table(maintenancePolicy.maintenanceExclusions:label=EXCLUSIONS)"

# Check upgrade status
gcloud container clusters describe your-cluster-name \
  --zone us-central1-a \
  --format="value(nodePools[].management.autoUpgrade)"
```

## Key Points:

1. **Maintenance Window**: Set to Saturdays 9 AM - 5 PM UTC (adjust timezone as needed)
2. **June Exclusion**: Covers entire month for quarterly code freeze
3. **November Exclusion**: Extended period covering Black Friday through Cyber Monday
4. **Auto-upgrades Disabled**: Both cluster and node pool auto-upgrades are disabled
5. **Manual Control**: You'll need to explicitly trigger upgrades using `gcloud container clusters upgrade`

## Manual Upgrade Process:

When you're ready to upgrade:

```bash
# Check available versions
gcloud container get-server-config --zone us-central1-a

# Upgrade master
gcloud container clusters upgrade your-cluster-name \
  --zone us-central1-a \
  --master \
  --cluster-version 1.28.3-gke.1286000

# Upgrade nodes
gcloud container clusters upgrade your-cluster-name \
  --zone us-central1-a \
  --node-pool default-pool
```

This configuration ensures you have complete control over when upgrades happen while protecting your critical business periods.
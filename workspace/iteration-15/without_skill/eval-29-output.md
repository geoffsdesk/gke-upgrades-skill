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

  # Maintenance policy with exclusions
  maintenance_policy {
    # Recurring maintenance window (when maintenance CAN happen)
    recurring_window {
      start_time = "2024-01-07T09:00:00Z"  # Sunday 9 AM UTC
      end_time   = "2024-01-07T17:00:00Z"  # Sunday 5 PM UTC
      recurrence = "FREQ=WEEKLY;BYDAY=SU"
    }

    # June code freeze exclusion (entire month)
    maintenance_exclusion {
      exclusion_name = "june-code-freeze"
      start_time     = "2024-06-01T00:00:00Z"
      end_time       = "2024-07-01T00:00:00Z"
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    # Black Friday/Cyber Monday exclusion
    maintenance_exclusion {
      exclusion_name = "black-friday-cyber-monday"
      start_time     = "2024-11-22T00:00:00Z"  # Week before Black Friday
      end_time       = "2024-12-03T00:00:00Z"  # Week after Cyber Monday
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    # Continuous exclusion for minor version upgrades
    maintenance_exclusion {
      exclusion_name = "no-minor-version-upgrades"
      start_time     = "2024-01-01T00:00:00Z"
      end_time       = "2025-12-31T23:59:59Z"
      exclusion_options {
        scope = "MINOR_AND_PATCH"
      }
    }
  }

  # Disable automatic upgrades
  cluster_autoscaling {
    auto_provisioning_defaults {
      upgrade_settings {
        strategy        = "SURGE"
        max_surge       = 1
        max_unavailable = 0
      }
    }
  }

  # Node pool configuration
  node_pool {
    name       = "default-pool"
    node_count = 1

    management {
      auto_repair  = true
      auto_upgrade = false  # Disable automatic node upgrades
    }

    upgrade_settings {
      strategy        = "SURGE"
      max_surge       = 1
      max_unavailable = 0
    }
  }
}
```

## 2. gcloud CLI Configuration

```bash
# Create the cluster with maintenance policy
gcloud container clusters create your-cluster-name \
    --zone=us-central1-a \
    --release-channel=regular \
    --enable-autorepair \
    --no-enable-autoupgrade \
    --maintenance-window-start="2024-01-07T09:00:00Z" \
    --maintenance-window-end="2024-01-07T17:00:00Z" \
    --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SU"

# Add June code freeze exclusion
gcloud container clusters update your-cluster-name \
    --zone=us-central1-a \
    --add-maintenance-exclusion-name="june-code-freeze" \
    --add-maintenance-exclusion-start="2024-06-01T00:00:00Z" \
    --add-maintenance-exclusion-end="2024-07-01T00:00:00Z" \
    --add-maintenance-exclusion-scope="ALL_UPGRADES"

# Add Black Friday/Cyber Monday exclusion
gcloud container clusters update your-cluster-name \
    --zone=us-central1-a \
    --add-maintenance-exclusion-name="black-friday-cyber-monday" \
    --add-maintenance-exclusion-start="2024-11-22T00:00:00Z" \
    --add-maintenance-exclusion-end="2024-12-03T00:00:00Z" \
    --add-maintenance-exclusion-scope="ALL_UPGRADES"

# Add continuous minor version upgrade exclusion
gcloud container clusters update your-cluster-name \
    --zone=us-central1-a \
    --add-maintenance-exclusion-name="no-minor-version-upgrades" \
    --add-maintenance-exclusion-start="2024-01-01T00:00:00Z" \
    --add-maintenance-exclusion-end="2025-12-31T23:59:59Z" \
    --add-maintenance-exclusion-scope="MINOR_AND_PATCH"
```

## 3. YAML Configuration for kubectl

```yaml
# maintenance-policy.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: maintenance-exclusions-config
  namespace: kube-system
data:
  policy.yaml: |
    maintenancePolicy:
      recurringWindow:
        startTime: "2024-01-07T09:00:00Z"
        endTime: "2024-01-07T17:00:00Z"
        recurrence: "FREQ=WEEKLY;BYDAY=SU"
      maintenanceExclusions:
        - exclusionName: "june-code-freeze"
          startTime: "2024-06-01T00:00:00Z"
          endTime: "2024-07-01T00:00:00Z"
          exclusionOptions:
            scope: "ALL_UPGRADES"
        - exclusionName: "black-friday-cyber-monday"
          startTime: "2024-11-22T00:00:00Z"
          endTime: "2024-12-03T00:00:00Z"
          exclusionOptions:
            scope: "ALL_UPGRADES"
        - exclusionName: "no-minor-version-upgrades"
          startTime: "2024-01-01T00:00:00Z"
          endTime: "2025-12-31T23:59:59Z"
          exclusionOptions:
            scope: "MINOR_AND_PATCH"
```

## 4. Automation Script for Annual Updates

```bash
#!/bin/bash
# update-maintenance-exclusions.sh

CLUSTER_NAME="your-cluster-name"
ZONE="us-central1-a"
CURRENT_YEAR=$(date +%Y)
NEXT_YEAR=$((CURRENT_YEAR + 1))

echo "Updating maintenance exclusions for $CURRENT_YEAR..."

# Remove old exclusions
gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --remove-maintenance-exclusion="june-code-freeze" || true

gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --remove-maintenance-exclusion="black-friday-cyber-monday" || true

gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --remove-maintenance-exclusion="no-minor-version-upgrades" || true

# Add new exclusions for current year
gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --add-maintenance-exclusion-name="june-code-freeze" \
    --add-maintenance-exclusion-start="${CURRENT_YEAR}-06-01T00:00:00Z" \
    --add-maintenance-exclusion-end="${CURRENT_YEAR}-07-01T00:00:00Z" \
    --add-maintenance-exclusion-scope="ALL_UPGRADES"

gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --add-maintenance-exclusion-name="black-friday-cyber-monday" \
    --add-maintenance-exclusion-start="${CURRENT_YEAR}-11-22T00:00:00Z" \
    --add-maintenance-exclusion-end="${CURRENT_YEAR}-12-03T00:00:00Z" \
    --add-maintenance-exclusion-scope="ALL_UPGRADES"

gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --add-maintenance-exclusion-name="no-minor-version-upgrades" \
    --add-maintenance-exclusion-start="${CURRENT_YEAR}-01-01T00:00:00Z" \
    --add-maintenance-exclusion-end="${NEXT_YEAR}-12-31T23:59:59Z" \
    --add-maintenance-exclusion-scope="MINOR_AND_PATCH"

echo "Maintenance exclusions updated successfully!"
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
    --format="table(maintenancePolicy.maintenanceExclusions[].exclusionName,
                     maintenancePolicy.maintenanceExclusions[].startTime,
                     maintenancePolicy.maintenanceExclusions[].endTime,
                     maintenancePolicy.maintenanceExclusions[].exclusionOptions.scope)"
```

## Key Points:

1. **Maintenance Window**: Set to Sundays 9 AM - 5 PM UTC (adjust timezone as needed)
2. **June Exclusion**: Blocks ALL upgrades for the entire month
3. **Black Friday Exclusion**: Covers approximately 2 weeks around Black Friday/Cyber Monday
4. **Minor Version Control**: Prevents automatic minor version upgrades year-round
5. **Node Pool Settings**: Disabled auto-upgrade on node pools for full control

Remember to:
- Adjust the timezone in the maintenance window to match your business hours
- Update the exclusion dates annually
- Test the configuration in a development cluster first
- Set up monitoring for available security patches during exclusion periods
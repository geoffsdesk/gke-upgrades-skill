Here's the exact GKE maintenance configuration to handle your requirements:

## 1. Maintenance Exclusion Windows

Create a maintenance policy file `maintenance-policy.yaml`:

```yaml
# maintenance-policy.yaml
exclusionWindows:
  - name: "quarterly-code-freeze-june"
    startTime: "2024-06-01T00:00:00Z"
    endTime: "2024-06-30T23:59:59Z"
    scope: "NO_UPGRADES"
  - name: "black-friday-cyber-monday"
    startTime: "2024-11-15T00:00:00Z"
    endTime: "2024-12-05T23:59:59Z"
    scope: "NO_UPGRADES"
```

## 2. Terraform Configuration

```hcl
resource "google_container_cluster" "primary" {
  name     = "your-cluster-name"
  location = "us-central1"

  # Disable automatic minor version upgrades
  node_version = var.kubernetes_version
  min_master_version = var.kubernetes_version

  maintenance_policy {
    # Prevent automatic minor version upgrades
    daily_maintenance_window {
      start_time = "03:00"  # Adjust to your preferred time
    }
  }

  # Maintenance exclusions
  maintenance_policy {
    maintenance_exclusion {
      exclusion_name = "quarterly-code-freeze-june"
      start_time     = "2024-06-01T00:00:00Z"
      end_time       = "2024-06-30T23:59:59Z"
      exclusion_options {
        scope = "NO_UPGRADES"
      }
    }

    maintenance_exclusion {
      exclusion_name = "black-friday-cyber-monday" 
      start_time     = "2024-11-15T00:00:00Z"
      end_time       = "2024-12-05T23:59:59Z"
      exclusion_options {
        scope = "NO_UPGRADES"
      }
    }
  }

  # Disable automatic node upgrades
  node_config {
    # Node configuration
  }

  # Node pool with manual upgrades only
  node_pool {
    name = "default-pool"
    
    management {
      auto_repair  = true
      auto_upgrade = false  # Disable automatic upgrades
    }

    upgrade_settings {
      strategy = "SURGE"
      max_surge = 1
      max_unavailable = 0
    }
  }

  # Disable release channel for full manual control
  release_channel {
    channel = "UNSPECIFIED"
  }
}
```

## 3. gcloud CLI Commands

### Apply maintenance exclusions:
```bash
# June code freeze
gcloud container clusters update YOUR_CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --add-maintenance-exclusion-end="2024-06-30T23:59:59Z" \
    --add-maintenance-exclusion-name="quarterly-code-freeze-june" \
    --add-maintenance-exclusion-scope="no-upgrades" \
    --add-maintenance-exclusion-start="2024-06-01T00:00:00Z"

# Black Friday/Cyber Monday period
gcloud container clusters update YOUR_CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --add-maintenance-exclusion-end="2024-12-05T23:59:59Z" \
    --add-maintenance-exclusion-name="black-friday-cyber-monday" \
    --add-maintenance-exclusion-scope="no-upgrades" \
    --add-maintenance-exclusion-start="2024-11-15T00:00:00Z"

# Disable automatic node upgrades
gcloud container node-pools update default-pool \
    --cluster=YOUR_CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --no-enable-autoupgrade

# Set maintenance window (optional - for minor patches only)
gcloud container clusters update YOUR_CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --maintenance-window-start="2024-01-01T03:00:00Z" \
    --maintenance-window-end="2024-01-01T07:00:00Z" \
    --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SA"
```

## 4. YAML Manifest for Multiple Years

For recurring exclusions, create `recurring-maintenance-exclusions.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: maintenance-schedule
data:
  exclusions: |
    # 2024 exclusions
    - name: "code-freeze-june-2024"
      start: "2024-06-01T00:00:00Z"
      end: "2024-06-30T23:59:59Z"
    - name: "holiday-shopping-2024"
      start: "2024-11-15T00:00:00Z" 
      end: "2024-12-05T23:59:59Z"
    
    # 2025 exclusions  
    - name: "code-freeze-june-2025"
      start: "2025-06-01T00:00:00Z"
      end: "2025-06-30T23:59:59Z"
    - name: "holiday-shopping-2025"
      start: "2025-11-15T00:00:00Z"
      end: "2025-12-05T23:59:59Z"
```

## 5. Automation Script for Annual Updates

Create `update-maintenance-exclusions.sh`:

```bash
#!/bin/bash
set -e

CLUSTER_NAME="your-cluster-name"
ZONE="us-central1-a"
CURRENT_YEAR=$(date +%Y)
NEXT_YEAR=$((CURRENT_YEAR + 1))

# Remove old exclusions
echo "Removing old maintenance exclusions..."
gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --remove-maintenance-exclusion-name="quarterly-code-freeze-june" \
    --remove-maintenance-exclusion-name="black-friday-cyber-monday" \
    --quiet || true

# Add current year exclusions
echo "Adding ${CURRENT_YEAR} maintenance exclusions..."

# June code freeze
gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --add-maintenance-exclusion-end="${CURRENT_YEAR}-06-30T23:59:59Z" \
    --add-maintenance-exclusion-name="quarterly-code-freeze-june" \
    --add-maintenance-exclusion-scope="no-upgrades" \
    --add-maintenance-exclusion-start="${CURRENT_YEAR}-06-01T00:00:00Z"

# Black Friday/Cyber Monday
gcloud container clusters update $CLUSTER_NAME \
    --zone=$ZONE \
    --add-maintenance-exclusion-end="${CURRENT_YEAR}-12-05T23:59:59Z" \
    --add-maintenance-exclusion-name="black-friday-cyber-monday" \
    --add-maintenance-exclusion-scope="no-upgrades" \
    --add-maintenance-exclusion-start="${CURRENT_YEAR}-11-15T00:00:00Z"

echo "Maintenance exclusions updated successfully!"
```

## 6. Verification Commands

```bash
# Check current maintenance policy
gcloud container clusters describe YOUR_CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --format="yaml(maintenancePolicy)"

# List all maintenance exclusions  
gcloud container clusters describe YOUR_CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --format="table(maintenancePolicy.window.maintenanceExclusions[].name,maintenancePolicy.window.maintenanceExclusions[].startTime,maintenancePolicy.window.maintenanceExclusions[].endTime)"

# Check node pool upgrade settings
gcloud container node-pools describe default-pool \
    --cluster=YOUR_CLUSTER_NAME \
    --zone=YOUR_ZONE \
    --format="yaml(management)"
```

## Key Points:

1. **No Automatic Minor Upgrades**: Set `release_channel` to `UNSPECIFIED` and `auto_upgrade = false`
2. **June Code Freeze**: Complete blackout from June 1-30
3. **Black Friday Period**: Extended protection from Nov 15 - Dec 5  
4. **Manual Control**: All upgrades require explicit approval via gcloud/terraform
5. **Recurring**: Use the automation script annually to update exclusion windows

This configuration ensures complete control over when maintenance occurs while protecting your critical business periods.
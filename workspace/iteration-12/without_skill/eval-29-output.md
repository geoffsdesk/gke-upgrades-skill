Here's the exact GKE maintenance exclusion configuration for your requirements:

## 1. Terraform Configuration

```hcl
resource "google_container_cluster" "primary" {
  name     = "your-cluster-name"
  location = "us-central1"

  # Disable automatic upgrades for control plane and nodes
  node_config {
    # Node configuration
  }

  # Control plane maintenance policy
  maintenance_policy {
    # Recurring maintenance window (optional - for patches only)
    recurring_window {
      start_time = "2024-01-01T09:00:00Z"
      end_time   = "2024-01-01T17:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SU"
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

    # Black Friday/Cyber Monday exclusion (extended period)
    maintenance_exclusion {
      exclusion_name = "black-friday-cyber-monday"
      start_time     = "2024-11-20T00:00:00Z"  # Week before Black Friday
      end_time       = "2024-12-03T23:59:59Z"  # Tuesday after Cyber Monday
      exclusion_options {
        scope = "ALL_UPGRADES"
      }
    }

    # Permanent exclusion for minor version upgrades
    maintenance_exclusion {
      exclusion_name = "no-minor-version-auto-upgrades"
      start_time     = "2024-01-01T00:00:00Z"
      end_time       = "2030-12-31T23:59:59Z"  # Long-term exclusion
      exclusion_options {
        scope = "MINOR_UPGRADES"
      }
    }
  }

  # Disable automatic upgrades
  remove_default_node_pool = true
}

resource "google_container_node_pool" "primary_nodes" {
  name       = "primary-node-pool"
  cluster    = google_container_cluster.primary.name
  location   = google_container_cluster.primary.location
  node_count = 3

  # Disable automatic upgrades for node pool
  management {
    auto_repair  = true   # Keep auto-repair for node health
    auto_upgrade = false  # Disable auto-upgrade
  }

  node_config {
    machine_type = "e2-medium"
    
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]
  }
}
```

## 2. gcloud CLI Configuration

```bash
# Create the cluster with maintenance exclusions
gcloud container clusters create your-cluster-name \
  --zone=us-central1-a \
  --maintenance-window-start="2024-01-01T09:00:00Z" \
  --maintenance-window-end="2024-01-01T17:00:00Z" \
  --maintenance-window-recurrence="FREQ=WEEKLY;BYDAY=SU" \
  --no-enable-autoupgrade \
  --enable-autorepair

# Add June code freeze exclusion
gcloud container clusters update your-cluster-name \
  --zone=us-central1-a \
  --add-maintenance-exclusion-name="june-code-freeze" \
  --add-maintenance-exclusion-start="2024-06-01T00:00:00Z" \
  --add-maintenance-exclusion-end="2024-06-30T23:59:59Z" \
  --add-maintenance-exclusion-scope="ALL_UPGRADES"

# Add Black Friday/Cyber Monday exclusion
gcloud container clusters update your-cluster-name \
  --zone=us-central1-a \
  --add-maintenance-exclusion-name="black-friday-cyber-monday" \
  --add-maintenance-exclusion-start="2024-11-20T00:00:00Z" \
  --add-maintenance-exclusion-end="2024-12-03T23:59:59Z" \
  --add-maintenance-exclusion-scope="ALL_UPGRADES"

# Add permanent minor version upgrade exclusion
gcloud container clusters update your-cluster-name \
  --zone=us-central1-a \
  --add-maintenance-exclusion-name="no-minor-version-auto-upgrades" \
  --add-maintenance-exclusion-start="2024-01-01T00:00:00Z" \
  --add-maintenance-exclusion-end="2030-12-31T23:59:59Z" \
  --add-maintenance-exclusion-scope="MINOR_UPGRADES"
```

## 3. YAML Configuration (for existing clusters)

```yaml
# maintenance-policy.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: maintenance-exclusions-config
data:
  exclusions: |
    # June Code Freeze
    - name: "june-code-freeze"
      start: "2024-06-01T00:00:00Z"
      end: "2024-06-30T23:59:59Z"
      scope: "ALL_UPGRADES"
    
    # Black Friday/Cyber Monday
    - name: "black-friday-cyber-monday" 
      start: "2024-11-20T00:00:00Z"
      end: "2024-12-03T23:59:59Z"
      scope: "ALL_UPGRADES"
    
    # No Minor Version Auto-upgrades
    - name: "no-minor-version-auto-upgrades"
      start: "2024-01-01T00:00:00Z"  
      end: "2030-12-31T23:59:59Z"
      scope: "MINOR_UPGRADES"
```

## 4. Automated Annual Updates Script

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
  --remove-maintenance-exclusion="june-code-freeze-$CURRENT_YEAR" \
  --remove-maintenance-exclusion="black-friday-cyber-monday-$CURRENT_YEAR"

# Add new exclusions for next year
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
  --format="value(maintenancePolicy)"

# List all maintenance exclusions
gcloud container clusters describe your-cluster-name \
  --zone=us-central1-a \
  --format="table(maintenancePolicy.exclusions[].exclusionName,
                   maintenancePolicy.exclusions[].startTime,
                   maintenancePolicy.exclusions[].endTime,
                   maintenancePolicy.exclusions[].exclusionOptions.scope)"
```

## Key Configuration Details:

1. **June Code Freeze**: Blocks ALL upgrades for entire month of June
2. **Black Friday/Cyber Monday**: Extended exclusion from Nov 20 - Dec 3 (covers preparation and recovery time)
3. **Minor Version Control**: Long-term exclusion (until 2030) prevents automatic minor version upgrades
4. **Scope Options**:
   - `ALL_UPGRADES`: Blocks all maintenance
   - `MINOR_UPGRADES`: Blocks only minor version upgrades
   - `PATCH_UPGRADES`: Blocks only patch upgrades

**Important Notes**:
- Security patches may still be applied during exclusions if critical
- You'll need to manually trigger upgrades during allowed windows
- Update the years annually for recurring exclusions
- Consider time zones when setting exclusion windows
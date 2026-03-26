Here's the exact GKE configuration to handle your maintenance exclusions and upgrade policies:

## 1. Terraform Configuration

```hcl
resource "google_container_cluster" "primary" {
  name     = "your-cluster-name"
  location = "us-central1"

  # Disable automatic upgrades for minor versions
  node_config {
    # Node configuration
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

    # Daily maintenance window (when updates ARE allowed)
    daily_maintenance_window {
      start_time = "03:00"  # 3 AM in cluster's timezone
    }
  }

  # Disable automatic minor version upgrades
  release_channel {
    channel = "REGULAR"  # or "RAPID", "STABLE"
  }

  # Node auto-upgrade configuration
  node_pool {
    name = "default-pool"
    
    management {
      auto_upgrade = false  # Disable automatic node upgrades
      auto_repair  = true   # Keep auto-repair enabled for stability
    }

    upgrade_settings {
      strategy      = "SURGE"
      max_surge     = 1
      max_unavailable = 0
    }
  }
}
```

## 2. YAML Configuration (for existing clusters)

```yaml
# maintenance-policy.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: maintenance-exclusions
data:
  policy: |
    maintenanceExclusions:
      quarterly-freeze:
        startTime: "2024-06-01T00:00:00Z"
        endTime: "2024-06-30T23:59:59Z"
        scope: "NO_UPGRADES"
      black-friday-period:
        startTime: "2024-11-20T00:00:00Z" 
        endTime: "2024-11-30T23:59:59Z"
        scope: "NO_UPGRADES"
```

## 3. gcloud Commands

```bash
# Set maintenance window
gcloud container clusters update CLUSTER_NAME \
    --maintenance-window-start "2024-01-01T03:00:00Z" \
    --maintenance-window-end "2024-01-01T07:00:00Z" \
    --maintenance-window-recurrence "FREQ=DAILY" \
    --zone=ZONE

# Add June exclusion (quarterly freeze)
gcloud container clusters update CLUSTER_NAME \
    --add-maintenance-exclusion-end "2024-06-30T23:59:59Z" \
    --add-maintenance-exclusion-name "quarterly-code-freeze" \
    --add-maintenance-exclusion-start "2024-06-01T00:00:00Z" \
    --add-maintenance-exclusion-scope "NO_UPGRADES" \
    --zone=ZONE

# Add November exclusion (Black Friday/Cyber Monday)
gcloud container clusters update CLUSTER_NAME \
    --add-maintenance-exclusion-end "2024-11-30T23:59:59Z" \
    --add-maintenance-exclusion-name "black-friday-period" \
    --add-maintenance-exclusion-start "2024-11-20T00:00:00Z" \
    --add-maintenance-exclusion-scope "NO_UPGRADES" \
    --zone=ZONE

# Disable automatic node upgrades
gcloud container node-pools update default-pool \
    --cluster=CLUSTER_NAME \
    --no-enable-autoupgrade \
    --zone=ZONE

# Disable automatic control plane upgrades
gcloud container clusters update CLUSTER_NAME \
    --no-enable-autoupgrade \
    --zone=ZONE
```

## 4. Complete Terraform with All Requirements

```hcl
resource "google_container_cluster" "production" {
  name     = "production-cluster"
  location = "us-central1"

  # Remove default node pool
  remove_default_node_pool = true
  initial_node_count       = 1

  # Release channel for controlled updates
  release_channel {
    channel = "REGULAR"
  }

  # Maintenance policy with exclusions
  maintenance_policy {
    # Daily maintenance window (3-7 AM)
    daily_maintenance_window {
      start_time = "03:00"
    }

    # Maintenance exclusions
    maintenance_exclusion {
      exclusion_name = "quarterly-code-freeze"
      start_time     = "2024-06-01T00:00:00Z"
      end_time       = "2024-06-30T23:59:59Z"
      exclusion_options {
        scope = "NO_UPGRADES"
      }
    }

    maintenance_exclusion {
      exclusion_name = "black-friday-cyber-monday"
      start_time     = "2024-11-20T00:00:00Z"
      end_time       = "2024-11-30T23:59:59Z"
      exclusion_options {
        scope = "NO_UPGRADES"
      }
    }

    # Recurring exclusions for future years
    recurring_window {
      start_time = "2025-06-01T00:00:00Z"
      end_time   = "2025-06-30T23:59:59Z"
      recurrence = "FREQ=YEARLY;BYMONTH=6"
    }

    recurring_window {
      start_time = "2025-11-20T00:00:00Z"
      end_time   = "2025-11-30T23:59:59Z"
      recurrence = "FREQ=YEARLY;BYMONTH=11"
    }
  }
}

resource "google_container_node_pool" "primary_nodes" {
  name       = "primary-node-pool"
  location   = "us-central1"
  cluster    = google_container_cluster.production.name
  node_count = 3

  # Disable automatic upgrades - require manual approval
  management {
    auto_repair  = true   # Keep for node health
    auto_upgrade = false  # Disable for manual control
  }

  # Upgrade settings for when you do manual upgrades
  upgrade_settings {
    strategy        = "SURGE"
    max_surge       = 1
    max_unavailable = 0
  }

  node_config {
    preemptible  = false
    machine_type = "e2-medium"

    oauth_scopes = [
      "https://www.googleapis.com/auth/logging.write",
      "https://www.googleapis.com/auth/monitoring",
    ]
  }
}
```

## 5. Validation Commands

```bash
# Check current maintenance policy
gcloud container clusters describe CLUSTER_NAME \
    --zone=ZONE \
    --format="value(maintenancePolicy)"

# List maintenance exclusions
gcloud container clusters describe CLUSTER_NAME \
    --zone=ZONE \
    --format="table(maintenancePolicy.window.maintenanceExclusions[].exclusionName,
                    maintenancePolicy.window.maintenanceExclusions[].startTime,
                    maintenancePolicy.window.maintenanceExclusions[].endTime)"

# Check node pool upgrade settings
gcloud container node-pools describe default-pool \
    --cluster=CLUSTER_NAME \
    --zone=ZONE \
    --format="value(management.autoUpgrade)"
```

## Key Points:

1. **Maintenance Exclusions**: Block ALL upgrades during June and November 20-30
2. **Auto-upgrade Disabled**: Both control plane and node pools require manual approval
3. **Auto-repair Enabled**: Keeps unhealthy nodes replaced automatically
4. **Maintenance Window**: 3-7 AM daily for when updates ARE allowed
5. **Recurring**: Exclusions repeat yearly automatically

This configuration ensures no surprise upgrades during your critical business periods while maintaining cluster health through auto-repair.
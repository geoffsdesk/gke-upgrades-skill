Here's the exact GKE maintenance exclusion configuration for your requirements:

## 1. Terraform Configuration

```hcl
resource "google_container_cluster" "main" {
  name     = "your-cluster-name"
  location = "us-central1"

  # Disable automatic upgrades for minor versions
  node_config {
    # Node configuration here
  }

  # Control plane maintenance policy
  maintenance_policy {
    # Quarterly code freeze in June (entire month)
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

    # Daily maintenance window (when maintenance IS allowed)
    daily_maintenance_window {
      start_time = "03:00"  # 3 AM in cluster's timezone
    }
  }

  # Disable automatic minor version upgrades
  release_channel {
    channel = "REGULAR"  # or "STABLE" for more conservative updates
  }

  # Explicitly control upgrade behavior
  cluster_autoscaling {
    auto_provisioning_defaults {
      upgrade_settings {
        max_surge       = 1
        max_unavailable = 0
        strategy        = "SURGE"
      }
    }
  }
}

# Node pool with controlled upgrades
resource "google_container_node_pool" "main" {
  name       = "main-pool"
  cluster    = google_container_cluster.main.name
  location   = google_container_cluster.main.location
  node_count = 3

  # Disable automatic upgrades and repairs during exclusion periods
  management {
    auto_repair  = true
    auto_upgrade = false  # Require explicit approval for upgrades
  }

  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
    strategy        = "SURGE"
  }

  node_config {
    machine_type = "e2-standard-4"
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]
  }
}
```

## 2. Using gcloud Commands

```bash
# Create cluster with maintenance exclusions
gcloud container clusters create your-cluster-name \
    --zone=us-central1-a \
    --maintenance-window-start=2024-06-01T00:00:00Z \
    --maintenance-window-end=2024-06-30T23:59:59Z \
    --maintenance-window-recurrence="FREQ=YEARLY;BYMONTH=6" \
    --daily-maintenance-window=03:00 \
    --release-channel=regular \
    --no-enable-autoupgrade

# Add June maintenance exclusion
gcloud container clusters update your-cluster-name \
    --zone=us-central1-a \
    --add-maintenance-exclusion-end=2024-06-30T23:59:59Z \
    --add-maintenance-exclusion-name="june-code-freeze" \
    --add-maintenance-exclusion-start=2024-06-01T00:00:00Z \
    --add-maintenance-exclusion-scope=NO_UPGRADES

# Add November Black Friday exclusion
gcloud container clusters update your-cluster-name \
    --zone=us-central1-a \
    --add-maintenance-exclusion-end=2024-11-30T23:59:59Z \
    --add-maintenance-exclusion-name="black-friday-cyber-monday" \
    --add-maintenance-exclusion-start=2024-11-20T00:00:00Z \
    --add-maintenance-exclusion-scope=NO_UPGRADES

# Set daily maintenance window
gcloud container clusters update your-cluster-name \
    --zone=us-central1-a \
    --maintenance-window=03:00

# Disable node auto-upgrade (requires manual approval)
gcloud container node-pools update main-pool \
    --cluster=your-cluster-name \
    --zone=us-central1-a \
    --no-enable-autoupgrade
```

## 3. YAML Configuration (for GitOps)

```yaml
apiVersion: container.cnrm.cloud.google.com/v1beta1
kind: ContainerCluster
metadata:
  name: your-cluster-name
  namespace: default
spec:
  location: us-central1-a
  
  # Maintenance policy with exclusions
  maintenancePolicy:
    dailyMaintenanceWindow:
      startTime: "03:00"
    
    # June code freeze exclusion
    maintenanceExclusions:
      june-code-freeze:
        exclusionName: "june-code-freeze"
        startTime: "2024-06-01T00:00:00Z"
        endTime: "2024-06-30T23:59:59Z"
        exclusionOptions:
          scope: "NO_UPGRADES"
      
      # Black Friday/Cyber Monday exclusion  
      black-friday-exclusion:
        exclusionName: "black-friday-cyber-monday"
        startTime: "2024-11-20T00:00:00Z"
        endTime: "2024-11-30T23:59:59Z"
        exclusionOptions:
          scope: "NO_UPGRADES"
  
  # Control release channel for upgrade frequency
  releaseChannel:
    channel: "REGULAR"
  
  # Disable automatic minor upgrades
  nodeConfig:
    machineType: "e2-standard-4"
  
  nodePool:
    name: "main-pool"
    management:
      autoRepair: true
      autoUpgrade: false  # Manual approval required
```

## 4. Manual Upgrade Process

When you're ready to approve upgrades outside exclusion periods:

```bash
# Check available upgrades
gcloud container get-server-config --zone=us-central1-a

# Upgrade control plane (manual approval)
gcloud container clusters upgrade your-cluster-name \
    --master \
    --cluster-version=1.28.3-gke.1286000 \
    --zone=us-central1-a

# Upgrade node pool (manual approval)
gcloud container clusters upgrade your-cluster-name \
    --node-pool=main-pool \
    --cluster-version=1.28.3-gke.1286000 \
    --zone=us-central1-a
```

## Key Points:

1. **June Exclusion**: Blocks ALL maintenance during your quarterly code freeze
2. **November Exclusion**: Covers Black Friday (Nov 24) through Cyber Monday and buffer days
3. **Manual Upgrades**: `auto_upgrade = false` requires your explicit approval for any version changes
4. **Maintenance Window**: 3 AM daily window when maintenance IS allowed (outside exclusion periods)
5. **Release Channel**: Use `REGULAR` or `STABLE` to control update frequency

This configuration ensures no surprise upgrades during your critical periods while maintaining security patches during approved maintenance windows.
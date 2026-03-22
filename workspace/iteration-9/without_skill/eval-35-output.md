Here's a comprehensive strategy for a GKE cluster optimized for long-running H100 training workloads:

## Cluster Configuration

```yaml
# cluster-config.yaml
apiVersion: container.googleapis.com/v1
kind: Cluster
metadata:
  name: ml-training-cluster
spec:
  releaseChannel:
    channel: REGULAR  # More stable than RAPID, more current than STABLE
  
  maintenancePolicy:
    window:
      dailyMaintenanceWindow:
        startTime: "02:00"  # Adjust for your timezone
      maintenanceExclusions:
        - name: "training-protection"
          startTime: "2024-01-01T00:00:00Z"
          endTime: "2024-12-31T23:59:59Z"
          scope: NO_UPGRADES  # Block all upgrades during training
  
  # Enable workload identity and other security features
  workloadIdentityConfig:
    workloadPool: "PROJECT_ID.svc.id.goog"
  
  networkPolicy:
    enabled: true
  
  # Enable surge upgrades for when you do upgrade
  nodePoolDefaults:
    upgradeSettings:
      maxSurge: 1
      maxUnavailable: 0
```

## Node Pool Strategy

```yaml
# gpu-nodepool.yaml
apiVersion: container.googleapis.com/v1
kind: NodePool
metadata:
  name: h100-training-pool
spec:
  cluster: ml-training-cluster
  
  # Use multiple smaller node pools instead of one large pool
  initialNodeCount: 2
  
  nodeConfig:
    machineType: a3-highgpu-8g  # 8x H100 GPUs
    accelerators:
      - acceleratorCount: 8
        acceleratorType: nvidia-h100-80gb
    
    # Use local SSDs for checkpointing
    localSsdCount: 16  # 24TB total
    
    # Spot instances for cost optimization (consider carefully)
    # spot: true  # Only if your training can handle preemption
    
    # Enable GPU sharing if needed
    guestAccelerators:
      - type: nvidia-h100-80gb
        count: 8
        gpuSharingConfig:
          maxSharedClientsPerGpu: 1
    
    # Optimize for training workloads
    kubeletConfig:
      cpuManagerPolicy: "static"
      topologyManagerPolicy: "best-effort"
    
    linuxNodeConfig:
      sysctls:
        # Optimize for high-bandwidth networking
        net.core.rmem_max: "134217728"
        net.core.wmem_max: "134217728"
        net.ipv4.tcp_rmem: "4096 87380 134217728"
  
  # Critical: Configure upgrade settings
  upgradeSettings:
    maxSurge: 0
    maxUnavailable: 0  # Prevent any node disruption
    
  # Use blue-green strategy for safer upgrades
  strategy:
    type: "SURGE"  # When you do upgrade
```

## Terraform Configuration

```hcl
# main.tf
resource "google_container_cluster" "ml_training" {
  name     = "ml-training-cluster"
  location = var.region
  
  # Use regional cluster for HA control plane
  node_locations = [
    "${var.region}-a",
    "${var.region}-b", 
    "${var.region}-c"
  ]
  
  release_channel {
    channel = "REGULAR"
  }
  
  maintenance_policy {
    daily_maintenance_window {
      start_time = "02:00"
    }
  }
  
  # Enable essential features
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }
  
  network_policy {
    enabled = true
  }
  
  # Remove default node pool
  remove_default_node_pool = true
  initial_node_count       = 1
  
  # Enable network endpoint groups for better load balancing
  addons_config {
    gce_persistent_disk_csi_driver_config {
      enabled = true
    }
    
    network_policy_config {
      disabled = false
    }
  }
}

# Separate node pools for different workload types
resource "google_container_node_pool" "h100_training" {
  name       = "h100-training-pool"
  cluster    = google_container_cluster.ml_training.name
  location   = var.region
  
  # Start with minimum nodes
  initial_node_count = 1
  
  autoscaling {
    min_node_count = 0
    max_node_count = 10
  }
  
  # Critical: Disable auto-upgrade and auto-repair during training
  management {
    auto_repair  = false
    auto_upgrade = false
  }
  
  upgrade_settings {
    max_surge       = 0
    max_unavailable = 0
  }
  
  node_config {
    machine_type = "a3-highgpu-8g"
    
    guest_accelerator {
      type  = "nvidia-h100-80gb"
      count = 8
    }
    
    local_ssd_count = 16
    disk_size_gb   = 500
    disk_type      = "pd-ssd"
    
    # Use custom service account
    service_account = google_service_account.gke_nodes.email
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]
    
    # Optimize for ML workloads
    kubelet_config {
      cpu_manager_policy   = "static"
      cpu_cfs_quota        = true
      cpu_cfs_quota_period = "100ms"
    }
    
    linux_node_config {
      sysctls = {
        "net.core.rmem_max"        = "134217728"
        "net.core.wmem_max"        = "134217728" 
        "net.ipv4.tcp_rmem"        = "4096 87380 134217728"
        "net.ipv4.tcp_wmem"        = "4096 65536 134217728"
        "net.core.netdev_max_backlog" = "30000"
      }
    }
    
    # GPU optimization
    labels = {
      "workload-type" = "gpu-training"
      "gpu-type"      = "h100"
    }
    
    taint {
      key    = "nvidia.com/gpu"
      value  = "h100"
      effect = "NO_SCHEDULE"
    }
  }
}

# Separate pool for system workloads
resource "google_container_node_pool" "system" {
  name     = "system-pool"
  cluster  = google_container_cluster.ml_training.name
  location = var.region
  
  initial_node_count = 1
  
  autoscaling {
    min_node_count = 1
    max_node_count = 5
  }
  
  # System pool can have auto-upgrade enabled
  management {
    auto_repair  = true
    auto_upgrade = true
  }
  
  node_config {
    machine_type = "e2-standard-4"
    disk_size_gb = 100
    
    service_account = google_service_account.gke_nodes.email
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]
    
    labels = {
      "workload-type" = "system"
    }
  }
}
```

## Protection Scripts

```bash
#!/bin/bash
# training-protection.sh

# Function to enable maintenance exclusions
enable_training_protection() {
  local cluster_name=$1
  local region=$2
  local duration_days=${3:-30}
  
  local end_date=$(date -d "+${duration_days} days" -u +"%Y-%m-%dT%H:%M:%SZ")
  local start_date=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  
  echo "Enabling training protection until: $end_date"
  
  gcloud container clusters update $cluster_name \
    --region $region \
    --add-maintenance-exclusion-name "training-run-$(date +%s)" \
    --add-maintenance-exclusion-start "$start_date" \
    --add-maintenance-exclusion-end "$end_date" \
    --add-maintenance-exclusion-scope "NO_UPGRADES"
    
  # Also disable node pool auto-repair/upgrade
  for pool in $(gcloud container node-pools list --cluster=$cluster_name --region=$region --format="value(name)"); do
    if [[ $pool == *"h100"* ]] || [[ $pool == *"training"* ]]; then
      echo "Disabling auto-management for pool: $pool"
      gcloud container node-pools update $pool \
        --cluster $cluster_name \
        --region $region \
        --no-enable-autorepair \
        --no-enable-autoupgrade
    fi
  done
}

# Function to create checkpoint before any maintenance
create_checkpoint_snapshot() {
  local namespace=${1:-default}
  
  kubectl create job checkpoint-backup-$(date +%s) \
    --from=cronjob/training-checkpoint \
    -n $namespace
    
  # Wait for checkpoint to complete
  kubectl wait --for=condition=complete \
    job/checkpoint-backup-$(date +%s) \
    --timeout=1800s -n $namespace
}

# Usage
enable_training_protection "ml-training-cluster" "us-central1" 45
```

## Security and Monitoring

```yaml
# monitoring.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: monitoring-config
data:
  prometheus.yml: |
    global:
      scrape_interval: 15s
    
    scrape_configs:
    - job_name: 'gpu-metrics'
      kubernetes_sd_configs:
      - role: pod
      relabel_configs:
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
        action: keep
        regex: true
      - source_labels: [__meta_kubernetes_pod_label_workload_type]
        action: keep
        regex: gpu-training

---
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule  
metadata:
  name: training-alerts
spec:
  groups:
  - name: training.rules
    rules:
    - alert: TrainingJobStuck
      expr: increase(training_steps_completed[10m]) == 0
      for: 10m
      annotations:
        summary: "Training job appears stuck"
        
    - alert: NodeMaintenanceScheduled
      expr: kube_node_spec_unschedulable == 1
      annotations:
        summary: "Node maintenance detected - checkpoint immediately"
```

## Key Recommendations

1. **Release Channel**: Use `REGULAR` for balance of stability and security updates

2. **Node Pool Strategy**:
   - Separate GPU pools from system pools
   - Disable auto-upgrade on training pools
   - Use surge upgrades when you do upgrade

3. **Maintenance Windows**:
   - Set maintenance exclusions during training runs
   - Use narrow maintenance windows (2-4 AM)
   - Plan upgrades around training schedules

4. **Checkpointing Strategy**:
   - Checkpoint every 15-30 minutes to local SSD
   - Sync to persistent storage every few hours
   - Test restore procedures regularly

5. **Monitoring**:
   - Monitor training progress
   - Alert on node maintenance events
   - Track GPU utilization and health

This configuration prioritizes workload stability while maintaining security through controlled, planned upgrades rather than automatic ones.
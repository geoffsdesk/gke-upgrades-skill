Here's a comprehensive GKE configuration strategy for stable foundation model training with H100 GPUs:

## Release Channel & Version Strategy

```yaml
# terraform/gke-cluster.tf
resource "google_container_cluster" "ml_training_cluster" {
  name     = "h100-training-cluster"
  location = var.region
  
  # Use REGULAR channel for predictable updates
  release_channel {
    channel = "REGULAR"
  }
  
  # Pin to specific version initially
  min_master_version = "1.28.3-gke.1203001"  # Example stable version
  
  # Maintenance configuration
  maintenance_policy {
    recurring_window {
      start_time = "2023-01-01T09:00:00Z"  # Sunday 9 AM UTC
      end_time   = "2023-01-01T17:00:00Z"  # Sunday 5 PM UTC
      recurrence = "FREQ=WEEKLY;BYDAY=SU"
    }
  }
  
  # Disable automatic upgrades initially
  node_config {
    machine_type = "e2-medium"  # Default pool, will be replaced
  }
  
  # Remove default node pool
  remove_default_node_pool = true
  initial_node_count       = 1
}
```

## Multi-Tier Node Pool Strategy

```yaml
# High-priority training nodes (upgrade-protected)
resource "google_container_node_pool" "h100_training_nodes" {
  name       = "h100-training-pool"
  location   = var.region
  cluster    = google_container_cluster.ml_training_cluster.name
  
  # Manual upgrade control
  management {
    auto_repair  = false  # Disable during training
    auto_upgrade = false  # Manual control only
  }
  
  # Surge settings for controlled upgrades
  upgrade_settings {
    strategy = "SURGE"
    max_surge = 1
    max_unavailable = 0  # Never remove nodes during upgrade
  }
  
  node_config {
    machine_type = "a3-highgpu-8g"  # H100 x8
    
    # GPU configuration
    guest_accelerator {
      type  = "nvidia-h100-80gb"
      count = 8
      gpu_driver_installation_config {
        gpu_driver_version = "INSTALLATION_DISABLED"  # Use custom drivers
      }
    }
    
    # Large boot disk for models/checkpoints
    disk_size_gb = 2000
    disk_type    = "pd-ssd"
    
    # Networking
    preemptible = false
    spot        = false
    
    # Security
    service_account = google_service_account.gke_nodes.email
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]
    
    # Labels for workload targeting
    labels = {
      "workload-type" = "training"
      "gpu-type"      = "h100"
      "tier"          = "critical"
    }
    
    # Taints to dedicated nodes
    taint {
      key    = "training-workload"
      value  = "true"
      effect = "NO_SCHEDULE"
    }
  }
  
  # Fixed size during training periods
  autoscaling {
    min_node_count = 4
    max_node_count = 8
  }
  
  # Placement policy for optimal networking
  placement_policy {
    type = "COMPACT"  # Minimize network latency
  }
}

# Inference/serving nodes (can be upgraded more frequently)
resource "google_container_node_pool" "inference_nodes" {
  name     = "inference-pool"
  location = var.region
  cluster  = google_container_cluster.ml_training_cluster.name
  
  management {
    auto_repair  = true
    auto_upgrade = true  # Allow automatic updates
  }
  
  upgrade_settings {
    strategy = "BLUE_GREEN"
    blue_green_settings {
      standard_rollout_policy {
        batch_node_count    = 1
        batch_soak_duration = "300s"
      }
      node_pool_soak_duration = "1800s"
    }
  }
  
  node_config {
    machine_type = "a2-highgpu-1g"  # A100 for inference
    
    guest_accelerator {
      type  = "nvidia-tesla-a100"
      count = 1
    }
    
    labels = {
      "workload-type" = "inference"
      "tier"          = "standard"
    }
  }
  
  autoscaling {
    min_node_count = 1
    max_node_count = 10
  }
}
```

## Maintenance and Update Controls

```yaml
# Custom maintenance exclusions
resource "google_container_cluster" "ml_training_cluster" {
  # ... previous config ...
  
  # Exclude critical training periods
  maintenance_policy {
    recurring_window {
      start_time = "2023-01-01T02:00:00Z"
      end_time   = "2023-01-01T06:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SU"
    }
    
    # Exclude major conference deadlines, etc.
    maintenance_exclusion {
      exclusion_name = "neurips-deadline"
      start_time     = "2024-05-15T00:00:00Z"
      end_time       = "2024-05-22T23:59:59Z"
      exclusion_scope = "NO_UPGRADES"
    }
  }
  
  # Network policy for security
  network_policy {
    enabled = true
    provider = "CALICO"
  }
  
  # Workload Identity for secure pod access
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }
}
```

## Training Job Protection Strategy

```yaml
# priorityclass.yaml
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: training-critical
value: 1000000
globalDefault: false
description: "Critical training workloads - highest priority"
---
# training-job.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: foundation-model-training
  labels:
    workload-type: training-critical
spec:
  parallelism: 4
  template:
    spec:
      priorityClassName: training-critical
      
      # Node selection for training pool
      nodeSelector:
        workload-type: training
        gpu-type: h100
      
      tolerations:
      - key: training-workload
        operator: Equal
        value: "true"
        effect: NoSchedule
      
      # Anti-affinity for fault tolerance
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              labelSelector:
                matchLabels:
                  app: foundation-model-training
              topologyKey: kubernetes.io/hostname
      
      containers:
      - name: trainer
        image: gcr.io/your-project/training:latest
        resources:
          requests:
            nvidia.com/gpu: 8
            memory: "800Gi"
            cpu: "240"
          limits:
            nvidia.com/gpu: 8
            memory: "800Gi"
            cpu: "240"
        
        # Checkpoint saving configuration
        env:
        - name: CHECKPOINT_INTERVAL
          value: "3600"  # Save every hour
        - name: CHECKPOINT_PATH
          value: "/checkpoints"
        
        volumeMounts:
        - name: checkpoint-storage
          mountPath: /checkpoints
        - name: shared-memory
          mountPath: /dev/shm
      
      volumes:
      - name: checkpoint-storage
        persistentVolumeClaim:
          claimName: training-checkpoints
      - name: shared-memory
        emptyDir:
          medium: Memory
          sizeLimit: 100Gi
      
      restartPolicy: Never
```

## Monitoring and Alerting

```yaml
# monitoring.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: training-alerts
spec:
  groups:
  - name: training-protection
    rules:
    - alert: TrainingNodeUpgradeScheduled
      expr: |
        kube_node_info{node=~".*training.*"} 
        * on(node) 
        kube_node_status_condition{condition="Ready", status="false"}
      for: 5m
      annotations:
        summary: "Training node may be upgrading"
        
    - alert: TrainingJobInterrupted
      expr: |
        kube_job_status_failed{job_name=~".*training.*"} > 0
      for: 1m
      annotations:
        summary: "Training job has failed - check for node disruptions"
```

## Operational Procedures

```bash
#!/bin/bash
# scripts/safe-upgrade.sh

# Pre-upgrade checklist
check_training_jobs() {
    echo "Checking for active training jobs..."
    kubectl get jobs -l workload-type=training-critical -o json | \
    jq -r '.items[] | select(.status.active > 0) | .metadata.name'
}

# Controlled node pool upgrade
upgrade_training_nodes() {
    local pool_name=$1
    
    # Check for active training
    active_jobs=$(check_training_jobs)
    if [[ -n "$active_jobs" ]]; then
        echo "Active training detected: $active_jobs"
        echo "Aborting upgrade. Reschedule during maintenance window."
        exit 1
    fi
    
    # Drain nodes one by one
    nodes=$(kubectl get nodes -l workload-type=training --no-headers -o name)
    for node in $nodes; do
        echo "Draining $node..."
        kubectl drain $node --ignore-daemonsets --delete-emptydir-data --timeout=600s
        
        # Wait for node to be upgraded
        kubectl wait --for=condition=Ready $node --timeout=1800s
        
        echo "Node $node ready. Proceeding to next node..."
        sleep 60
    done
}

# Emergency procedures
pause_all_upgrades() {
    echo "Pausing all automatic upgrades..."
    gcloud container node-pools update h100-training-pool \
        --cluster=h100-training-cluster \
        --region=us-central1 \
        --no-enable-autoupgrade \
        --no-enable-autorepair
}
```

## Key Recommendations

1. **Phased Rollout**: Start with REGULAR channel, move to STABLE after initial validation
2. **Dedicated Pools**: Separate training and inference workloads completely  
3. **Manual Control**: Disable auto-upgrades on training nodes during active runs
4. **Checkpoint Strategy**: Implement frequent checkpointing with preemption handling
5. **Monitoring**: Alert on any node condition changes during training
6. **Maintenance Windows**: Align with your training schedule (weekends/between experiments)

This configuration provides maximum stability for training runs while maintaining security through controlled, manual updates during safe periods.
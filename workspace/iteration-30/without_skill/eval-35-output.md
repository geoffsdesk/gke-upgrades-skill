Here's a comprehensive strategy for a resilient GKE cluster optimized for long-running H100 training workloads:

## Release Channel & Version Strategy

```yaml
# terraform/cluster.tf
resource "google_container_cluster" "ml_training" {
  name     = "h100-training-cluster"
  location = var.region
  
  # Use Regular channel for stability with security patches
  release_channel {
    channel = "REGULAR"
  }
  
  # Enable version pinning capability
  min_master_version = "1.28.3-gke.1286000"  # Pin to specific patch
  
  # Critical: Enable maintenance exclusions
  maintenance_policy {
    recurring_window {
      start_time = "2024-01-01T02:00:00Z"
      end_time   = "2024-01-01T06:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SU"
    }
    
    # Block upgrades during typical training periods
    maintenance_exclusion {
      exclusion_name = "training-season-1"
      start_time     = "2024-02-01T00:00:00Z"
      end_time       = "2024-04-30T23:59:59Z"
      exclusion_options {
        scope = "NO_UPGRADES"
      }
    }
  }
}
```

## Multi-Pool Node Strategy

```yaml
# Dedicated H100 training pool - maximum stability
resource "google_container_node_pool" "h100_training" {
  name       = "h100-training-stable"
  cluster    = google_container_cluster.ml_training.name
  location   = var.region
  
  # Fixed version, manual upgrades only
  version = "1.28.3-gke.1286000"
  
  node_config {
    machine_type = "a3-highgpu-8g"  # 8x H100 80GB
    
    guest_accelerator {
      type  = "nvidia-h100-80gb"
      count = 8
      gpu_driver_installation_config {
        gpu_driver_version = "LATEST"
      }
    }
    
    # Optimize for training workloads
    disk_size_gb = 1000
    disk_type    = "pd-ssd"
    
    # Dedicated nodes for isolation
    taint {
      key    = "training.ai/h100"
      value  = "true"
      effect = "NO_SCHEDULE"
    }
    
    labels = {
      "workload-type" = "training"
      "gpu-type"      = "h100"
      "stability"     = "maximum"
    }
    
    # Enhanced security
    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }
  }
  
  # Critical: Disable auto-upgrades
  management {
    auto_repair  = true   # Keep repair for hardware issues
    auto_upgrade = false  # Never auto-upgrade training nodes
  }
  
  # Surge upgrade settings for manual upgrades
  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
    strategy        = "SURGE"
    
    blue_green_settings {
      standard_rollout_policy {
        batch_percentage    = 0.1  # Very gradual rollouts
        batch_node_count    = 1
        batch_soak_duration = "3600s"
      }
      node_pool_soak_duration = "7200s"
    }
  }
  
  autoscaling {
    min_node_count = 1
    max_node_count = 10
  }
}

# Utility pool for supporting services
resource "google_container_node_pool" "utility" {
  name     = "utility-pool"
  cluster  = google_container_cluster.ml_training.name
  location = var.region
  
  # Allow auto-upgrades for utility workloads
  management {
    auto_repair  = true
    auto_upgrade = true
  }
  
  node_config {
    machine_type = "c2-standard-16"
    labels = {
      "workload-type" = "utility"
    }
  }
  
  autoscaling {
    min_node_count = 2
    max_node_count = 10
  }
}
```

## Training Job Protection Strategy

```yaml
# training-job.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: foundation-model-training
  annotations:
    # Prevent disruption
    cluster-autoscaler.kubernetes.io/safe-to-evict: "false"
spec:
  backoffLimit: 3
  template:
    metadata:
      annotations:
        cluster-autoscaler.kubernetes.io/safe-to-evict: "false"
    spec:
      # Pin to stable training nodes
      nodeSelector:
        workload-type: training
        gpu-type: h100
      
      tolerations:
      - key: "training.ai/h100"
        operator: "Equal"
        value: "true"
        effect: "NoSchedule"
      
      # Prevent preemption
      priorityClassName: training-priority
      
      # Anti-affinity for multi-node training
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              labelSelector:
                matchLabels:
                  job-name: foundation-model-training
              topologyKey: kubernetes.io/hostname
      
      containers:
      - name: trainer
        image: gcr.io/project/training:latest
        resources:
          requests:
            nvidia.com/gpu: 8
            cpu: "120"
            memory: "800Gi"
          limits:
            nvidia.com/gpu: 8
            cpu: "120"
            memory: "800Gi"
        
        # Checkpointing configuration
        env:
        - name: CHECKPOINT_FREQUENCY
          value: "100"  # Checkpoint every 100 steps
        - name: CHECKPOINT_PATH
          value: "/mnt/checkpoints"
        
        volumeMounts:
        - name: checkpoint-storage
          mountPath: /mnt/checkpoints
        - name: training-data
          mountPath: /mnt/data
          readOnly: true
      
      volumes:
      - name: checkpoint-storage
        persistentVolumeClaim:
          claimName: training-checkpoints
      - name: training-data
        persistentVolumeClaim:
          claimName: training-data
---
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: training-priority
value: 1000
globalDefault: false
description: "High priority for training workloads"
```

## Operational Safety Measures

```bash
#!/bin/bash
# scripts/safe-upgrade.sh

# Pre-upgrade safety checks
check_training_jobs() {
    echo "Checking for active training jobs..."
    ACTIVE_JOBS=$(kubectl get jobs -l workload-type=training --field-selector status.successful=0 -o name | wc -l)
    
    if [ "$ACTIVE_JOBS" -gt 0 ]; then
        echo "WARNING: $ACTIVE_JOBS active training jobs found!"
        kubectl get jobs -l workload-type=training --field-selector status.successful=0
        read -p "Continue with upgrade? (y/N): " -n 1 -r
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

# Cordoned upgrade process
safe_node_upgrade() {
    local NODE_POOL=$1
    local NODES=$(kubectl get nodes -l cloud.google.com/gke-nodepool=$NODE_POOL -o name)
    
    for node in $NODES; do
        echo "Upgrading $node..."
        
        # Check for training pods
        TRAINING_PODS=$(kubectl get pods --field-selector spec.nodeName=${node#node/} -l workload-type=training -o name | wc -l)
        
        if [ "$TRAINING_PODS" -gt 0 ]; then
            echo "Training pods found on $node, skipping..."
            continue
        fi
        
        # Cordon and drain
        kubectl cordon $node
        kubectl drain $node --ignore-daemonsets --delete-emptydir-data --timeout=600s
        
        # Trigger node pool upgrade for this specific node
        gcloud container operations wait \
            $(gcloud container clusters upgrade $CLUSTER_NAME \
                --node-pool=$NODE_POOL \
                --cluster-version=$TARGET_VERSION \
                --zone=$ZONE \
                --async --format="value(name)")
        
        # Wait and uncordon
        kubectl wait --for=condition=Ready node/$node --timeout=300s
        kubectl uncordon $node
        
        # Soak time
        echo "Soaking for 300 seconds..."
        sleep 300
    done
}
```

## Monitoring & Alerting

```yaml
# monitoring/training-alerts.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: training-protection-alerts
spec:
  groups:
  - name: training.protection
    rules:
    - alert: TrainingJobDisrupted
      expr: |
        increase(kube_job_status_failed{job_name=~".*training.*"}[5m]) > 0
      for: 0m
      labels:
        severity: critical
      annotations:
        summary: "Training job {{ $labels.job_name }} failed"
        description: "Training job may have been disrupted by cluster operations"
    
    - alert: NodeUpgradeWithTrainingPods
      expr: |
        kube_node_status_condition{condition="Ready",status="false"} 
        and on(node) kube_pod_info{pod=~".*training.*"}
      for: 2m
      labels:
        severity: warning
      annotations:
        summary: "Node upgrade affecting training workload"
    
    - alert: GPUUtilizationDrop
      expr: |
        avg_over_time(DCGM_FI_DEV_GPU_UTIL[5m]) < 80 
        and 
        avg_over_time(DCGM_FI_DEV_GPU_UTIL[1h] offset 1h) > 90
      for: 10m
      labels:
        severity: warning
      annotations:
        summary: "Significant GPU utilization drop detected"
```

## Key Operational Guidelines

1. **Training Season Planning**: Schedule maintenance exclusions around known training periods
2. **Manual Upgrade Only**: Keep training nodes on manual upgrade with thorough pre-checks
3. **Checkpoint Frequently**: Implement robust checkpointing every few minutes of training time
4. **Node Pool Separation**: Isolate training workloads from cluster management operations
5. **Version Pinning**: Pin both cluster and node versions during active training
6. **Monitoring**: Set up alerts for job failures, node issues, and GPU utilization drops

This configuration provides maximum protection for long-running training jobs while maintaining security through controlled, manual updates of critical components.
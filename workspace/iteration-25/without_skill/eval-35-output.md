Here's a production-ready GKE configuration optimized for long-running ML training with minimal disruption:

## Cluster Configuration

```yaml
# cluster-config.yaml
apiVersion: container.cnx.cloud.google.com/v1beta1
kind: Cluster
metadata:
  name: ml-training-cluster
spec:
  location: us-central1-a  # Single zone for GPU availability
  
  # Release Channel - Critical for ML workloads
  releaseChannel:
    channel: REGULAR  # Balance of stability and security patches
  
  # Maintenance Policy - Protect training runs
  maintenancePolicy:
    window:
      dailyMaintenanceWindow:
        startTime: "02:00"  # Low activity window
    maintenanceExclusions:
      - name: "training-protection"
        startTime: "2024-01-01T00:00:00Z"
        endTime: "2024-12-31T23:59:59Z"
        scope: "NO_UPGRADES"  # Block automatic upgrades
  
  # Network configuration
  network: projects/PROJECT_ID/global/networks/ml-vpc
  subnetwork: projects/PROJECT_ID/regions/us-central1/subnetworks/ml-subnet
  
  # Security hardening
  networkPolicy:
    enabled: true
  
  workloadIdentityConfig:
    workloadPool: PROJECT_ID.svc.id.goog
  
  # Logging optimized for ML
  loggingConfig:
    componentConfig:
      enableComponents:
      - "SYSTEM_COMPONENTS"
      - "WORKLOADS"  # Capture training logs
  
  monitoringConfig:
    componentConfig:
      enableComponents:
      - "SYSTEM_COMPONENTS"
      - "DCGM"  # GPU monitoring
```

## Node Pool Strategy

```yaml
# training-nodepool.yaml
apiVersion: container.cnx.cloud.google.com/v1beta1
kind: NodePool
metadata:
  name: h100-training-pool
spec:
  cluster: ml-training-cluster
  
  # Node configuration
  config:
    machineType: a3-highgpu-8g  # 8x H100 GPUs
    accelerators:
    - acceleratorCount: 8
      acceleratorType: nvidia-h100-80gb
      gpuPartitionSize: "1g.10gb"  # Adjust based on model size
    
    diskSizeGb: 1000
    diskType: pd-ssd
    
    # Preemptible: false for training workloads
    preemptible: false
    spot: false
    
    # OS and container runtime
    imageType: COS_CONTAINERD
    
    # Resource reservations
    reservationAffinity:
      consumeReservationType: SPECIFIC_RESERVATION
      key: "compute.googleapis.com/reservation-name"
      values: ["h100-reservation"]
  
  # Autoscaling - Conservative for training
  autoscaling:
    enabled: true
    minNodeCount: 2  # Minimum for redundancy
    maxNodeCount: 10
    
  # Management settings - Critical for training protection
  management:
    autoUpgrade: false  # Manual control over upgrades
    autoRepair: true    # Keep for hardware issues
  
  # Upgrade settings
  upgradeSettings:
    maxSurge: 1
    maxUnavailable: 0  # Never reduce capacity during upgrades
    strategy: SURGE     # Add nodes before removing old ones
  
  # Node taints for dedicated GPU usage
  nodeConfig:
    taints:
    - key: "nvidia.com/gpu"
      value: "true"
      effect: NO_SCHEDULE
```

## CPU Node Pool for System Workloads

```yaml
# system-nodepool.yaml
apiVersion: container.cnx.cloud.google.com/v1beta1
kind: NodePool
metadata:
  name: system-pool
spec:
  cluster: ml-training-cluster
  
  config:
    machineType: n2-standard-4
    diskSizeGb: 100
    diskType: pd-standard
    
    # Allow preemptible for non-critical workloads
    preemptible: true
  
  autoscaling:
    enabled: true
    minNodeCount: 1
    maxNodeCount: 5
  
  management:
    autoUpgrade: false  # Consistent with training pool
    autoRepair: true
```

## Training Job Configuration

```yaml
# training-job.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: foundation-model-training
spec:
  parallelism: 2  # Multi-node training
  backoffLimit: 3
  
  template:
    spec:
      # Node selection
      nodeSelector:
        cloud.google.com/gke-nodepool: h100-training-pool
      
      # Tolerate GPU taints
      tolerations:
      - key: "nvidia.com/gpu"
        operator: "Equal"
        value: "true"
        effect: "NoSchedule"
      
      # Anti-affinity for multi-node jobs
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
          - labelSelector:
              matchLabels:
                job-name: foundation-model-training
            topologyKey: kubernetes.io/hostname
      
      containers:
      - name: training
        image: gcr.io/PROJECT_ID/training:latest
        
        resources:
          requests:
            nvidia.com/gpu: 8
            memory: "400Gi"
            cpu: "48"
          limits:
            nvidia.com/gpu: 8
            memory: "400Gi"
            cpu: "48"
        
        # Checkpoint persistence
        volumeMounts:
        - name: checkpoint-storage
          mountPath: /checkpoints
        - name: dataset-storage
          mountPath: /data
        
        env:
        - name: NCCL_DEBUG
          value: "INFO"
        - name: CUDA_VISIBLE_DEVICES
          value: "0,1,2,3,4,5,6,7"
      
      volumes:
      - name: checkpoint-storage
        persistentVolumeClaim:
          claimName: checkpoint-pvc
      - name: dataset-storage
        persistentVolumeClaim:
          claimName: dataset-pvc
      
      # Prevent eviction
      priorityClassName: high-priority
      
      restartPolicy: Never
```

## Operational Safeguards

```yaml
# priority-class.yaml
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: high-priority
value: 1000000
globalDefault: false
description: "High priority for training workloads"

---
# pod-disruption-budget.yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-pdb
spec:
  minAvailable: 1
  selector:
    matchLabels:
      workload-type: training
```

## Terraform Configuration

```hcl
# main.tf
resource "google_container_cluster" "ml_training" {
  name     = "ml-training-cluster"
  location = "us-central1-a"
  
  # Disable default node pool
  remove_default_node_pool = true
  initial_node_count       = 1
  
  # Release channel
  release_channel {
    channel = "REGULAR"
  }
  
  # Maintenance policy
  maintenance_policy {
    daily_maintenance_window {
      start_time = "02:00"
    }
  }
  
  # Network security
  network_policy {
    enabled = true
  }
  
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }
  
  # Resource usage export
  resource_usage_export_config {
    enable_network_egress_metering = true
    enable_resource_consumption_metering = true
    
    bigquery_destination {
      dataset_id = "gke_usage"
    }
  }
  
  # Vertical Pod Autoscaling
  vertical_pod_autoscaling {
    enabled = false  # Disable for training workloads
  }
}

# GPU node pool
resource "google_container_node_pool" "h100_pool" {
  cluster  = google_container_cluster.ml_training.name
  location = google_container_cluster.ml_training.location
  name     = "h100-training-pool"
  
  # Manual scaling for predictable resources
  autoscaling {
    min_node_count = 2
    max_node_count = 10
  }
  
  management {
    auto_repair  = true
    auto_upgrade = false  # Manual control
  }
  
  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
    strategy        = "SURGE"
  }
  
  node_config {
    machine_type = "a3-highgpu-8g"
    
    guest_accelerator {
      type  = "nvidia-h100-80gb"
      count = 8
    }
    
    disk_size_gb = 1000
    disk_type    = "pd-ssd"
    
    # Security
    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }
    
    workload_metadata_config {
      mode = "GKE_METADATA"
    }
    
    taint {
      key    = "nvidia.com/gpu"
      value  = "true"
      effect = "NO_SCHEDULE"
    }
  }
}
```

## Monitoring and Alerting

```yaml
# monitoring.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: gpu-monitoring
data:
  dcgm-exporter.yaml: |
    collectors:
    - name: "default"
      interval: 30s
      metrics:
      - DCGM_FI_DEV_GPU_UTIL
      - DCGM_FI_DEV_MEM_COPY_UTIL  
      - DCGM_FI_DEV_GPU_TEMP
      - DCGM_FI_DEV_POWER_USAGE

---
# Alert for training job failures
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: training-alerts
spec:
  groups:
  - name: training.rules
    rules:
    - alert: TrainingJobFailed
      expr: kube_job_failed{job_name=~".*training.*"} > 0
      for: 5m
      labels:
        severity: critical
      annotations:
        summary: "Training job {{ $labels.job_name }} failed"
    
    - alert: GPUUtilizationLow
      expr: DCGM_FI_DEV_GPU_UTIL < 70
      for: 10m
      labels:
        severity: warning
      annotations:
        summary: "GPU utilization below 70% for 10 minutes"
```

## Key Recommendations:

1. **Manual Upgrade Control**: Disabled auto-upgrades on both cluster and node pools
2. **Maintenance Exclusions**: Use broad exclusion windows during training campaigns
3. **REGULAR Release Channel**: Balances security patches with stability
4. **Surge Upgrade Strategy**: Never reduces capacity during maintenance
5. **Reserved Instances**: Use commitments/reservations for cost optimization
6. **Multi-zone**: Consider multi-zone for production (with proper NCCL configuration)
7. **Checkpointing**: Implement robust checkpointing every 30-60 minutes
8. **Monitoring**: Comprehensive GPU and training job monitoring

This configuration provides maximum protection for long-running training while maintaining security through controlled, manual updates during planned maintenance windows.
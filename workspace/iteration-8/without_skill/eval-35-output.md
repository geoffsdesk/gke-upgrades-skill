Here's a production-ready configuration for your H100 GKE cluster optimized for long-running ML workloads:

## Cluster Configuration

```yaml
# cluster.yaml
apiVersion: container.v1
kind: Cluster
metadata:
  name: h100-training-cluster
spec:
  # Use REGULAR channel for balanced stability/security
  releaseChannel:
    channel: REGULAR
  
  # Configure maintenance windows
  maintenancePolicy:
    window:
      recurringWindow:
        window:
          startTime: "2024-01-07T06:00:00Z"  # Sunday 6 AM UTC
          endTime: "2024-01-07T10:00:00Z"    # 4-hour window
        recurrence: "FREQ=WEEKLY;BYDAY=SU"
    
    # Block automatic upgrades during training periods
    maintenanceExclusions:
      training-period-q1:
        startTime: "2024-02-01T00:00:00Z"
        endTime: "2024-04-30T23:59:59Z"
        scope: UPGRADES
  
  # Enable workload identity and security features
  workloadIdentityConfig:
    workloadPool: "PROJECT_ID.svc.id.goog"
  
  shieldedNodes:
    enabled: true
  
  # Network configuration for high-bandwidth training
  network: projects/PROJECT_ID/global/networks/ml-network
  subnetwork: projects/PROJECT_ID/regions/us-central1/subnetworks/h100-subnet
  
  # Enable network policy for security
  networkPolicy:
    enabled: true
    provider: CALICO
```

## Node Pool Strategy

```yaml
# training-nodepool.yaml
apiVersion: container.v1
kind: NodePool
metadata:
  name: h100-training-pool
spec:
  cluster: h100-training-cluster
  
  # Start with minimal nodes, scale as needed
  initialNodeCount: 0
  
  autoscaling:
    enabled: true
    minNodeCount: 0
    maxNodeCount: 10
    
  # GPU node configuration
  config:
    machineType: a3-highgpu-8g  # 8x H100 GPUs
    
    # Use spot instances for cost optimization (optional)
    spot: false  # Set to true for non-critical training
    
    # Optimize for training workloads
    diskSizeGb: 500
    diskType: pd-ssd
    
    # GPU configuration
    accelerators:
    - acceleratorCount: 8
      acceleratorType: nvidia-h100-80gb
      gpuDriverInstallationConfig:
        gpuDriverVersion: LATEST
    
    # Security and node management
    shieldedInstanceConfig:
      enableSecureBoot: true
      enableIntegrityMonitoring: true
    
    # Prevent automatic updates during training
    upgradeSettings:
      maxSurge: 0
      maxUnavailable: 1
      strategy: BLUE_GREEN
      blueGreenSettings:
        standardRolloutPolicy:
          batchNodeCount: 1
          batchSoakDuration: "300s"
    
    # Node labels for workload scheduling
    labels:
      workload-type: "training"
      gpu-type: "h100"
      
    # Taints to ensure only training workloads scheduled here
    taints:
    - key: "nvidia.com/gpu"
      value: "h100"
      effect: "NO_SCHEDULE"
```

## Inference Node Pool (Separate)

```yaml
# inference-nodepool.yaml
apiVersion: container.v1
kind: NodePool
metadata:
  name: inference-pool
spec:
  cluster: h100-training-cluster
  
  autoscaling:
    enabled: true
    minNodeCount: 1
    maxNodeCount: 5
    
  config:
    machineType: n1-standard-4
    
    # Allow more aggressive updates for inference nodes
    upgradeSettings:
      maxSurge: 2
      maxUnavailable: 0
      
    labels:
      workload-type: "inference"
```

## Training Job Configuration

```yaml
# training-job.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: foundation-model-training
spec:
  # Prevent job deletion on cluster updates
  ttlSecondsAfterFinished: 604800  # 7 days
  
  template:
    metadata:
      annotations:
        # Prevent eviction during upgrades
        cluster-autoscaler.kubernetes.io/safe-to-evict: "false"
    spec:
      # Schedule only on training nodes
      nodeSelector:
        workload-type: "training"
        
      tolerations:
      - key: "nvidia.com/gpu"
        operator: "Equal"
        value: "h100"
        effect: "NoSchedule"
      
      # Anti-disruption settings
      restartPolicy: Never
      
      containers:
      - name: training
        image: gcr.io/PROJECT_ID/training:latest
        
        resources:
          requests:
            nvidia.com/gpu: 8
            memory: "800Gi"
            cpu: "96"
          limits:
            nvidia.com/gpu: 8
            memory: "800Gi"
            cpu: "96"
            
        # Checkpoint frequently
        env:
        - name: CHECKPOINT_INTERVAL
          value: "3600"  # Every hour
        - name: CHECKPOINT_PATH
          value: "gs://training-checkpoints/model-v1"
```

## Cluster Upgrade Protection

```bash
#!/bin/bash
# upgrade-protection.sh

# Function to check for running training jobs
check_training_jobs() {
    kubectl get jobs -l workload-type=training --field-selector status.successful!=1 -o name | wc -l
}

# Function to add maintenance exclusion
add_maintenance_exclusion() {
    local start_date=$1
    local end_date=$2
    
    gcloud container clusters update h100-training-cluster \
        --zone us-central1-a \
        --add-maintenance-exclusion-end "$end_date" \
        --add-maintenance-exclusion-name "training-protection-$(date +%s)" \
        --add-maintenance-exclusion-start "$start_date" \
        --add-maintenance-exclusion-scope upgrades
}

# Auto-protect when training starts
if [ $(check_training_jobs) -gt 0 ]; then
    echo "Training jobs detected, adding maintenance exclusion"
    start_date=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    end_date=$(date -u -d "+30 days" +%Y-%m-%dT%H:%M:%SZ)
    add_maintenance_exclusion "$start_date" "$end_date"
fi
```

## Monitoring and Alerting

```yaml
# monitoring.yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: training-monitoring
spec:
  selector:
    matchLabels:
      app: training-job
  endpoints:
  - port: metrics
---
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: training-alerts
spec:
  groups:
  - name: training.rules
    rules:
    - alert: TrainingJobFailed
      expr: kube_job_status_failed > 0
      for: 5m
      labels:
        severity: critical
      annotations:
        summary: "Training job {{ $labels.job_name }} has failed"
        
    - alert: GPUUtilizationLow
      expr: DCGM_FI_DEV_GPU_UTIL < 80
      for: 10m
      labels:
        severity: warning
      annotations:
        summary: "GPU utilization is low on {{ $labels.instance }}"
```

## Key Recommendations:

1. **Release Channel**: Use REGULAR for balance of stability and security updates
2. **Maintenance Windows**: Set to low-usage periods with 4-hour windows
3. **Maintenance Exclusions**: Automatically block upgrades during training
4. **Node Pool Separation**: Separate pools for training vs. other workloads
5. **Anti-Disruption**: Use taints, node selectors, and PodDisruptionBudgets
6. **Checkpointing**: Frequent checkpoints to GCS for recovery
7. **Monitoring**: Comprehensive alerting for job health and resource utilization

This configuration provides maximum protection for long-running training jobs while maintaining security through controlled update windows.
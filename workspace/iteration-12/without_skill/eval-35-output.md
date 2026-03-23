Here's a production-ready GKE configuration optimized for long-running H100 training workloads:

## Cluster Configuration

```yaml
apiVersion: container.googleapis.com/v1
kind: Cluster
metadata:
  name: foundation-model-training
  location: us-central1-a  # Single zone for GPU availability
spec:
  releaseChannel:
    channel: REGULAR  # Balanced stability vs security updates
  
  # Maintenance configuration
  maintenancePolicy:
    window:
      dailyMaintenanceWindow:
        startTime: "02:00"  # Off-peak hours
      maintenanceExclusions:
        - name: "training-sprint-1"
          startTime: "2024-01-15T00:00:00Z"
          endTime: "2024-02-15T00:00:00Z"
          scope: NO_UPGRADES
  
  # Network configuration
  network: "projects/PROJECT/global/networks/ml-vpc"
  subnetwork: "projects/PROJECT/regions/us-central1/subnetworks/ml-subnet"
  
  # Enable workload identity and other security features
  workloadIdentityConfig:
    workloadPool: "PROJECT.svc.id.goog"
  
  # Cluster-level configurations
  networkPolicy:
    enabled: true
  
  addonsConfig:
    gkeBackupAgentConfig:
      enabled: true
```

## Node Pool Strategy

### Primary Training Node Pool (H100s)
```yaml
apiVersion: container.googleapis.com/v1
kind: NodePool
metadata:
  name: h100-training-pool
spec:
  cluster: foundation-model-training
  
  # Conservative node count - scale based on needs
  initialNodeCount: 4
  
  config:
    machineType: a3-highgpu-8g  # 8x H100 GPUs
    diskSizeGb: 200
    diskType: pd-ssd
    
    # GPU configuration
    accelerators:
    - acceleratorCount: 8
      acceleratorType: nvidia-h100-80gb
      gpuDriverInstallationConfig:
        gpuDriverVersion: LATEST
    
    # Taints to ensure only ML workloads run here
    taints:
    - key: nvidia.com/gpu
      value: h100
      effect: NO_SCHEDULE
    
    labels:
      workload-type: training
      gpu-type: h100
      
    # Enable preemptible for cost savings if acceptable
    preemptible: false  # Set true for 60-80% cost savings with risk
    
    # Workload Identity
    workloadMetadataConfig:
      mode: GKE_METADATA
  
  # Critical: Node management settings
  management:
    autoUpgrade: false  # Manual control for training stability
    autoRepair: true    # Keep for hardware issues
  
  # Upgrade settings for when you do upgrade
  upgradeSettings:
    maxSurge: 0
    maxUnavailable: 1
    strategy: SURGE
  
  # Autoscaling disabled initially - enable carefully
  autoscaling:
    enabled: false
```

### System Node Pool (CPU workloads)
```yaml
apiVersion: container.googleapis.com/v1
kind: NodePool
metadata:
  name: system-pool
spec:
  cluster: foundation-model-training
  initialNodeCount: 2
  
  config:
    machineType: n2-standard-4
    diskSizeGb: 100
    diskType: pd-standard
    
    labels:
      workload-type: system
  
  management:
    autoUpgrade: true   # System nodes can upgrade more frequently
    autoRepair: true
  
  autoscaling:
    enabled: true
    minNodeCount: 2
    maxNodeCount: 10
```

## Training Job Configuration

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: foundation-model-training
  namespace: ml-training
spec:
  backoffLimit: 3
  template:
    spec:
      # Node selection
      nodeSelector:
        workload-type: training
        gpu-type: h100
      
      tolerations:
      - key: nvidia.com/gpu
        operator: Equal
        value: h100
        effect: NoSchedule
      
      # Prevent eviction during cluster operations
      priority: 1000
      priorityClassName: training-priority
      
      restartPolicy: Never
      
      containers:
      - name: trainer
        image: gcr.io/PROJECT/training:latest
        
        resources:
          requests:
            nvidia.com/gpu: 8
            cpu: 32
            memory: 200Gi
            ephemeral-storage: 100Gi
          limits:
            nvidia.com/gpu: 8
            cpu: 32
            memory: 200Gi
        
        # Graceful shutdown handling
        lifecycle:
          preStop:
            exec:
              command: ["/bin/sh", "-c", "python save_checkpoint.py"]
        
        env:
        - name: CHECKPOINT_INTERVAL
          value: "3600"  # Checkpoint every hour
        
        volumeMounts:
        - name: model-data
          mountPath: /data
        - name: checkpoints
          mountPath: /checkpoints
        
      volumes:
      - name: model-data
        persistentVolumeClaim:
          claimName: training-data-pvc
      - name: checkpoints
        persistentVolumeClaim:
          claimName: checkpoints-pvc
```

## Priority Classes
```yaml
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: training-priority
value: 1000
globalDefault: false
description: "High priority for training workloads"
```

## Operational Recommendations

### 1. Maintenance Window Management
```bash
# Schedule maintenance exclusions around training runs
gcloud container clusters update foundation-model-training \
  --add-maintenance-exclusion-name="training-phase-2" \
  --add-maintenance-exclusion-start="2024-03-01T00:00:00Z" \
  --add-maintenance-exclusion-end="2024-03-31T23:59:59Z" \
  --add-maintenance-exclusion-scope="NO_UPGRADES"
```

### 2. Monitoring Setup
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: training-alerts
data:
  alerts.yml: |
    groups:
    - name: training.rules
      rules:
      - alert: TrainingJobDown
        expr: kube_job_status_failed{job_name=~"foundation-model.*"} > 0
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Training job failed"
      
      - alert: GPUUtilizationLow
        expr: DCGM_FI_DEV_GPU_UTIL < 80
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "GPU utilization below 80%"
```

### 3. Backup Strategy
```yaml
apiVersion: gkebackup.cnrm.cloud.google.com/v1beta1
kind: BackupPlan
metadata:
  name: training-backup-plan
spec:
  cluster: foundation-model-training
  location: us-central1
  
  backupSchedule:
    cronSchedule: "0 2 * * *"  # Daily at 2 AM
  
  backupConfig:
    includeVolumeData: true
    includeSecrets: true
    
    selectedApplications:
      namespacedNames:
      - namespace: ml-training
        name: "*"
```

## Key Operational Practices

1. **Before Training Starts:**
   - Set maintenance exclusions for your training duration
   - Validate checkpoint/resume functionality
   - Test node replacement scenarios

2. **During Training:**
   - Monitor via Cloud Logging and custom metrics
   - Keep maintenance exclusions updated
   - Regular checkpoint validation

3. **Security Updates:**
   - Use a staging cluster to test updates first
   - Plan security updates during natural break points
   - Consider blue-green node pool strategy for urgent updates

4. **Cost Optimization:**
   - Use committed use discounts for predictable workloads
   - Consider spot instances for fault-tolerant training
   - Right-size CPU node pools with autoscaling

This configuration prioritizes training stability while maintaining security through controlled updates and comprehensive monitoring.
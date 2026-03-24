Here's a comprehensive GKE configuration strategy for stable foundation model training with H100 GPUs:

## Cluster Configuration

```yaml
apiVersion: container.googleapis.com/v1
kind: Cluster
metadata:
  name: h100-training-cluster
spec:
  # Use Static GKE version - critical for training stability
  initialClusterVersion: "1.28.3-gke.1203001"  # Pin to specific patch
  
  # Release channel: None (manual upgrades only)
  releaseChannel:
    channel: UNSPECIFIED
  
  # Maintenance policy - tightly controlled windows
  maintenancePolicy:
    window:
      recurringWindow:
        window:
          startTime: "2024-01-07T06:00:00Z"  # Sunday 6 AM UTC
          endTime: "2024-01-07T10:00:00Z"    # 4-hour window
        recurrence: "FREQ=WEEKLY;BYDAY=SU"
    
    # Maintenance exclusions for planned training periods
    maintenanceExclusions:
      training-period-q1:
        startTime: "2024-01-15T00:00:00Z"
        endTime: "2024-03-15T23:59:59Z"
        scope: NO_UPGRADES
  
  # Network configuration
  networkConfig:
    network: "projects/PROJECT_ID/global/networks/training-vpc"
    subnetwork: "projects/PROJECT_ID/regions/us-central1/subnetworks/h100-subnet"
    enableIntraNodeVisibility: true
  
  # Security and monitoring
  networkPolicy:
    enabled: true
  
  monitoringService: "monitoring.googleapis.com/kubernetes"
  loggingService: "logging.googleapis.com/kubernetes"
  
  # Workload Identity for secure pod authentication
  workloadIdentityConfig:
    workloadPool: "PROJECT_ID.svc.id.goog"
```

## Node Pool Strategy

### Primary Training Node Pool (H100s)
```yaml
apiVersion: container.googleapis.com/v1
kind: NodePool
metadata:
  name: h100-training-primary
spec:
  cluster: h100-training-cluster
  
  # Static node version - no auto-upgrades
  version: "1.28.3-gke.1203001"
  
  # Manual upgrade strategy
  management:
    autoUpgrade: false
    autoRepair: true  # Keep repair for hardware issues
  
  # Node configuration
  config:
    machineType: "a3-highgpu-8g"  # 8x H100 80GB
    
    # GPU configuration
    guestAccelerator:
    - type: "nvidia-h100-80gb"
      count: 8
      gpuDriverInstallationConfig:
        gpuDriverVersion: "LATEST"  # Or pin to specific driver
    
    # Disk configuration for checkpoints
    diskSizeGb: 200
    diskType: "pd-ssd"
    
    # Additional local NVMe for fast I/O
    localSsdCount: 4
    
    # Taints to ensure only ML workloads schedule here
    taints:
    - key: "training.ai/h100"
      value: "true"
      effect: "NO_SCHEDULE"
    
    labels:
      workload-type: "training"
      gpu-type: "h100"
      node-pool: "primary"
    
    # Metadata for monitoring
    metadata:
      disable-legacy-endpoints: "true"
    
    # Security
    serviceAccount: "h100-training-sa@PROJECT_ID.iam.gserviceaccount.com"
    oauthScopes:
    - "https://www.googleapis.com/auth/cloud-platform"
    
    shieldedInstanceConfig:
      enableSecureBoot: true
      enableIntegrityMonitoring: true
  
  # Scaling configuration
  initialNodeCount: 4
  autoscaling:
    enabled: true
    minNodeCount: 2
    maxNodeCount: 16
    
  # Placement policy for optimal interconnect
  placementPolicy:
    type: "COMPACT"  # Keep nodes close for better GPU-to-GPU communication
```

### Backup Training Node Pool
```yaml
apiVersion: container.googleapis.com/v1
kind: NodePool
metadata:
  name: h100-training-backup
spec:
  cluster: h100-training-cluster
  
  # Identical config to primary but separate pool
  version: "1.28.3-gke.1203001"
  
  management:
    autoUpgrade: false
    autoRepair: true
  
  config:
    machineType: "a3-highgpu-8g"
    guestAccelerator:
    - type: "nvidia-h100-80gb"
      count: 8
    
    taints:
    - key: "training.ai/h100-backup"
      value: "true" 
      effect: "NO_SCHEDULE"
    
    labels:
      workload-type: "training"
      gpu-type: "h100"
      node-pool: "backup"
  
  # Start with 0 nodes, scale when needed
  initialNodeCount: 0
  autoscaling:
    enabled: true
    minNodeCount: 0
    maxNodeCount: 8
```

### System Node Pool
```yaml
apiVersion: container.googleapis.com/v1
kind: NodePool
metadata:
  name: system-pool
spec:
  cluster: h100-training-cluster
  
  # Can use a more recent version for system components
  version: "1.28.5-gke.1217001"
  
  management:
    autoUpgrade: false  # Still manual for consistency
    autoRepair: true
  
  config:
    machineType: "e2-standard-4"
    
    labels:
      workload-type: "system"
    
    # Taint to prevent training workloads
    taints:
    - key: "system-only"
      value: "true"
      effect: "NO_SCHEDULE"
  
  initialNodeCount: 3
  autoscaling:
    enabled: true
    minNodeCount: 3
    maxNodeCount: 6
```

## Critical Training Job Configuration

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: foundation-model-training
spec:
  template:
    spec:
      # Use backup pool as fallback
      affinity:
        nodeAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            preference:
              matchExpressions:
              - key: node-pool
                operator: In
                values: ["primary"]
          - weight: 50
            preference:
              matchExpressions:
              - key: node-pool
                operator: In
                values: ["backup"]
      
      # Tolerate training taints
      tolerations:
      - key: "training.ai/h100"
        operator: "Equal"
        value: "true"
        effect: "NO_SCHEDULE"
      - key: "training.ai/h100-backup"
        operator: "Equal"
        value: "true"
        effect: "NO_SCHEDULE"
      
      # Critical for training stability
      restartPolicy: Never
      
      containers:
      - name: training
        resources:
          requests:
            nvidia.com/gpu: 8
          limits:
            nvidia.com/gpu: 8
```

## Operational Strategy

### 1. **Upgrade Windows**
```bash
# Set maintenance exclusions before training
gcloud container clusters update h100-training-cluster \
  --add-maintenance-exclusion-name="training-run-march" \
  --add-maintenance-exclusion-start="2024-03-01T00:00:00Z" \
  --add-maintenance-exclusion-end="2024-03-31T23:59:59Z" \
  --add-maintenance-exclusion-scope="NO_UPGRADES"
```

### 2. **Emergency Node Pool Switching**
```bash
# Cordon primary pool if issues arise
kubectl cordon -l node-pool=primary

# Scale backup pool
gcloud container node-pools resize h100-training-backup \
  --cluster=h100-training-cluster \
  --num-nodes=4 \
  --zone=us-central1-a
```

### 3. **Monitoring Setup**
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: training-alerts
data:
  alerts.yaml: |
    groups:
    - name: training-stability
      rules:
      - alert: NodeUpgrade
        expr: increase(kube_node_info[5m]) > 0
        labels:
          severity: critical
        annotations:
          summary: "Node upgrade detected during training"
      
      - alert: GPUNodeDown
        expr: kube_node_status_condition{condition="Ready",status="false"} 
              and on(node) kube_node_labels{label_gpu_type="h100"}
        labels:
          severity: critical
```

### 4. **Security Updates Strategy**
- **Node OS**: Use Container-Optimized OS with automatic security updates enabled
- **Kubernetes**: Manual upgrades only during planned maintenance windows
- **Applications**: Update training images independently of infrastructure

## Key Protection Strategies

1. **No Release Channel**: Complete manual control over upgrades
2. **Dual Node Pools**: Seamless failover capability
3. **Maintenance Exclusions**: Block upgrades during training periods
4. **Version Pinning**: Consistent environment across all nodes
5. **Placement Policies**: Optimize for GPU interconnect performance
6. **Comprehensive Monitoring**: Early warning for any infrastructure changes

This configuration provides maximum stability while maintaining security through controlled, planned updates.
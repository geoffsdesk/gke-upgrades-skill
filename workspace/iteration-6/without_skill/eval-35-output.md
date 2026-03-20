Here's a comprehensive GKE configuration strategy for your H100-based foundation model training that balances stability with security:

## Cluster Configuration

```yaml
# cluster-config.yaml
apiVersion: container.googleapis.com/v1
kind: Cluster
metadata:
  name: h100-training-cluster
spec:
  releaseChannel:
    channel: REGULAR  # Balance of stability and security patches
  
  # Enable Autopilot for simplified management (if workload fits)
  # Or use Standard mode with careful node pool configuration
  
  maintenancePolicy:
    window:
      # Set maintenance windows during your typical model checkpoint intervals
      dailyMaintenanceWindow:
        startTime: "02:00"  # Adjust to your timezone
        duration: "4h"
    
    # Critical: Configure maintenance exclusions for training periods
    maintenanceExclusions:
      - name: "training-run-q1"
        startTime: "2024-01-15T00:00:00Z"
        endTime: "2024-02-15T00:00:00Z"
        scope: NO_UPGRADES
      
  # Network configuration for high-throughput training
  ipAllocationPolicy:
    useIpAliases: true
    clusterSecondaryRangeName: "pods"
    servicesSecondaryRangeName: "services"
  
  # Enable necessary features
  addonsConfig:
    gcePersistentDiskCsiDriverConfig:
      enabled: true
    gkeBackupAgentConfig:
      enabled: true
```

## Node Pool Strategy

```yaml
# training-node-pool.yaml
apiVersion: container.googleapis.com/v1
kind: NodePool
metadata:
  name: h100-training-pool
spec:
  # Use multiple smaller node pools vs one large pool
  initialNodeCount: 2
  
  nodeConfig:
    machineType: "a3-highgpu-8g"  # 8x H100 GPUs
    
    # Use Container-Optimized OS with containerd
    imageType: "COS_CONTAINERD"
    
    # Prevent automatic node upgrades during training
    upgradeSettings:
      strategy: "SURGE"
      maxSurge: 1
      maxUnavailable: 0
    
    # Reservations for cost optimization
    reservationAffinity:
      consumeReservationType: "SPECIFIC_RESERVATION"
      key: "h100-training-reservation"
    
    # Taints to ensure only ML workloads schedule here
    taints:
    - key: "nvidia.com/gpu"
      value: "h100"
      effect: "NO_SCHEDULE"
    
    # Local SSD for checkpointing
    localSsdCount: 16  # Adjust based on model size
    
    metadata:
      disable-legacy-endpoints: "true"
    
    oauthScopes:
    - "https://www.googleapis.com/auth/cloud-platform"

# Separate node pool for system workloads
---
apiVersion: container.googleapis.com/v1
kind: NodePool
metadata:
  name: system-pool
spec:
  initialNodeCount: 3
  nodeConfig:
    machineType: "n2-standard-4"
    imageType: "COS_CONTAINERD"
    preemptible: true  # Cost optimization for non-critical workloads
```

## Advanced Maintenance Configuration

```yaml
# maintenance-policy.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: maintenance-config
data:
  policy: |
    # Automated maintenance exclusions based on training jobs
    maintenance_exclusions:
      - pattern: "training-*"
        duration_weeks: 4
        auto_extend: true
        notification_channels:
          - "projects/PROJECT_ID/notificationChannels/CHANNEL_ID"
```

## Training Job Protection Setup

```bash
#!/bin/bash
# setup-training-protection.sh

# Create maintenance exclusion function
create_maintenance_exclusion() {
    local start_date=$1
    local duration_weeks=$2
    local job_name=$3
    
    local end_date=$(date -d "$start_date + $duration_weeks weeks" -Iso-8601)
    
    gcloud container clusters update h100-training-cluster \
        --maintenance-window-start "$start_date" \
        --maintenance-window-end "$end_date" \
        --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU" \
        --zone=us-central1-a
    
    # Set up monitoring
    gcloud alpha monitoring policies create \
        --policy-from-file=training-disruption-policy.yaml
}

# Node pool surge upgrade configuration
configure_surge_upgrades() {
    gcloud container node-pools update h100-training-pool \
        --cluster=h100-training-cluster \
        --max-surge=1 \
        --max-unavailable=0 \
        --zone=us-central1-a
}
```

## Workload Configuration for Resilience

```yaml
# training-job-template.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: foundation-model-training
  annotations:
    cluster-autoscaler.kubernetes.io/safe-to-evict: "false"
spec:
  template:
    metadata:
      annotations:
        # Prevent preemption during maintenance
        cluster-autoscaler.kubernetes.io/safe-to-evict: "false"
    spec:
      tolerations:
      - key: "nvidia.com/gpu"
        operator: "Equal"
        value: "h100"
        effect: "NoSchedule"
      
      nodeSelector:
        cloud.google.com/gke-nodepool: h100-training-pool
      
      # Pod disruption budget
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
          - labelSelector:
              matchLabels:
                app: foundation-model-training
            topologyKey: kubernetes.io/hostname
      
      containers:
      - name: trainer
        image: your-training-image
        resources:
          requests:
            nvidia.com/gpu: 8
          limits:
            nvidia.com/gpu: 8
        
        # Checkpoint configuration
        env:
        - name: CHECKPOINT_INTERVAL
          value: "3600"  # 1 hour
        - name: CHECKPOINT_PATH
          value: "/mnt/checkpoints"
        
        volumeMounts:
        - name: checkpoint-storage
          mountPath: /mnt/checkpoints
        - name: local-ssd
          mountPath: /tmp/training
      
      volumes:
      - name: checkpoint-storage
        persistentVolumeClaim:
          claimName: training-checkpoints
      - name: local-ssd
        hostPath:
          path: /mnt/disks/ssd0
```

## Monitoring and Alerting Setup

```yaml
# monitoring-config.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: training-protection-rules
spec:
  groups:
  - name: training.rules
    rules:
    - alert: MaintenanceWindowApproaching
      expr: |
        (gke_cluster_maintenance_window_start - time()) < 86400
      for: 1h
      labels:
        severity: warning
      annotations:
        summary: "Maintenance window starting in less than 24 hours"
        description: "Consider checkpointing training job {{ $labels.job_name }}"
    
    - alert: NodeUpgradeStarted
      expr: |
        increase(gke_node_upgrade_events_total[5m]) > 0
      labels:
        severity: critical
      annotations:
        summary: "Node upgrade detected during training"
```

## Best Practices Implementation

```bash
# pre-training-checklist.sh

# 1. Set maintenance exclusions
set_training_period_exclusions() {
    gcloud container clusters update h100-training-cluster \
        --clear-maintenance-window \
        --maintenance-window-start="$(date -d '+1 day' -Iso-8601)" \
        --maintenance-window-end="$(date -d '+30 days' -Iso-8601)"
}

# 2. Verify node pool stability
check_node_pool_versions() {
    gcloud container node-pools describe h100-training-pool \
        --cluster=h100-training-cluster \
        --format="value(version,status)"
}

# 3. Set up automated checkpointing
setup_checkpoint_automation() {
    kubectl apply -f - <<EOF
apiVersion: v1
kind: CronJob
metadata:
  name: checkpoint-trigger
spec:
  schedule: "0 */6 * * *"  # Every 6 hours
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: checkpoint
            image: google/cloud-sdk:slim
            command:
            - /bin/bash
            - -c
            - |
              # Send checkpoint signal to training pods
              kubectl get pods -l app=foundation-model-training \
                -o name | xargs -I {} kubectl exec {} -- kill -USR1 1
EOF
}
```

## Key Recommendations

1. **Release Channel**: Use `REGULAR` for H100 training - provides security updates without bleeding-edge instability
2. **Maintenance Windows**: Set 4-6 hour windows during natural checkpoint intervals
3. **Node Pools**: Separate GPU and CPU workloads, use surge upgrades with `maxUnavailable: 0`
4. **Monitoring**: Set up alerts 24-48 hours before maintenance windows
5. **Backup Strategy**: Automated checkpointing every 1-6 hours depending on training speed
6. **Cost Optimization**: Use committed use discounts and reservations for predictable multi-week runs

This configuration provides maximum protection for long-running training jobs while maintaining security compliance and operational flexibility.
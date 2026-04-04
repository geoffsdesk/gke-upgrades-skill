Here's a comprehensive strategy for a resilient GKE cluster optimized for long-running H100 training workloads:

## Release Channel & Maintenance Strategy

```yaml
# cluster-config.yaml
apiVersion: container.gke.io/v1beta1
kind: Cluster
metadata:
  name: ml-training-cluster
spec:
  releaseChannel:
    channel: STABLE  # More predictable than RAPID, more secure than REGULAR
  maintenancePolicy:
    window:
      dailyMaintenanceWindow:
        startTime: "02:00"  # Low-usage hours
      maintenanceExclusions:
        # Block maintenance during critical training periods
        - name: "training-sprint-q1"
          startTime: "2024-01-15T00:00:00Z"
          endTime: "2024-02-15T23:59:59Z"
          scope: NO_UPGRADES
    resourceVersion: ""
```

## Node Pool Architecture

```yaml
# Dedicated system node pool (always upgradeable)
systemNodePool:
  name: system-pool
  nodeConfig:
    machineType: n2-standard-8
    diskSizeGb: 100
    diskType: pd-ssd
    serviceAccount: gke-system-sa@project.iam.gserviceaccount.com
    oauthScopes:
      - https://www.googleapis.com/auth/cloud-platform
    labels:
      node-type: system
    taints:
      - key: system-only
        value: "true"
        effect: NO_SCHEDULE
  initialNodeCount: 3
  management:
    autoUpgrade: true
    autoRepair: true

# H100 training node pools (upgrade-protected)
h100NodePools:
  - name: h100-pool-a
    nodeConfig:
      machineType: a3-highgpu-8g  # 8x H100
      accelerators:
        - type: nvidia-h100-80gb
          count: 8
      diskSizeGb: 2000
      diskType: pd-ssd
      labels:
        node-type: training
        gpu-type: h100
        pool-generation: "a"
      taints:
        - key: training-only
          value: "true"
          effect: NO_SCHEDULE
    initialNodeCount: 4
    management:
      autoUpgrade: false  # Manual control for training nodes
      autoRepair: true    # Keep repair for hardware issues
    upgradeSettings:
      maxSurge: 1
      maxUnavailable: 0
```

## Cluster Configuration

```yaml
# Complete cluster setup
apiVersion: container.gke.io/v1beta1
kind: Cluster
spec:
  addonsConfig:
    gcePersistentDiskCsiDriverConfig:
      enabled: true
    networkPolicyConfig:
      disabled: false
    
  # Enhanced security without disrupting training
  workloadIdentityConfig:
    workloadPool: "PROJECT_ID.svc.id.goog"
  
  shieldedNodes:
    enabled: true
  
  # Network configuration for high-bandwidth training
  networkConfig:
    networkPolicy:
      enabled: true
    datapathProvider: ADVANCED_DATAPATH  # For better GPU networking
  
  # Monitoring and logging (essential for long runs)
  loggingConfig:
    componentConfig:
      enableComponents:
        - SYSTEM_COMPONENTS
        - WORKLOADS
        - API_AUDIT
  
  monitoringConfig:
    componentConfig:
      enableComponents:
        - SYSTEM_COMPONENTS
        - WORKLOADS
        - STORAGE
        - HPA
        - POD
        - DAEMONSET
        - DEPLOYMENT
        - STATEFULSET
```

## Training Workload Protection

```yaml
# training-job.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: foundation-model-training
  labels:
    app: training
    critical: "true"
spec:
  template:
    metadata:
      labels:
        app: training
        critical: "true"
    spec:
      # Ensure placement on training nodes only
      nodeSelector:
        node-type: training
        gpu-type: h100
      
      tolerations:
        - key: training-only
          operator: Equal
          value: "true"
          effect: NoSchedule
      
      # Prevent eviction during maintenance
      priorityClassName: training-critical
      
      # Graceful shutdown handling
      terminationGracePeriodSeconds: 300
      
      containers:
        - name: training
          image: gcr.io/project/training:latest
          resources:
            requests:
              nvidia.com/gpu: 8
              memory: 1000Gi
              cpu: 100
            limits:
              nvidia.com/gpu: 8
              memory: 1000Gi
          
          # Checkpoint frequently
          env:
            - name: CHECKPOINT_INTERVAL
              value: "1800"  # 30 minutes
            - name: CHECKPOINT_PATH
              value: "/mnt/checkpoints"
          
          volumeMounts:
            - name: checkpoints
              mountPath: /mnt/checkpoints
            - name: datasets
              mountPath: /mnt/data
      
      volumes:
        - name: checkpoints
          persistentVolumeClaim:
            claimName: training-checkpoints
        - name: datasets
          persistentVolumeClaim:
            claimName: training-data

---
# Critical priority class
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: training-critical
value: 1000000
globalDefault: false
description: "Critical training workloads that should not be evicted"
```

## Operational Safeguards

```bash
#!/bin/bash
# upgrade-protection.sh

# 1. Pre-training cluster lockdown
gcloud container clusters update ml-training-cluster \
    --maintenance-window-start "02:00" \
    --maintenance-window-end "04:00" \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"

# 2. Add maintenance exclusion for training period
gcloud container clusters update ml-training-cluster \
    --add-maintenance-exclusion-name "training-run-$(date +%Y%m%d)" \
    --add-maintenance-exclusion-start "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --add-maintenance-exclusion-end "$(date -u -d '+4 weeks' +%Y-%m-%dT%H:%M:%SZ)" \
    --add-maintenance-exclusion-scope "NO_UPGRADES"

# 3. Monitor for forced upgrades
kubectl create configmap cluster-monitoring --from-literal=script="
while true; do
  # Check for node upgrade events
  kubectl get events --field-selector reason=NodeUpgrade -o json | \
    jq '.items[] | select(.involvedObject.kind==\"Node\")' || echo 'No upgrade events'
  sleep 300
done
"
```

## Checkpoint and Recovery Strategy

```yaml
# checkpoint-storage.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: training-checkpoints
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Ti
  storageClassName: pd-ssd

---
# Automated checkpoint backup
apiVersion: batch/v1
kind: CronJob
metadata:
  name: checkpoint-backup
spec:
  schedule: "0 */6 * * *"  # Every 6 hours
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: backup
              image: google/cloud-sdk:alpine
              command:
                - /bin/sh
                - -c
                - |
                  gsutil -m rsync -r -d /mnt/checkpoints \
                    gs://training-backups/checkpoints/$(date +%Y%m%d_%H%M%S)
              volumeMounts:
                - name: checkpoints
                  mountPath: /mnt/checkpoints
          volumes:
            - name: checkpoints
              persistentVolumeClaim:
                claimName: training-checkpoints
          restartPolicy: OnFailure
```

## Monitoring and Alerting

```yaml
# training-monitoring.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: training-alerts
data:
  rules.yaml: |
    groups:
      - name: training.rules
        rules:
          - alert: TrainingJobDown
            expr: up{job="training-job"} == 0
            for: 5m
            labels:
              severity: critical
            annotations:
              summary: "Training job is down"
          
          - alert: NodeUpgradeScheduled
            expr: increase(kube_node_info[1h]) > 0
            labels:
              severity: warning
            annotations:
              summary: "Node upgrade detected during training"
          
          - alert: GPUMemoryHigh
            expr: nvidia_gpu_memory_used_bytes / nvidia_gpu_memory_total_bytes > 0.95
            for: 10m
            labels:
              severity: warning
            annotations:
              summary: "GPU memory usage very high"
```

## Key Operational Practices

1. **Before Starting Training:**
   ```bash
   # Lock down the cluster
   gcloud container node-pools update h100-pool-a \
       --cluster=ml-training-cluster \
       --no-enable-autoupgrade
   ```

2. **During Training:**
   - Monitor maintenance exclusions
   - Regular checkpoint verification
   - GPU health monitoring
   - Network performance tracking

3. **Planned Node Pool Rotation:**
   ```bash
   # Create new pool with updated images
   gcloud container node-pools create h100-pool-b \
       --cluster=ml-training-cluster \
       --machine-type=a3-highgpu-8g \
       --num-nodes=4 \
       --no-enable-autoupgrade
   
   # Migrate workloads during maintenance window
   # Delete old pool after validation
   ```

This configuration provides maximum protection for long-running training while maintaining security through the STABLE channel and controlled upgrade processes.
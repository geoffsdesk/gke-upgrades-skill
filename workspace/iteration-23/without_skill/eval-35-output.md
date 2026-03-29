Here's a comprehensive GKE configuration strategy for stable, long-running foundation model training with H100 GPUs:

## Cluster Configuration

```yaml
# cluster-config.yaml
apiVersion: container.googleapis.com/v1
kind: Cluster
metadata:
  name: h100-training-cluster
spec:
  releaseChannel:
    channel: REGULAR  # Balanced stability vs security updates
  
  maintenancePolicy:
    window:
      dailyMaintenanceWindow:
        startTime: "02:00"  # Low-traffic hours
      maintenanceExclusions:
        - name: "training-protection"
          startTime: "2024-01-01T00:00:00Z"
          endTime: "2024-12-31T23:59:59Z"
          scope: UPGRADES  # Block upgrades, allow security patches
  
  nodeConfig:
    machineType: a3-highgpu-8g  # H100 instances
    diskSizeGb: 200
    diskType: pd-ssd
    
  workloadIdentityConfig:
    workloadPool: "PROJECT_ID.svc.id.goog"
    
  privateClusterConfig:
    enablePrivateNodes: true
    enablePrivateEndpoint: false
    masterIpv4CidrBlock: "10.0.0.0/28"
```

## Strategic Node Pool Design

```yaml
# training-nodepool.yaml
apiVersion: container.googleapis.com/v1
kind: NodePool
metadata:
  name: h100-training-pool
spec:
  cluster: h100-training-cluster
  
  # Critical: Disable auto-upgrades for training nodes
  management:
    autoUpgrade: false
    autoRepair: true  # Keep repair for hardware failures
  
  # Fixed size for predictable training
  initialNodeCount: 8
  autoscaling:
    enabled: false
  
  config:
    machineType: a3-highgpu-8g
    accelerators:
      - type: nvidia-h100-80gb
        count: 8
    
    # Prevent preemption
    preemptible: false
    spot: false
    
    # Extended maintenance exclusions
    metadata:
      disable-legacy-endpoints: "true"
      
    taints:
      - key: "training-workload"
        value: "h100"
        effect: "NO_SCHEDULE"
        
    labels:
      workload-type: "foundation-training"
      gpu-type: "h100"
      maintenance-group: "protected"

---
# Separate pool for supporting services
apiVersion: container.googleapis.com/v1
kind: NodePool
metadata:
  name: system-pool
spec:
  cluster: h100-training-cluster
  
  management:
    autoUpgrade: true  # OK for system services
    autoRepair: true
    
  autoscaling:
    enabled: true
    minNodeCount: 2
    maxNodeCount: 5
    
  config:
    machineType: n2-standard-4
    preemptible: false
    
    labels:
      workload-type: "system"
```

## Training Job Protection Strategy

```yaml
# training-job.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: foundation-model-training
  annotations:
    # Prevent disruption during training
    cluster-autoscaler.kubernetes.io/safe-to-evict: "false"
spec:
  backoffLimit: 3
  template:
    metadata:
      annotations:
        cluster-autoscaler.kubernetes.io/safe-to-evict: "false"
    spec:
      restartPolicy: Never
      
      # Pin to protected nodes
      nodeSelector:
        workload-type: foundation-training
      
      tolerations:
        - key: "training-workload"
          operator: "Equal"
          value: "h100"
          effect: "NoSchedule"
      
      # High priority to prevent preemption
      priorityClassName: training-critical
      
      containers:
      - name: training
        image: gcr.io/PROJECT_ID/training:latest
        resources:
          requests:
            nvidia.com/gpu: 8
            memory: 1000Gi
            cpu: 200
          limits:
            nvidia.com/gpu: 8
            memory: 1000Gi
        
        # Graceful shutdown handling
        lifecycle:
          preStop:
            exec:
              command: ["/bin/sh", "-c", "python save_checkpoint.py --emergency=true"]
        
        # Health checks to detect training issues
        livenessProbe:
          exec:
            command: ["python", "health_check.py"]
          initialDelaySeconds: 300
          periodSeconds: 300
          timeoutSeconds: 60
          failureThreshold: 3

---
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: training-critical
value: 1000000
globalDefault: false
description: "Critical priority for training workloads"
```

## Advanced Maintenance Control

```bash
#!/bin/bash
# maintenance-manager.sh

# Function to create training-aware maintenance exclusion
create_maintenance_exclusion() {
    local start_date=$1
    local end_date=$2
    local exclusion_name="training-run-$(date +%s)"
    
    gcloud container clusters update h100-training-cluster \
        --add-maintenance-exclusion-name="$exclusion_name" \
        --add-maintenance-exclusion-start="$start_date" \
        --add-maintenance-exclusion-end="$end_date" \
        --add-maintenance-exclusion-scope=upgrades \
        --zone=us-central1-a
}

# Monitor for running training jobs
monitor_training_jobs() {
    while true; do
        # Check for active training jobs
        active_jobs=$(kubectl get jobs -l workload-type=foundation-training \
            --field-selector status.active=1 -o name | wc -l)
        
        if [ "$active_jobs" -gt 0 ]; then
            echo "Training jobs active. Maintenance exclusion in effect."
            
            # Ensure exclusion is active for next 30 days
            end_date=$(date -d "+30 days" -Iseconds)
            create_maintenance_exclusion "$(date -Iseconds)" "$end_date"
        fi
        
        sleep 3600  # Check hourly
    done
}
```

## Monitoring and Alerting

```yaml
# training-monitoring.yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: training-disruption-alerts
spec:
  groups:
  - name: training.protection
    rules:
    - alert: TrainingNodeUnschedulable
      expr: kube_node_spec_unschedulable{node=~".*h100-training.*"} == 1
      for: 5m
      annotations:
        summary: "Training node became unschedulable"
        description: "H100 training node {{ $labels.node }} is unschedulable"
    
    - alert: MaintenanceWindowApproaching
      expr: (gke_cluster_maintenance_window_start_time - time()) < 86400
      annotations:
        summary: "Cluster maintenance window in 24 hours"
        description: "Check for active training jobs before maintenance"
    
    - alert: TrainingJobRestart
      expr: increase(kube_job_status_failed[5m]) > 0
      labels:
        severity: critical
      annotations:
        summary: "Training job failed and restarted"

---
# GPU monitoring
apiVersion: v1
kind: ConfigMap
metadata:
  name: gpu-monitoring
data:
  monitor.py: |
    import subprocess
    import time
    
    def check_gpu_health():
        try:
            result = subprocess.run(['nvidia-smi', '--query-gpu=temperature.gpu,utilization.gpu', 
                                   '--format=csv,noheader,nounits'], 
                                  capture_output=True, text=True)
            
            for line in result.stdout.strip().split('\n'):
                temp, util = line.split(', ')
                if int(temp) > 80 or int(util) < 5:  # Potential issues
                    print(f"GPU alert: temp={temp}°C, util={util}%")
                    
        except Exception as e:
            print(f"GPU monitoring error: {e}")
    
    while True:
        check_gpu_health()
        time.sleep(60)
```

## Checkpoint and Recovery Strategy

```yaml
# checkpoint-cronjob.yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: training-checkpoint
spec:
  schedule: "0 */4 * * *"  # Every 4 hours
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: OnFailure
          containers:
          - name: checkpoint
            image: gcr.io/PROJECT_ID/checkpoint-manager:latest
            command:
            - /bin/bash
            - -c
            - |
              # Signal training pods to save checkpoint
              kubectl get pods -l workload-type=foundation-training \
                -o name | xargs -I {} kubectl exec {} -- \
                python trigger_checkpoint.py --sync=true
              
              # Verify checkpoint integrity
              gsutil -m cp gs://training-checkpoints/latest/* /tmp/verify/
              python verify_checkpoint.py /tmp/verify/
            
            volumeMounts:
            - name: checkpoint-storage
              mountPath: /checkpoints
          volumes:
          - name: checkpoint-storage
            persistentVolumeClaim:
              claimName: checkpoint-pvc
```

## Security Updates Strategy

```bash
#!/bin/bash
# security-update-manager.sh

# Controlled security update process
apply_security_updates() {
    local training_jobs=$(kubectl get jobs -l workload-type=foundation-training \
        --field-selector status.active=1 -o name | wc -l)
    
    if [ "$training_jobs" -eq 0 ]; then
        echo "No active training jobs. Safe to apply security updates."
        
        # Update system node pool first
        gcloud container clusters upgrade h100-training-cluster \
            --node-pool=system-pool \
            --zone=us-central1-a \
            --quiet
        
        # Schedule training node updates during maintenance window
        echo "System nodes updated. Training nodes will update during next maintenance window."
    else
        echo "Training jobs active. Deferring security updates."
        # Log for security team review
        echo "$(date): Security update deferred due to active training" >> /var/log/deferred-updates.log
    fi
}

# Run weekly security check
apply_security_updates
```

## Key Recommendations

1. **Release Channel**: Use `REGULAR` for balanced stability and security
2. **Node Pool Strategy**: Separate pools for training (upgrades disabled) and system services
3. **Maintenance Exclusions**: Implement dynamic exclusions based on training job status
4. **Monitoring**: Comprehensive alerting for node health and job status
5. **Checkpointing**: Automated checkpoint strategy every 4 hours
6. **Security**: Controlled update process that respects training schedules

This configuration provides maximum protection for long-running training while maintaining security posture through controlled update mechanisms.
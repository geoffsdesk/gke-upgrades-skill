Here's a production-ready GKE configuration optimized for long-running H100 training workloads:

## Cluster Configuration

```yaml
# cluster.yaml
apiVersion: container.v1
kind: Cluster
metadata:
  name: ml-training-h100
spec:
  releaseChannel:
    channel: REGULAR  # Balance of stability and security updates
  
  maintenancePolicy:
    window:
      dailyMaintenanceWindow:
        startTime: "02:00"  # UTC - adjust for your timezone
      maintenanceExclusions:
        - name: "training-blackout"
          startTime: "2024-01-01T00:00:00Z"
          endTime: "2024-12-31T23:59:59Z"
          scope: NO_UPGRADES
  
  nodePoolDefaults:
    nodeConfigDefaults:
      gcfsConfig:
        enabled: true  # For faster image pulls
      
  workloadIdentityConfig:
    workloadPool: "PROJECT_ID.svc.id.goog"
  
  # Network configuration for high-bandwidth GPU communication
  networkConfig:
    network: "projects/PROJECT_ID/global/networks/ml-vpc"
    subnetwork: "projects/PROJECT_ID/regions/REGION/subnetworks/ml-subnet"
    enableIntraNodeVisibility: true
```

## Node Pool Strategy

```yaml
# h100-training-pool.yaml
apiVersion: container.v1
kind: NodePool
metadata:
  name: h100-training-pool
  cluster: ml-training-h100
spec:
  initialNodeCount: 2
  
  autoscaling:
    enabled: true
    minNodeCount: 0
    maxNodeCount: 10
    
  management:
    autoUpgrade: false  # Critical: Manual control for training nodes
    autoRepair: true    # Keep repair enabled for hardware issues
    
  upgradeSettings:
    maxSurge: 0
    maxUnavailable: 1
    strategy: BLUE_GREEN  # Safer for GPU workloads
    
  nodeConfig:
    machineType: "a3-highgpu-8g"  # H100 instance type
    
    accelerators:
      - acceleratorCount: 8
        acceleratorType: "nvidia-h100-80gb"
        gpuDriverInstallationConfig:
          gpuDriverVersion: "LATEST"
          
    diskSizeGb: 200
    diskType: "pd-ssd"
    
    # Optimize for ML workloads
    metadata:
      disable-legacy-endpoints: "true"
      
    labels:
      workload-type: "training"
      gpu-type: "h100"
      
    taints:
      - key: "nvidia.com/gpu"
        value: "h100"
        effect: "NO_SCHEDULE"
        
    serviceAccount: "training-sa@PROJECT_ID.iam.gserviceaccount.com"
    
    # Enable placement policies for optimal GPU interconnect
    reservationAffinity:
      consumeReservationType: "ANY_RESERVATION"
```

## Utility Node Pool

```yaml
# utility-pool.yaml - For system workloads
apiVersion: container.v1
kind: NodePool
metadata:
  name: utility-pool
  cluster: ml-training-h100
spec:
  initialNodeCount: 2
  
  management:
    autoUpgrade: true   # OK for utility nodes
    autoRepair: true
    
  nodeConfig:
    machineType: "n2-standard-4"
    diskSizeGb: 100
    
    labels:
      workload-type: "utility"
      
  upgradeSettings:
    maxSurge: 1
    maxUnavailable: 0
```

## Training Job Protection

```yaml
# training-job.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: foundation-model-training
  labels:
    training-run: "experiment-001"
spec:
  backoffLimit: 3
  
  template:
    metadata:
      labels:
        training-run: "experiment-001"
      annotations:
        # Prevent preemption during training
        cluster-autoscaler.kubernetes.io/safe-to-evict: "false"
        
    spec:
      restartPolicy: Never
      
      # Schedule only on H100 nodes
      nodeSelector:
        gpu-type: "h100"
        
      tolerations:
        - key: "nvidia.com/gpu"
          value: "h100"
          effect: "NO_SCHEDULE"
          
      # Anti-affinity for distributed training
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              podAffinityTerm:
                labelSelector:
                  matchLabels:
                    training-run: "experiment-001"
                topologyKey: "kubernetes.io/hostname"
                
      containers:
        - name: trainer
          image: "gcr.io/PROJECT_ID/training:latest"
          
          resources:
            requests:
              nvidia.com/gpu: 8
              cpu: "32"
              memory: "200Gi"
            limits:
              nvidia.com/gpu: 8
              cpu: "32"
              memory: "200Gi"
              
          # Graceful shutdown handling
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "kill -TERM $PID && wait"]
                
          # Health checks
          livenessProbe:
            exec:
              command: ["python", "/app/health_check.py"]
            initialDelaySeconds: 300
            periodSeconds: 300
            timeoutSeconds: 30
            
      # Long grace period for checkpoint saving
      terminationGracePeriodSeconds: 3600
```

## Monitoring and Alerting

```yaml
# training-monitor.yaml
apiVersion: v1
kind: Service
metadata:
  name: training-metrics
  labels:
    app: training-monitor
spec:
  selector:
    training-run: "experiment-001"
  ports:
    - port: 8080
      targetPort: metrics
      
---
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: training-metrics
spec:
  selector:
    matchLabels:
      app: training-monitor
  endpoints:
    - port: metrics
      interval: 30s
      
---
# Alert for training job failures
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: training-alerts
spec:
  groups:
    - name: training
      rules:
        - alert: TrainingJobFailed
          expr: kube_job_failed{job_name=~"foundation-model.*"} > 0
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
            summary: "GPU utilization low on {{ $labels.instance }}"
```

## Operational Scripts

```bash
#!/bin/bash
# cluster-maintenance.sh

# Function to safely drain H100 nodes
drain_h100_node() {
    local node_name=$1
    
    echo "Checking for running training jobs on $node_name"
    
    # Check if critical training pods are running
    training_pods=$(kubectl get pods --field-selector spec.nodeName=$node_name \
        -l workload-type=training --no-headers | wc -l)
    
    if [ $training_pods -gt 0 ]; then
        echo "ERROR: Training pods found on $node_name. Manual intervention required."
        kubectl get pods --field-selector spec.nodeName=$node_name -l workload-type=training
        return 1
    fi
    
    # Safe to drain
    kubectl drain $node_name --ignore-daemonsets --delete-emptydir-data --grace-period=3600
}

# Function to perform controlled cluster upgrade
upgrade_cluster() {
    echo "Starting controlled cluster upgrade..."
    
    # 1. Upgrade utility nodes first
    kubectl patch nodepool utility-pool --type='merge' \
        -p='{"spec":{"management":{"autoUpgrade":true}}}'
    
    # 2. Wait for utility nodes to complete
    echo "Waiting for utility nodes to upgrade..."
    # Monitor upgrade progress
    
    # 3. Schedule H100 upgrade during maintenance window
    echo "H100 nodes will be upgraded manually during next maintenance window"
    echo "Run: gcloud container clusters upgrade ml-training-h100 --node-pool=h100-training-pool"
}

# Backup training checkpoints
backup_checkpoints() {
    kubectl exec -it $(kubectl get pods -l training-run=experiment-001 -o name | head -1) \
        -- gsutil -m cp -r /checkpoints gs://ml-training-backups/$(date +%Y%m%d-%H%M%S)/
}
```

## Key Recommendations

1. **Release Channel**: Use REGULAR for balanced stability and security updates
2. **Maintenance Windows**: Set specific windows and use exclusions during critical training
3. **Node Management**: Disable auto-upgrade on training pools, enable manual control
4. **Workload Protection**: Use PodDisruptionBudgets and proper taints/tolerations
5. **Monitoring**: Implement comprehensive GPU and training job monitoring
6. **Backup Strategy**: Automate checkpoint backups to GCS

This configuration provides maximum protection for long-running training while maintaining security through controlled updates.
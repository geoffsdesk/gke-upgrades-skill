Here's a comprehensive strategy to handle GKE upgrades with long-running batch jobs:

## 1. Use Node Pools for Separation

**Create dedicated node pools for batch workloads:**

```yaml
# batch-nodepool.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: batch-nodepool-config
data:
  nodepool-config: |
    gcloud container node-pools create batch-workloads \
      --cluster=your-cluster \
      --zone=your-zone \
      --node-taints=workload-type=batch:NoSchedule \
      --node-labels=workload-type=batch \
      --enable-autoscaling \
      --min-nodes=0 \
      --max-nodes=10 \
      --preemptible  # Optional: for cost savings
```

## 2. Configure Jobs with Node Affinity

```yaml
# batch-job.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: long-running-batch-job
spec:
  template:
    spec:
      nodeSelector:
        workload-type: batch
      tolerations:
      - key: "workload-type"
        operator: "Equal"
        value: "batch"
        effect: "NoSchedule"
      containers:
      - name: batch-processor
        image: your-batch-image
        resources:
          requests:
            memory: "2Gi"
            cpu: "1000m"
      restartPolicy: Never
  backoffLimit: 3
```

## 3. Upgrade Strategy with Rolling Node Pool Updates

**Step 1: Upgrade control plane first**
```bash
# Control plane upgrade (minimal disruption)
gcloud container clusters upgrade your-cluster \
  --master \
  --cluster-version=1.30.x-gke.x \
  --zone=your-zone
```

**Step 2: Create new node pool with 1.30**
```bash
# Create new node pool with latest version
gcloud container node-pools create batch-workloads-v130 \
  --cluster=your-cluster \
  --zone=your-zone \
  --node-version=1.30.x-gke.x \
  --node-taints=workload-type=batch:NoSchedule \
  --node-labels=workload-type=batch,version=v130 \
  --enable-autoscaling \
  --min-nodes=0 \
  --max-nodes=10
```

## 4. Implement Job Checkpointing

```yaml
# checkpointed-job.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: resumable-batch-job
spec:
  template:
    spec:
      nodeSelector:
        workload-type: batch
      containers:
      - name: batch-processor
        image: your-batch-image
        env:
        - name: CHECKPOINT_INTERVAL
          value: "300"  # 5 minutes
        - name: CHECKPOINT_PATH
          value: "/data/checkpoints"
        volumeMounts:
        - name: checkpoint-storage
          mountPath: /data/checkpoints
        - name: batch-data
          mountPath: /data/work
      volumes:
      - name: checkpoint-storage
        persistentVolumeClaim:
          claimName: checkpoint-pvc
      - name: batch-data
        persistentVolumeClaim:
          claimName: batch-data-pvc
      restartPolicy: Never
```

## 5. Graceful Migration Script

```bash
#!/bin/bash
# migration-script.sh

CLUSTER_NAME="your-cluster"
ZONE="your-zone"
OLD_NODEPOOL="batch-workloads"
NEW_NODEPOOL="batch-workloads-v130"

# Wait for running jobs to complete
wait_for_jobs() {
    echo "Checking for running jobs..."
    while kubectl get jobs -l workload-type=batch --field-selector=status.successful!=1 | grep -q "0/1"; do
        echo "Jobs still running, waiting 10 minutes..."
        kubectl get jobs -l workload-type=batch
        sleep 600
    done
    echo "All jobs completed!"
}

# Cordon old nodes to prevent new scheduling
cordon_old_nodes() {
    echo "Cordoning old nodes..."
    kubectl get nodes -l workload-type=batch,version!=v130 -o name | \
        xargs -I {} kubectl cordon {}
}

# Migrate workloads
migrate_workloads() {
    echo "Updating node selector for new jobs..."
    # Update your deployment scripts to target new nodepool
    kubectl patch job future-jobs -p '{
        "spec": {
            "template": {
                "spec": {
                    "nodeSelector": {
                        "workload-type": "batch",
                        "version": "v130"
                    }
                }
            }
        }
    }'
}

# Main migration flow
main() {
    echo "Starting migration..."
    cordon_old_nodes
    wait_for_jobs
    migrate_workloads
    
    echo "Safe to delete old node pool:"
    echo "gcloud container node-pools delete $OLD_NODEPOOL --cluster=$CLUSTER_NAME --zone=$ZONE"
}

main
```

## 6. Use CronJob for Scheduled Batch Work

```yaml
# scheduled-batch.yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: scheduled-batch-job
spec:
  schedule: "0 2 * * *"  # 2 AM daily
  concurrencyPolicy: Forbid  # Prevent overlapping jobs
  jobTemplate:
    spec:
      template:
        spec:
          nodeSelector:
            workload-type: batch
            version: v130
          containers:
          - name: batch-processor
            image: your-batch-image
          restartPolicy: OnFailure
```

## 7. Monitoring and Alerting

```yaml
# job-monitor.yaml
apiVersion: v1
kind: ServiceMonitor
metadata:
  name: batch-job-monitor
spec:
  selector:
    matchLabels:
      workload-type: batch
  endpoints:
  - port: metrics
---
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: batch-job-alerts
spec:
  groups:
  - name: batch-jobs
    rules:
    - alert: LongRunningJobBlocked
      expr: kube_job_status_active{job_name=~"batch-.*"} > 0 and kube_job_status_start_time < (time() - 18*3600)
      for: 1h
      annotations:
        summary: "Batch job running longer than 18 hours"
```

## 8. Complete Migration Timeline

1. **Week 1**: Create new node pool, test with non-critical jobs
2. **Week 2**: Migrate new jobs to new node pool
3. **Week 3**: Cordon old nodes, wait for current jobs to complete
4. **Week 4**: Delete old node pool

## Key Benefits:

- **Zero downtime** for running jobs
- **Gradual migration** reduces risk
- **Job isolation** prevents interference
- **Rollback capability** if issues arise
- **Cost optimization** with preemptible nodes for batch workloads

This approach ensures your long-running batch jobs complete successfully while enabling cluster upgrades with minimal risk.
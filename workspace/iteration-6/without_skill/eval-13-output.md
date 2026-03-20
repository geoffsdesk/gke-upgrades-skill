Here are several strategies to handle GKE upgrades without killing long-running batch jobs:

## 1. **Node Pool Surge Upgrade (Recommended)**

Configure surge upgrades to minimize disruption:

```yaml
# Configure node pool for surge upgrade
gcloud container node-pools update [NODE_POOL_NAME] \
    --cluster=[CLUSTER_NAME] \
    --zone=[ZONE] \
    --max-surge-upgrade=2 \
    --max-unavailable-upgrade=0
```

This creates new nodes before draining old ones, allowing jobs to complete naturally.

## 2. **Blue-Green Node Pool Strategy**

Create a new node pool with v1.30 while keeping the old one:

```bash
# Create new node pool with v1.30
gcloud container node-pools create "pool-v130" \
    --cluster=[CLUSTER_NAME] \
    --zone=[ZONE] \
    --node-version=1.30.x \
    --num-nodes=3

# Taint old nodes to prevent new scheduling
kubectl taint nodes -l cloud.google.com/gke-nodepool=[OLD_POOL] \
    upgrade=pending:NoSchedule

# Monitor jobs completion
kubectl get jobs --watch

# After jobs complete, delete old pool
gcloud container node-pools delete [OLD_POOL] --cluster=[CLUSTER_NAME]
```

## 3. **Job-Aware Scheduling Configuration**

Configure your batch jobs to be upgrade-resilient:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: long-running-batch
spec:
  backoffLimit: 3
  activeDeadlineSeconds: 57600  # 16 hours
  template:
    spec:
      restartPolicy: OnFailure
      tolerations:
      - key: "upgrade"
        operator: "Equal"
        value: "pending"
        effect: "NoSchedule"
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
            - matchExpressions:
              - key: cloud.google.com/gke-nodepool
                operator: In
                values: ["stable-pool"]
      containers:
      - name: batch-job
        image: your-job-image
        # Add checkpointing/state saving logic
```

## 4. **Maintenance Window Approach**

Set up maintenance exclusions and upgrade windows:

```bash
# Set maintenance exclusion (avoid peak job times)
gcloud container clusters update [CLUSTER_NAME] \
    --add-maintenance-exclusion-name weekend-jobs \
    --add-maintenance-exclusion-start 2024-01-15T18:00:00Z \
    --add-maintenance-exclusion-end 2024-01-16T10:00:00Z \
    --zone=[ZONE]

# Schedule upgrade window
gcloud container clusters update [CLUSTER_NAME] \
    --maintenance-window-start 2024-01-17T02:00:00Z \
    --maintenance-window-end 2024-01-17T06:00:00Z \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=WE"
```

## 5. **Graceful Job Management**

Implement job checkpointing and monitoring:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: job-monitor-script
data:
  monitor.sh: |
    #!/bin/bash
    # Check for node cordoning (upgrade signal)
    if kubectl get node $NODE_NAME -o jsonpath='{.spec.unschedulable}' | grep -q true; then
        echo "Node being drained, saving checkpoint..."
        # Implement your checkpointing logic here
        save_checkpoint
        exit 0
    fi
---
apiVersion: batch/v1
kind: Job
spec:
  template:
    spec:
      containers:
      - name: batch-processor
        env:
        - name: NODE_NAME
          valueFrom:
            fieldRef:
              fieldPath: spec.nodeName
        volumeMounts:
        - name: monitor-script
          mountPath: /scripts
        # Your job container
      volumes:
      - name: monitor-script
        configMap:
          name: job-monitor-script
          defaultMode: 0755
```

## 6. **Pre-Upgrade Checklist**

```bash
# 1. Check current running jobs
kubectl get jobs --all-namespaces
kubectl get pods --field-selector=status.phase=Running

# 2. Estimate completion times
kubectl describe jobs | grep "Active\|Start Time"

# 3. Set appropriate drain timeout
gcloud container node-pools update [NODE_POOL] \
    --max-pods-per-node=110 \
    --enable-autorepair \
    --enable-autoupgrade=false  # Disable auto-upgrade temporarily

# 4. Monitor job progress
watch "kubectl get jobs --all-namespaces"
```

## 7. **Recommended Upgrade Process**

1. **Disable auto-upgrade** temporarily
2. **Schedule during low-activity periods**
3. **Use surge upgrades** with `max-unavailable=0`
4. **Monitor job completion** before proceeding
5. **Implement job checkpointing** for critical workloads
6. **Test the process** in a staging environment first

## 8. **Emergency Rollback Plan**

```bash
# If issues arise, quickly rollback nodes
gcloud container node-pools rollback [NODE_POOL_NAME] \
    --cluster=[CLUSTER_NAME] \
    --zone=[ZONE]
```

The **surge upgrade with blue-green node pools** approach is typically the safest for long-running batch jobs, as it ensures jobs can complete on existing nodes while new capacity is available for future workloads.
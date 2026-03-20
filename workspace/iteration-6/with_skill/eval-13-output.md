# GKE Upgrade Plan for Long-Running Batch Jobs

## Overview
You'll need a **drain-and-wait** strategy rather than surge upgrades to protect your 8-16 hour batch jobs. Here's a detailed plan for upgrading your Standard cluster from 1.29 to 1.30 without disrupting active jobs.

## Upgrade Strategy

### 1. Use Maintenance Exclusions for Job Protection
Apply a **"no minor or node upgrades"** exclusion during active batch processing periods:

```bash
# Block node upgrades during batch processing windows
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "batch-processing-protection" \
  --add-maintenance-exclusion-start-time 2024-XX-XXTHH:MM:SSZ \
  --add-maintenance-exclusion-end-time 2024-XX-XXTHH:MM:SSZ \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

This allows control plane security patches while preventing disruptive node upgrades during your batch windows.

### 2. Dedicated Batch Node Pool (Recommended)
Isolate batch workloads on a dedicated node pool for precise upgrade control:

```bash
# Create dedicated batch node pool with auto-upgrade disabled
gcloud container node-pools create batch-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --num-nodes 3 \
  --machine-type n2-standard-8 \
  --enable-autoscaling \
  --min-nodes 0 \
  --max-nodes 10 \
  --no-enable-autoupgrade \
  --node-labels batch=true
```

Update your batch jobs to use node affinity:
```yaml
spec:
  nodeSelector:
    batch: "true"
  # or use affinity for more flexibility
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
        - matchExpressions:
          - key: batch
            operator: In
            values: ["true"]
```

### 3. Cordon-and-Wait Node Pool Upgrade Process

For the main upgrade, use this sequence:

```bash
# Step 1: Control plane upgrade (safe - doesn't affect running jobs)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.30

# Step 2: Configure batch pool for manual drain
gcloud container node-pools update batch-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1

# Step 3: Cordon batch nodes to prevent NEW jobs from scheduling
kubectl cordon -l batch=true

# Step 4: Wait for running jobs to complete naturally
# Monitor with:
kubectl get jobs -A --field-selector status.active=1
kubectl get pods -A --field-selector status.phase=Running | grep batch

# Step 5: Once batch nodes are empty, upgrade the pool
gcloud container node-pools upgrade batch-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30

# Step 6: Uncordon nodes after upgrade completes
kubectl uncordon -l batch=true
```

## Pre-Upgrade Checklist

```
Pre-Upgrade Checklist - Batch Processing Cluster
- [ ] Cluster: ___ | Mode: Standard | Channel: ___
- [ ] Current: 1.29 | Target: 1.30

Batch Job Protection
- [ ] Job scheduling patterns documented (when do 8-16h jobs typically start?)
- [ ] Current active jobs inventory: `kubectl get jobs -A --field-selector status.active=1`
- [ ] Maintenance exclusion configured for active batch windows
- [ ] Dedicated batch node pool created with auto-upgrade disabled
- [ ] Batch jobs configured with nodeSelector/affinity to batch pool
- [ ] Job queue/scheduler can handle cordoned nodes gracefully

Compatibility & Dependencies
- [ ] 1.30 available in cluster's release channel
- [ ] Batch processing framework compatibility verified with K8s 1.30
- [ ] Job scheduler (Argo Workflows/Airflow/etc.) supports 1.30
- [ ] Container images compatible with 1.30 node image
- [ ] No deprecated API usage in job specs

Infrastructure Readiness
- [ ] Non-batch node pools configured for surge upgrades (faster completion)
- [ ] Sufficient quota for surge nodes in non-batch pools
- [ ] Monitoring active for job completion detection
- [ ] Runbook for emergency job cancellation if needed
```

## Batch Job Best Practices

### 1. Implement Checkpointing
If possible, modify your batch jobs to save progress periodically:

```yaml
apiVersion: batch/v1
kind: Job
spec:
  template:
    spec:
      containers:
      - name: batch-job
        env:
        - name: CHECKPOINT_INTERVAL
          value: "3600"  # Save every hour
        - name: CHECKPOINT_PATH
          value: "/persistent-storage/checkpoints"
        volumeMounts:
        - name: checkpoint-storage
          mountPath: /persistent-storage
      volumes:
      - name: checkpoint-storage
        persistentVolumeClaim:
          claimName: batch-checkpoint-pvc
```

### 2. Use PodDisruptionBudgets
Protect running jobs from accidental eviction:

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: batch-jobs-pdb
spec:
  minAvailable: 100%  # Don't evict any batch pods
  selector:
    matchLabels:
      app: batch-processor
```

### 3. Graceful Termination
Set appropriate termination grace periods:

```yaml
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 300  # 5 minutes for cleanup
      containers:
      - name: batch-job
        # Handle SIGTERM to save work and exit gracefully
```

## Timeline Recommendation

1. **Week 1**: Control plane upgrade to 1.30 (zero downtime)
2. **Week 2**: Upgrade non-batch node pools during low-activity period
3. **Week 3**: Schedule batch pool upgrade during planned maintenance window
   - Coordinate with your batch job scheduler team
   - Ensure no critical jobs are queued for the upgrade window
   - Plan for 4-6 hours: job completion wait + actual upgrade time

## Monitoring During Upgrade

```bash
# Track active batch jobs
watch 'kubectl get jobs -A --field-selector status.active=1 | wc -l'

# Monitor node upgrade progress
watch 'kubectl get nodes -o wide -l batch=true'

# Check for any stuck/pending pods
kubectl get pods -A | grep -E "Pending|Terminating" | grep batch
```

## Emergency Procedures

If a job absolutely must be terminated:
```bash
# Cancel specific job (saves any checkpointed work)
kubectl delete job JOB_NAME -n NAMESPACE --cascade=foreground

# Force-delete stuck terminating pods (last resort)
kubectl delete pod POD_NAME -n NAMESPACE --force --grace-period=0
```

This approach gives you complete control over when batch workloads are disrupted while still maintaining cluster security through control plane patches.
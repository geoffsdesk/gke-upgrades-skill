# GKE Upgrade Plan for Long-Running Batch Jobs

## Executive Summary
Your 8-16 hour batch jobs need special protection during GKE upgrades since they can't tolerate mid-execution termination. The key strategy is using **maintenance exclusions** to control upgrade timing and **autoscaled blue-green upgrades** for the actual node pool transitions.

## Current State Assessment
- **Cluster**: Standard GKE on Regular channel
- **Upgrade path**: 1.30 → 1.31 (single minor version, supported)
- **Challenge**: Long-running batch jobs (8-16 hours) vs GKE's 1-hour PDB timeout

## Recommended Upgrade Strategy

### Phase 1: Control Plane Upgrade (Low Risk)
The control plane can be upgraded immediately with minimal impact to running workloads.

```bash
# Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.31

# Verify control plane version
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

### Phase 2: Node Pool Strategy - Autoscaled Blue-Green
For your long-running jobs, use GKE's **autoscaled blue-green upgrade** strategy (preview feature). This is specifically designed for workloads like yours:

**Why autoscaled blue-green is perfect for batch jobs:**
- Green pool scales up based on actual workload demand
- Blue pool scales down as pods naturally complete
- Supports longer eviction periods for job completion
- No forced termination after 1 hour like surge upgrades

```bash
# Configure autoscaled blue-green strategy
gcloud container node-pools update BATCH_NODE_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaled-blue-green-upgrade \
  --node-pool-soak-duration 2h \
  --wait-for-drain-timeout 24h
```

### Phase 3: Timing Protection with Maintenance Exclusions

**Option A: Schedule Around Job Cycles (Recommended)**
```bash
# Add "no minor or node upgrades" exclusion during active batch periods
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "batch-protection" \
  --add-maintenance-exclusion-start-time "2024-MM-DDTHH:MM:SSZ" \
  --add-maintenance-exclusion-end-time "2024-MM-DDTHH:MM:SSZ" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

**Option B: Dedicated Batch Node Pool with Auto-Upgrade Disabled**
```bash
# Create dedicated batch node pool with no auto-upgrade
gcloud container node-pools create batch-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --machine-type n1-standard-8 \
  --enable-autoscaling \
  --min-nodes 0 \
  --max-nodes 10 \
  --node-version 1.30 \
  --no-enable-autoupgrade
```

## Step-by-Step Upgrade Runbook

### Pre-Upgrade Checklist
```
- [ ] Control plane upgraded to 1.31
- [ ] Current batch jobs inventory captured
- [ ] Job completion timeline estimated
- [ ] Autoscaled blue-green enabled on batch node pools
- [ ] Maintenance exclusion configured during active job periods
- [ ] Monitoring and alerting active
- [ ] Job checkpointing verified (if supported)
```

### Execution Steps

**1. Wait for Natural Job Completion Window**
```bash
# Monitor running batch jobs
kubectl get jobs -A --field-selector status.completion-time=""
kubectl get pods -A -l batch.kubernetes.io/job-name --field-selector status.phase=Running
```

**2. Apply Maintenance Exclusion (if jobs are running)**
```bash
# Block node upgrades for 30 days max
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "batch-job-protection" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time $(date -u -d "+30 days" +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

**3. Upgrade Node Pools During Quiet Period**
```bash
# Upgrade batch node pool when no jobs running
gcloud container node-pools upgrade BATCH_NODE_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31

# Monitor progress - autoscaled blue-green will handle the transition
watch 'kubectl get nodes -L cloud.google.com/gke-nodepool'
```

**4. Remove Maintenance Exclusion**
```bash
# After successful upgrade
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "batch-job-protection"
```

## Alternative Approaches

### Manual Blue-Green (if autoscaled preview unavailable)
```bash
# Create new node pool at 1.31
gcloud container node-pools create batch-pool-131 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31 \
  --machine-type EXISTING_MACHINE_TYPE \
  --num-nodes 0

# Scale to match capacity when ready
gcloud container node-pools resize batch-pool-131 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --num-nodes DESIRED_SIZE

# Cordon old pool and wait for natural job completion
kubectl cordon -l cloud.google.com/gke-nodepool=BATCH_NODE_POOL

# Delete old pool after jobs finish
gcloud container node-pools delete BATCH_NODE_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE
```

### Dedicated Batch Cluster Strategy
For the most isolation, consider running long batch jobs on a separate cluster with Extended release channel:

```bash
# Create batch-specific cluster with Extended channel (24-month support)
gcloud container clusters create batch-cluster \
  --zone ZONE \
  --release-channel extended \
  --machine-type n1-standard-8 \
  --num-nodes 3
```

## Job-Level Protections

### Enhance Job Definitions
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: long-batch-job
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 3600  # 1 hour for cleanup
      restartPolicy: Never
      containers:
      - name: batch-processor
        image: your-batch-image
        # Add checkpointing logic if possible
        lifecycle:
          preStop:
            exec:
              command: ["/bin/sh", "-c", "save-checkpoint.sh"]
```

### Pod Disruption Budget
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: batch-job-pdb
spec:
  minAvailable: 100%  # Prevent any voluntary disruption
  selector:
    matchLabels:
      app: batch-processor
```

## Monitoring and Validation

```bash
# Check upgrade progress
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE

# Monitor job completion
kubectl get jobs -A -w

# Verify no stuck pods
kubectl get pods -A | grep -E "Terminating|Pending"

# Confirm all nodes upgraded
kubectl get nodes -o wide
```

## Key Recommendations

1. **Use autoscaled blue-green upgrades** - specifically designed for your use case
2. **Leverage maintenance exclusions** - "no minor or node upgrades" during active job periods
3. **Upgrade control plane first** - minimal risk to running workloads
4. **Consider dedicated batch node pools** - with separate maintenance policies
5. **Implement job checkpointing** - if your batch framework supports it
6. **Monitor job queues** - time upgrades during natural low periods

This approach ensures your 8-16 hour batch jobs can complete naturally while still keeping your cluster secure and up-to-date.
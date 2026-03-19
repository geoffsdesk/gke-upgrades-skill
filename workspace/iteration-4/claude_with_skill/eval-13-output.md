# GKE Upgrade Plan for Long-Running Batch Jobs

## Upgrade Strategy

For 8-16 hour batch jobs that can't be interrupted, I recommend a **blue-green upgrade** approach with careful job scheduling coordination.

## Current Assessment

- **Cluster**: Standard GKE
- **Versions**: 1.29 → 1.30
- **Challenge**: Long-running batch jobs (8-16h) that can't be killed
- **Solution**: Blue-green with job-aware scheduling

## Recommended Approach

### Phase 1: Prepare New Node Pool

Create a new node pool at version 1.30 alongside your existing 1.29 pool:

```bash
# Create new node pool with 1.30
gcloud container node-pools create batch-pool-v130 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --node-version 1.30.x-gke.xxx \
  --machine-type MACHINE_TYPE \
  --num-nodes NUM_NODES \
  --node-labels=batch-generation=v130 \
  --disk-size=100GB

# Keep existing pool with label
kubectl label nodes -l cloud.google.com/gke-nodepool=EXISTING_POOL_NAME batch-generation=v129
```

### Phase 2: Control Plane Upgrade

Upgrade the control plane first (safe for running workloads):

```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.30.x-gke.xxx
```

### Phase 3: Job Scheduling Strategy

**Option A: Natural Job Completion (Recommended)**
- Stop scheduling new jobs on old nodes
- Let existing jobs complete naturally
- Schedule new jobs on v1.30 nodes

**Option B: Checkpoint/Resume (If Supported)**
- Implement checkpointing in your batch jobs
- Drain and migrate with resume capability

### Phase 4: Workload Migration

#### For Job Scheduling Systems (Recommended)

If using a job scheduler like Argo Workflows, Tekton, or custom controllers:

```yaml
# Update job templates to prefer new nodes
apiVersion: batch/v1
kind: Job
spec:
  template:
    spec:
      nodeSelector:
        batch-generation: v130
      tolerations:
      - key: "batch-generation"
        operator: "Equal"
        value: "v130"
        effect: "NoSchedule"
```

#### For Direct Kubernetes Jobs

```yaml
# Taint old nodes to prevent new job scheduling
apiVersion: v1
kind: Node
metadata:
  name: NODE_NAME
spec:
  taints:
  - key: "upgrading"
    value: "true"
    effect: "NoSchedule"
```

## Detailed Migration Runbook

### Pre-Migration Checklist

```
- [ ] Job inventory completed (identify all long-running batch workloads)
- [ ] Job completion monitoring in place
- [ ] New node pool created and healthy
- [ ] Control plane upgraded to 1.30
- [ ] Job scheduling system updated to target new nodes
- [ ] Rollback plan documented
```

### Migration Commands

```bash
# 1. Taint old nodes to stop new job scheduling
kubectl get nodes -l cloud.google.com/gke-nodepool=OLD_POOL_NAME -o name | \
  xargs -I {} kubectl taint {} upgrading=true:NoSchedule

# 2. Monitor running jobs on old nodes
kubectl get pods -A -o wide --field-selector=status.phase=Running | \
  grep OLD_NODE_NAMES

# 3. Wait for jobs to complete naturally
# Create monitoring script:
watch 'kubectl get pods -A --field-selector=status.phase=Running -o wide | grep -c OLD_NODE_NAMES'

# 4. Once old nodes are clear, cordon them
kubectl get nodes -l cloud.google.com/gke-nodepool=OLD_POOL_NAME -o name | \
  xargs kubectl cordon

# 5. Delete old node pool
gcloud container node-pools delete OLD_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE
```

### Timeline Estimation

- **Control plane upgrade**: 10-15 minutes
- **New node pool creation**: 5-10 minutes
- **Job migration period**: 16-24 hours (one full job cycle)
- **Total upgrade window**: 1-2 days

## Risk Mitigation

### Job Completion Monitoring

```bash
# Script to monitor job completion on old nodes
#!/bin/bash
OLD_POOL="batch-pool-v129"

while true; do
  RUNNING_JOBS=$(kubectl get pods -A -o wide --field-selector=status.phase=Running | \
    grep -c "$OLD_POOL" || echo "0")
  
  echo "$(date): $RUNNING_JOBS jobs still running on old nodes"
  
  if [ "$RUNNING_JOBS" -eq 0 ]; then
    echo "All jobs completed on old nodes. Safe to proceed."
    break
  fi
  
  sleep 300  # Check every 5 minutes
done
```

### Emergency Procedures

If a critical issue arises:

1. **Pause new job submission** to new nodes
2. **Preserve old node pool** (don't delete until confirmed stable)
3. **Rollback job scheduling** to old nodes if needed

```bash
# Emergency: Route jobs back to old nodes
kubectl taint nodes -l cloud.google.com/gke-nodepool=OLD_POOL_NAME upgrading-
```

## Alternative: Surge Upgrade with Extended Grace Period

If blue-green isn't feasible, configure surge upgrade with very long termination grace:

```bash
# Configure conservative surge settings
gcloud container node-pools update EXISTING_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# In your batch job specs, set long termination grace
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 3600  # 1 hour max GKE respects
```

**Note**: GKE only respects PDBs and termination grace for up to 1 hour during surge upgrades, so this won't fully protect 8-16 hour jobs.

## Post-Upgrade Validation

```bash
# Verify all nodes at 1.30
kubectl get nodes -o wide

# Confirm job scheduling on new nodes
kubectl get pods -A -o wide | grep batch

# Test job submission
kubectl apply -f test-batch-job.yaml
kubectl get pods -o wide | grep test-batch
```

The blue-green approach gives you complete control over the migration timeline and ensures zero interruption to your long-running batch jobs.
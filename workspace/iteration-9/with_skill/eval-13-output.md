# GKE Upgrade Plan for Long-Running Batch Workloads

## Executive Summary

For your 8-16 hour batch jobs, the key is **preventing forced eviction during node upgrades**. I'll recommend a combination of maintenance exclusions, dedicated node pools, and GKE's autoscaled blue-green upgrade strategy to protect your long-running workloads.

## Upgrade Strategy Overview

**Control Plane:** Upgrade immediately (no impact on running pods)  
**Node Pools:** Use maintenance exclusions + autoscaled blue-green upgrade during job completion windows  
**Protection Method:** Dedicated batch node pool with controlled upgrade timing  

## Detailed Plan

### 1. Architecture Setup (if not already in place)

Isolate batch workloads on dedicated node pools with specific taints/tolerations:

```bash
# Create dedicated batch processing node pool
gcloud container node-pools create batch-processing \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --machine-type n1-standard-16 \
  --num-nodes 3 \
  --node-taints workload=batch:NoSchedule \
  --node-labels workload=batch

# Configure batch jobs with tolerations
# Add to your job specs:
tolerations:
- key: "workload"
  operator: "Equal"
  value: "batch"
  effect: "NoSchedule"
nodeSelector:
  workload: "batch"
```

### 2. Control Plane Upgrade (Safe - No Pod Impact)

```bash
# Upgrade control plane first - this doesn't affect running pods
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.31.0-gke.1146000

# Verify control plane upgrade
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

### 3. Node Pool Protection Strategy

**Option A: Maintenance Exclusions (Recommended)**

Block node upgrades during active batch processing periods:

```bash
# Add "no minor or node upgrades" exclusion to protect batch pool
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "batch-job-protection" \
  --add-maintenance-exclusion-start-time 2024-12-15T00:00:00Z \
  --add-maintenance-exclusion-end-time 2024-12-31T23:59:59Z \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

This blocks ALL node pool upgrades until you're ready. Control plane still gets security patches.

**Option B: Per-Node Pool Exclusion (Fine-grained Control)**

```bash
# Apply exclusion only to the batch processing node pool
gcloud container node-pools update batch-processing \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "batch-protection" \
  --add-maintenance-exclusion-start-time 2024-12-15T00:00:00Z \
  --add-maintenance-exclusion-end-time 2024-12-31T23:59:59Z \
  --add-maintenance-exclusion-scope no_upgrades
```

### 4. Node Pool Upgrade Timing

When ready to upgrade nodes (during a gap between batch jobs):

**Use Autoscaled Blue-Green Upgrade Strategy:**

```bash
# Configure autoscaled blue-green for batch node pool
gcloud container node-pools update batch-processing \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --min-nodes 0 \
  --max-nodes 10 \
  --node-pool-soak-duration 3600s \
  --blue-green-settings standard-rollout-policy=blue-green \
  --blue-green-settings node-pool-soak-duration=3600s

# Remove maintenance exclusion when ready
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "batch-job-protection"

# Initiate node pool upgrade
gcloud container node-pools upgrade batch-processing \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.0-gke.1146000
```

**Why autoscaled blue-green for batch workloads:**
- Creates new nodes (green pool) without disrupting existing jobs
- Allows jobs to complete naturally on old nodes (blue pool)
- Supports longer eviction periods for graceful completion
- Automatically scales based on workload demand

### 5. Job-Level Protection (Defense in Depth)

Add these configurations to your batch job specs:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: long-batch-job
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 3600  # 1 hour for graceful shutdown
      tolerations:
      - key: "workload"
        operator: "Equal"
        value: "batch"
        effect: "NoSchedule"
      nodeSelector:
        workload: "batch"
      containers:
      - name: batch-processor
        image: your-batch-image
        # Add SIGTERM handler for checkpointing
        lifecycle:
          preStop:
            exec:
              command: ["/bin/sh", "-c", "echo 'Saving checkpoint...' && save-checkpoint.sh"]
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: batch-job-pdb
spec:
  minAvailable: 1  # Adjust based on your parallelism needs
  selector:
    matchLabels:
      app: batch-processor
```

### 6. Alternative: Cordon and Wait Pattern

For maximum control, manually manage the upgrade:

```bash
# 1. Cordon batch nodes to prevent new job scheduling
kubectl cordon -l workload=batch

# 2. Wait for current jobs to complete (monitor progress)
kubectl get jobs -A --watch

# 3. Drain nodes when empty
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data

# 4. Upgrade the empty node pool
gcloud container node-pools upgrade batch-processing \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.0-gke.1146000

# 5. Uncordon after upgrade completes
kubectl uncordon -l workload=batch
```

## Pre-Upgrade Checklist

```
- [ ] Cluster: ___ | Current: 1.30.x | Target: 1.31.0-gke.1146000
- [ ] Batch workloads isolated on dedicated node pool with taints
- [ ] Job specs include adequate terminationGracePeriodSeconds (≥1hr)
- [ ] Checkpointing/graceful shutdown handlers implemented
- [ ] PDBs configured for batch workloads
- [ ] No active batch jobs scheduled during upgrade window
- [ ] Maintenance exclusion applied to protect node pool
- [ ] Monitoring active for job completion status
- [ ] Rollback plan documented (recreate node pool at 1.30 if needed)
```

## Timeline

1. **Week 1:** Control plane upgrade (immediate, no disruption)
2. **Week 2-3:** Wait for current batch cycles to complete
3. **Week 4:** Remove maintenance exclusions and upgrade node pools during job completion gap

## Risk Mitigation

- **Control plane first:** Eliminates version skew risk early
- **Maintenance exclusions:** Absolute protection against forced upgrades
- **Autoscaled blue-green:** Minimizes disruption, allows natural completion
- **Job-level PDBs:** Additional protection layer
- **Graceful shutdown:** Jobs can checkpoint and resume post-upgrade

This approach gives you complete control over timing while leveraging GKE's built-in upgrade strategies designed for long-running workloads.
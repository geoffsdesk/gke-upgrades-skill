# GKE Upgrade Plan: Long-Running Batch Jobs (8-16 hours)

## Executive Summary

For your long-running batch processing workloads (8-16 hours), I recommend a **maintenance exclusion strategy** combined with **job-aware scheduling** to protect running jobs while staying current with security patches. The key insight is that you can control WHEN upgrades happen without completely disabling them.

## Current Environment
- **Cluster**: Standard GKE on Regular release channel
- **Workloads**: 8-16 hour batch processing jobs
- **Upgrade path**: 1.30 → 1.31
- **Priority**: Job completion over immediate upgrades

## Recommended Approach: Maintenance Exclusions + Controlled Timing

### Strategy 1: "No minor or node upgrades" exclusion (Recommended)

This allows security patches on the control plane while blocking disruptive node upgrades:

```bash
# Block minor and node upgrades until you're ready
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "batch-job-protection" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time "2024-07-01T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

**Benefits:**
- Control plane gets security patches automatically
- Node pools stay on 1.30 until you initiate the upgrade
- Jobs continue uninterrupted
- You control the exact timing

### Strategy 2: Dedicated batch processing node pools

Create separate node pools for batch jobs with different upgrade policies:

```bash
# Create dedicated batch node pool with auto-upgrade disabled
gcloud container node-pools create batch-processing \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoupgrade=false \
  --node-version 1.30.x-gke.xxxx \
  --num-nodes 3 \
  --machine-type e2-standard-8

# Keep general workloads on auto-upgrading pools
gcloud container node-pools update general-workloads \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoupgrade
```

## Upgrade Execution Plan

### Phase 1: Control Plane (Safe - No Job Impact)
The control plane upgrade won't affect running jobs:

```bash
# Upgrade control plane first - jobs continue running
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.31.x-gke.latest
```

### Phase 2: Node Pool Upgrades (Requires Coordination)

**Option A: Cordon-and-wait pattern (Safest)**
```bash
# 1. Cordon nodes to prevent new jobs
kubectl cordon -l cloud.google.com/gke-nodepool=batch-processing

# 2. Monitor running jobs
kubectl get pods -A -o wide --field-selector spec.nodeName=NODE_NAME
# Or use your job monitoring system

# 3. Wait for natural completion (8-16 hours)
# 4. Upgrade empty node pool
gcloud container node-pools upgrade batch-processing \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.latest

# 5. Uncordon nodes
kubectl uncordon -l cloud.google.com/gke-nodepool=batch-processing
```

**Option B: Use GKE's autoscaled blue-green upgrade (Recommended for your use case)**

This is perfect for long-running workloads - it allows extended drain times:

```bash
# Configure blue-green with extended drain time
gcloud container node-pools update batch-processing \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --node-pool-soak-duration 18h \
  --max-pods-per-node-disruption-budget-timeout 20h

# Initiate blue-green upgrade
gcloud container node-pools upgrade batch-processing \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.latest \
  --upgrade-strategy blue-green-autoscaling
```

## Job Protection Configuration

### 1. Pod Disruption Budgets
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: batch-job-pdb
spec:
  minAvailable: "100%"  # Don't evict ANY running jobs
  selector:
    matchLabels:
      job-type: batch-processing
```

### 2. Extended termination grace period
```yaml
spec:
  terminationGracePeriodSeconds: 3600  # 1 hour for graceful shutdown
  containers:
  - name: batch-job
    lifecycle:
      preStop:
        exec:
          command: ["/bin/sh", "-c", "save_checkpoint && graceful_shutdown"]
```

### 3. Node affinity for batch pools
```yaml
spec:
  nodeSelector:
    cloud.google.com/gke-nodepool: batch-processing
  tolerations:
  - key: "batch-workload"
    operator: "Equal"
    value: "true"
    effect: "NoSchedule"
```

## Timeline and Maintenance Windows

### Recommended Schedule
```bash
# Set maintenance window during planned batch job gaps
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-03-16T02:00:00Z" \
  --maintenance-window-end "2024-03-16T10:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### Job-Aware Scheduling
- **Schedule batch jobs**: Start Friday evening, complete by Saturday morning
- **Upgrade window**: Saturday 2 AM - 10 AM (when jobs typically complete)
- **Buffer time**: 2-hour buffer between expected job completion and upgrade window

## Monitoring During Upgrade

### Track job completion before upgrading:
```bash
# Monitor running batch jobs
kubectl get jobs -A --field-selector status.conditions[0].type!=Complete

# Check pod status on nodes about to be upgraded
kubectl get pods -A --field-selector spec.nodeName=NODE_NAME,status.phase=Running

# Watch for pods that have been running >6 hours (likely long-running jobs)
kubectl get pods -A -o json | jq -r '.items[] | select((.status.startTime | fromdateiso8601) < (now - 21600)) | "\(.metadata.namespace)/\(.metadata.name)"'
```

## Rollback Plan

If something goes wrong:

```bash
# For autoscaled blue-green: fast rollback by uncordoning old pool
kubectl uncordon -l cloud.google.com/gke-nodepool=batch-processing-old

# For manual upgrades: create new pool at old version
gcloud container node-pools create batch-processing-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --node-version 1.30.x-gke.xxxx \
  --num-nodes 3
```

## Key Recommendations

1. **Use autoscaled blue-green upgrade** - designed exactly for your scenario with long-running workloads
2. **Maintain "no minor or node upgrades" exclusions** during active job campaigns
3. **Coordinate with your batch job scheduler** - align upgrades with natural job completion windows
4. **Implement checkpointing** in your jobs so they can resume after unexpected eviction
5. **Monitor job duration trends** to optimize your maintenance windows

This approach gives you security patches automatically while protecting your valuable long-running jobs from interruption.
# GKE Upgrade Plan for Long-Running Batch Jobs

## Executive Summary

Your 8-16 hour batch jobs exceed GKE's default 1-hour eviction timeout during surge upgrades, so standard upgrades will force-kill running jobs. I recommend **autoscaled blue-green upgrade strategy** combined with maintenance exclusions to protect active batch campaigns.

## Strategy Selection

**Primary recommendation: Autoscaled Blue-Green Upgrade**
- Respects extended `terminationGracePeriodSeconds` (no 1-hour force-eviction limit)
- Cost-efficient (scales down old pool as workloads drain to new pool)
- Allows jobs to complete naturally before eviction
- Ideal for 8+ hour workloads

**Alternative: Maintenance exclusions with planned upgrade windows**
- Block auto-upgrades during batch campaigns
- Manually upgrade during gaps between job runs

## Upgrade Plan

### Phase 1: Control Plane Upgrade (1.30 → 1.31)

```bash
# Pre-flight: Verify target version available
gcloud container get-server-config --zone YOUR_ZONE --format="yaml(channels.regular)"

# Upgrade control plane (no workload impact)
gcloud container clusters upgrade YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --master \
  --cluster-version 1.31.x-gke.xxxx
```

Control plane upgrades don't affect running workloads, so this can be done immediately.

### Phase 2: Node Pool Upgrade Strategy

**Option A: Autoscaled Blue-Green (Recommended)**

1. **Configure node pool for autoscaled blue-green:**
```bash
# Enable autoscaling if not already enabled
gcloud container node-pools update YOUR_BATCH_NODE_POOL \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --enable-autoscaling \
  --min-nodes 0 \
  --max-nodes YOUR_MAX_NODES

# Configure autoscaled blue-green upgrade
gcloud container node-pools update YOUR_BATCH_NODE_POOL \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --enable-blue-green-upgrade \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

2. **Configure batch pods for graceful termination:**
```yaml
# Add to your batch job specs
spec:
  terminationGracePeriodSeconds: 57600  # 16 hours
  containers:
  - name: batch-job
    image: your-batch-image
    # Add safe-to-evict annotation to prevent cluster autoscaler interference
  metadata:
    annotations:
      cluster-autoscaler.kubernetes.io/safe-to-evict: "false"
```

3. **Execute upgrade:**
```bash
gcloud container node-pools upgrade YOUR_BATCH_NODE_POOL \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --cluster-version 1.31.x-gke.xxxx
```

**Option B: Maintenance Exclusions + Planned Upgrade Windows**

1. **Add maintenance exclusion during active batch campaigns:**
```bash
gcloud container clusters update YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --add-maintenance-exclusion-name "batch-protection" \
  --add-maintenance-exclusion-start-time CAMPAIGN_START \
  --add-maintenance-exclusion-end-time CAMPAIGN_END \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

2. **Schedule upgrade during batch job gaps:**
```bash
# Remove exclusion
gcloud container clusters update YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --remove-maintenance-exclusion "batch-protection"

# Immediately trigger manual upgrade
gcloud container node-pools upgrade YOUR_BATCH_NODE_POOL \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --cluster-version 1.31.x-gke.xxxx
```

## Pre-Upgrade Checklist

```
Batch Job Upgrade Checklist
- [ ] Control plane upgraded to 1.31 (no workload impact)
- [ ] Batch jobs have checkpoint/resume capability
- [ ] terminationGracePeriodSeconds set to job duration + buffer (57600s for 16h jobs)
- [ ] safe-to-evict=false annotation on long-running batch pods
- [ ] Node pool configured for autoscaled blue-green OR maintenance exclusion applied
- [ ] Batch job submission paused 30 minutes before node upgrade
- [ ] Current batch jobs inventory documented (which jobs running, expected completion times)
- [ ] Monitoring configured for job completion rates and upgrade progress
```

## Validation Steps

**During upgrade:**
```bash
# Monitor node upgrade phases
kubectl get nodes -o wide --sort-by='.metadata.creationTimestamp'

# Check batch job status
kubectl get pods -l job-name=YOUR_BATCH_JOBS -o wide

# Verify no jobs force-killed
kubectl get events --field-selector reason=Killing
```

**Post-upgrade:**
```bash
# Confirm all nodes at 1.31
gcloud container node-pools list --cluster YOUR_CLUSTER_NAME --zone YOUR_ZONE

# Verify batch jobs resume normally
kubectl get jobs -A
```

## Why Standard Surge Won't Work

- **1-hour eviction timeout:** GKE force-evicts pods after 1 hour during surge upgrades, regardless of `terminationGracePeriodSeconds`
- **Job loss:** 8-16 hour jobs will be killed mid-execution, losing hours of compute work
- **No graceful completion:** Jobs can't finish processing and save state

## Expected Timeline

- **Control plane upgrade:** 10-15 minutes
- **Autoscaled blue-green node upgrade:** 2-4 hours for the upgrade process + time for existing jobs to complete naturally
- **Total window:** Plan for 6-20 hours depending on when current jobs complete

## Recommendations for Future Upgrades

1. **Dedicated batch node pool:** Isolate long-running jobs on a separate node pool with `no_minor_or_node_upgrades` exclusion for maximum control
2. **Checkpoint frequently:** Ensure jobs can resume from checkpoints if interruption occurs
3. **Job scheduling coordination:** Coordinate batch campaigns with your GKE upgrade schedule using maintenance windows

Would you like me to adjust this plan based on your specific batch job patterns or node pool configuration?
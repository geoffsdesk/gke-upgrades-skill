# GKE Upgrade Plan for Long-Running Batch Workloads

## Current Situation Analysis

**Problem:** Standard surge upgrades force-evict pods after 1 hour, which will kill your 8-16 hour batch jobs mid-execution.

**Recommended Strategy:** Use **autoscaled blue-green upgrade** — this is the ONLY native GKE strategy that respects extended graceful termination periods without the 1-hour force-eviction limit.

## Upgrade Plan

### Phase 1: Configure Batch Job Protection

**1. Update batch job pod specs with extended termination grace period:**
```yaml
apiVersion: v1
kind: Pod
spec:
  terminationGracePeriodSeconds: 57600  # 16 hours
  containers:
  - name: batch-job
    image: your-batch-image
    # Ensure job can handle SIGTERM gracefully for checkpointing
```

**2. Add safe-to-evict annotation to prevent premature eviction:**
```yaml
metadata:
  annotations:
    cluster-autoscaler.kubernetes.io/safe-to-evict: "false"
```

### Phase 2: Control Plane Upgrade

```bash
# Upgrade control plane first (mandatory before node pools)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.31.x-gke.latest

# Verify (~10-15 min wait)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

### Phase 3: Configure Autoscaled Blue-Green for Node Pools

**Enable autoscaling on your batch node pool:**
```bash
gcloud container node-pools update BATCH_NODE_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 3 \
  --total-max-nodes 50  # Adjust based on your needs
```

**Configure autoscaled blue-green upgrade:**
```bash
gcloud container node-pools update BATCH_NODE_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

### Phase 4: Execute Node Pool Upgrade

**Timing strategy — choose one:**

**Option A: Wait for natural job completion**
```bash
# 1. Pause new job submissions
# 2. Wait for current jobs to complete (up to 16 hours)
# 3. Upgrade empty pool
gcloud container node-pools upgrade BATCH_NODE_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.latest
```

**Option B: Upgrade with jobs running (autoscaled blue-green)**
```bash
# Upgrade immediately - autoscaled blue-green will:
# - Create new (green) nodes as needed
# - Scale down old (blue) nodes as jobs complete
# - Respect 16-hour termination grace period
gcloud container node-pools upgrade BATCH_NODE_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.latest
```

## How Autoscaled Blue-Green Works for Your Use Case

1. **Green pool creation:** New nodes (1.31) are created based on demand
2. **Blue pool cordon:** Old nodes (1.30) are cordoned but continue running existing jobs
3. **Gradual transition:** New jobs schedule on green nodes, existing jobs complete on blue nodes
4. **Respect termination grace:** Jobs get full 16 hours to complete gracefully
5. **Cost efficiency:** Blue pool scales down as jobs finish (no 2x resource spike)

## Pre-Upgrade Checklist

```
Long-Running Batch Job Upgrade Checklist
- [ ] Cluster: ___ | Current: 1.30 | Target: 1.31 | Channel: Regular

Batch Job Protection
- [ ] terminationGracePeriodSeconds set to 57600s (16 hours) on batch pods
- [ ] safe-to-evict: "false" annotation added to batch pods
- [ ] Jobs have checkpointing/resume capability verified
- [ ] Job scheduler can pause new submissions if needed

Node Pool Configuration  
- [ ] Autoscaling enabled on batch node pool
- [ ] Autoscaled blue-green rollout policy configured
- [ ] Sufficient quota for temporary additional nodes during transition
- [ ] Monitor batch job completion times in past week (baseline)

Upgrade Readiness
- [ ] 1.31 available in Regular channel confirmed
- [ ] No deprecated API usage (kubectl get --raw /metrics | grep deprecated)
- [ ] Maintenance window configured for off-peak hours
- [ ] Rollback plan documented (create new pool at 1.30 if needed)
```

## Alternative: Maintenance Exclusion Strategy

If autoscaled blue-green isn't suitable, use maintenance exclusions:

```bash
# Block node upgrades during batch campaigns
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "batch-campaign" \
  --add-maintenance-exclusion-start-time 2024-MM-DDTHH:MM:SSZ \
  --add-maintenance-exclusion-end-time 2024-MM-DDTHH:MM:SSZ \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Upgrade manually during planned batch downtime
```

## Why Not Standard Surge?

❌ **Standard surge upgrade:** Force-evicts after 1 hour regardless of terminationGracePeriodSeconds — will kill your 8-16 hour jobs

❌ **Standard blue-green:** Requires 2x resource capacity throughout the upgrade

✅ **Autoscaled blue-green:** Designed exactly for this scenario — respects long termination periods and scales efficiently

## Monitoring During Upgrade

```bash
# Watch node pool transition
kubectl get nodes -o wide -L cloud.google.com/gke-nodepool

# Monitor running batch jobs
kubectl get pods -l job-type=batch -o wide

# Check for any stuck terminating pods
kubectl get pods -A | grep Terminating
```

The autoscaled blue-green strategy is specifically designed for workloads like yours that cannot tolerate the 1-hour eviction timeout of standard surge upgrades.
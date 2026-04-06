# GKE Upgrade Plan for Long-Running Batch Jobs

Your 8-16 hour batch jobs need special handling because GKE's default surge upgrade strategy will **force-evict pods after 1 hour** — far shorter than your job duration. Here's a comprehensive approach:

## Recommended Strategy: Autoscaled Blue-Green Upgrade

For your long-running batch workloads, **autoscaled blue-green** is the ideal strategy. It's specifically designed for jobs exceeding GKE's 1-hour eviction timeout and respects extended graceful termination periods.

### Why autoscaled blue-green works for batch jobs:
- **No 1-hour force-eviction** — respects longer `terminationGracePeriodSeconds`
- **Cost-efficient** — scales down old nodes as jobs complete, unlike standard blue-green's 2x resource requirement
- **Graceful transition** — jobs can complete naturally before node deletion

## Upgrade Plan

### Phase 1: Pre-Upgrade Preparation

**1. Configure batch job protection:**
```bash
# Ensure batch pods have extended termination grace period
kubectl patch deployment BATCH_JOB_NAME \
  -p '{"spec":{"template":{"spec":{"terminationGracePeriodSeconds":57600}}}}'
# 57600s = 16 hours (adjust to your max job duration)

# Add safe-to-evict annotation to prevent premature eviction
kubectl annotate pods -l app=BATCH_JOB_NAME \
  cluster-autoscaler.kubernetes.io/safe-to-evict="false"
```

**2. Pause new job submissions:**
- Stop your job scheduler/cron 30 minutes before upgrade
- Let currently running jobs continue uninterrupted
- Monitor active jobs: `kubectl get pods -l app=BATCH_JOB_NAME -o wide`

**3. Verify upgrade prerequisites:**
```bash
# Check current versions
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="value(currentMasterVersion,nodePools[].version)"

# Confirm 1.31 available in Regular channel
gcloud container get-server-config --region REGION \
  --format="yaml(channels.regular)"

# Check for deprecated APIs (common upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
```

### Phase 2: Control Plane Upgrade

```bash
# Upgrade control plane first (required before node pools)
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version 1.31.X-gke.XXXX

# Verify CP upgrade (takes ~10-15 minutes)
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="value(currentMasterVersion)"
```

### Phase 3: Node Pool Upgrade with Autoscaled Blue-Green

**Configure the batch node pool for autoscaled blue-green:**
```bash
# Enable autoscaling (required for autoscaled blue-green)
gcloud container node-pools update BATCH_NODE_POOL \
  --cluster CLUSTER_NAME \
  --region REGION \
  --enable-autoscaling \
  --total-min-nodes 3 \
  --total-max-nodes 20

# Configure autoscaled blue-green strategy
gcloud container node-pools update BATCH_NODE_POOL \
  --cluster CLUSTER_NAME \
  --region REGION \
  --enable-blue-green-upgrade \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

**Start the upgrade:**
```bash
gcloud container node-pools upgrade BATCH_NODE_POOL \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.31.X-gke.XXXX
```

### How Autoscaled Blue-Green Works for Your Jobs

1. **Green pool creation**: GKE creates 25% of nodes in the new (green) pool with 1.31
2. **Blue pool cordon**: Old (blue) pool is cordoned — no new pods scheduled there
3. **Gradual migration**: As batch jobs complete on blue nodes, those nodes scale down
4. **Green pool scale-up**: New batch jobs (when you resume submissions) land on green nodes
5. **Natural completion**: Long-running jobs finish on blue nodes without forced eviction
6. **Cleanup**: Blue pool scales to zero as all jobs complete

### Phase 4: Monitoring and Validation

**Monitor upgrade progress:**
```bash
# Track node pool upgrade status
gcloud container node-pools describe BATCH_NODE_POOL \
  --cluster CLUSTER_NAME \
  --region REGION \
  --format="value(upgradeSettings,status)"

# Monitor batch job distribution across node versions
kubectl get pods -l app=BATCH_JOB_NAME -o wide \
  --sort-by='.spec.nodeName'

# Check nodes by version
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion
```

**Resume job submissions when safe:**
- Wait until at least 2-3 green nodes are Ready
- Test with a short job first
- Gradually resume normal job scheduling

## Alternative: Maintenance Exclusion + Scheduled Upgrade

If you prefer maximum control and can plan upgrades during job gaps:

```bash
# Block auto-upgrades during batch campaigns
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "batch-processing-campaign" \
  --add-maintenance-exclusion-start-time 2024-01-15T00:00:00Z \
  --add-maintenance-exclusion-end-time 2024-01-25T00:00:00Z \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Manually upgrade during scheduled maintenance windows
# Remove exclusion and upgrade when no batch jobs are running
```

## Pre-Upgrade Checklist

```
Batch Job Upgrade Checklist
- [ ] Cluster: YOUR_CLUSTER | Standard | Regular channel
- [ ] Current version: 1.30.x | Target version: 1.31.x

Batch Job Protection
- [ ] terminationGracePeriodSeconds set to 57600s (16h) on batch pods
- [ ] safe-to-evict=false annotation applied to long-running jobs
- [ ] Job scheduler paused 30 minutes before upgrade
- [ ] Active job inventory documented
- [ ] Checkpoint/resume capability verified for critical jobs

Node Pool Configuration
- [ ] Autoscaling enabled on batch node pool
- [ ] Autoscaled blue-green strategy configured
- [ ] blue-green-initial-node-percentage=0.25 (creates 25% green nodes initially)
- [ ] blue-green-full-batch-timeout=3600s (1h timeout for green pool readiness)

Ops Readiness
- [ ] Upgrade window scheduled during low batch activity
- [ ] Monitoring active for job completion rates
- [ ] Rollback plan documented (resume on blue nodes if needed)
```

## Expected Timeline

- **Control plane**: 10-15 minutes
- **Node pool upgrade**: 4-8 hours (depends on job completion rate)
- **Total window**: Plan for 8-12 hours to allow jobs to complete naturally

This approach protects your long-running jobs while ensuring a smooth upgrade to 1.31. The autoscaled blue-green strategy is specifically designed for workloads like yours that exceed GKE's default 1-hour eviction timeout.
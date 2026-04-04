# GKE Upgrade Plan: Long-Running Batch Jobs (8-16 Hours)

## Challenge Analysis

Your 8-16 hour batch jobs face a critical constraint with GKE's default upgrade behavior:
- **GKE's surge upgrade timeout is 1 hour** — after this, pods are force-evicted regardless of graceful termination settings
- Standard surge upgrades will kill your long-running jobs mid-execution
- Need a strategy that respects job completion time

## Recommended Strategy: Autoscaled Blue-Green Upgrade

**Primary recommendation:** Use GKE's **autoscaled blue-green upgrade strategy** for your batch node pools. This is the ONLY native GKE strategy that respects longer graceful termination periods without force-eviction.

### Why Autoscaled Blue-Green for Batch Jobs

- **Respects extended terminationGracePeriodSeconds** (no 1-hour force-eviction limit)
- **Cost-efficient** — scales down old pool as jobs complete, unlike standard blue-green
- **Wait-for-drain semantics** — GKE waits for jobs to finish naturally
- **Autoscaled replacement** — new nodes provision based on actual demand

### Configuration Commands

```bash
# Configure your batch node pool for autoscaled blue-green
gcloud container node-pools update BATCH_NODE_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --enable-autoscaling \
    --total-min-nodes 0 \
    --total-max-nodes MAX_NODES \
    --strategy AUTOSCALED_BLUE_GREEN \
    --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

# Set extended termination grace period on batch pods (in your job spec)
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 57600  # 16 hours
      containers:
      - name: batch-job
        # Add safe-to-evict annotation to prevent cluster autoscaler interference
        annotations:
          cluster-autoscaler.kubernetes.io/safe-to-evict: "false"
```

## Alternative Strategy: Maintenance Exclusions + Scheduled Windows

If you prefer to stick with surge upgrades but control timing:

### Step 1: Apply "No Minor or Node Upgrades" Exclusion
```bash
# Block disruptive upgrades while allowing CP security patches
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "batch-campaign-protection" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
```

### Step 2: Schedule Manual Upgrades During Job Gaps
```bash
# When you have a gap between batch campaigns:
# 1. Ensure no jobs are running
kubectl get pods -n BATCH_NAMESPACE | grep -v Completed

# 2. Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
    --zone ZONE \
    --master \
    --cluster-version 1.31.x-gke.xxxx

# 3. Upgrade batch node pools with conservative settings
gcloud container node-pools update BATCH_NODE_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --max-surge-upgrade 1 \
    --max-unavailable-upgrade 0

gcloud container node-pools upgrade BATCH_NODE_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version 1.31.x-gke.xxxx
```

## Pre-Upgrade Checklist

```
Long-Running Batch Job Upgrade Checklist

Job Protection Setup
- [ ] Batch jobs have checkpoint/resume capability
- [ ] terminationGracePeriodSeconds set to 57600s (16 hours) in job specs
- [ ] safe-to-evict=false annotation on batch pods
- [ ] Job submission pipeline can be paused/resumed

Node Pool Configuration (Autoscaled Blue-Green)
- [ ] Batch node pool has autoscaling enabled
- [ ] total-min-nodes=0, total-max-nodes set appropriately
- [ ] Autoscaled blue-green strategy configured
- [ ] blue-green-initial-node-percentage=25% (or appropriate for your workload)

Version Compatibility
- [ ] Kubernetes 1.30 → 1.31 breaking changes reviewed
- [ ] Batch framework (Argo Workflows, Kubeflow, etc.) compatible with 1.31
- [ ] No deprecated APIs in batch job definitions

Operational Readiness
- [ ] Current batch campaign status documented
- [ ] Job completion timeline estimated
- [ ] Monitoring for stuck/failed jobs during upgrade
- [ ] Rollback plan if jobs fail to restart properly
```

## Upgrade Execution Plan

### Phase 1: Control Plane Upgrade
```bash
# Control plane upgrade (minimal disruption to running jobs)
gcloud container clusters upgrade CLUSTER_NAME \
    --zone ZONE \
    --master \
    --cluster-version 1.31.x-gke.xxxx
```

### Phase 2: Non-Batch Node Pools (if any)
```bash
# Upgrade other node pools first with standard surge
gcloud container node-pools upgrade NON_BATCH_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version 1.31.x-gke.xxxx
```

### Phase 3: Batch Node Pool (Autoscaled Blue-Green)
```bash
# This respects your 16-hour termination grace period
gcloud container node-pools upgrade BATCH_NODE_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version 1.31.x-gke.xxxx
```

## Monitoring Commands During Upgrade

```bash
# Track job completion
kubectl get jobs -n BATCH_NAMESPACE -o wide

# Monitor node upgrade progress
watch 'kubectl get nodes -L cloud.google.com/gke-nodepool -o wide'

# Check for stuck pods during drain
kubectl get pods -A | grep Terminating

# Verify new nodes are ready for future jobs
kubectl get nodes --show-labels | grep batch-pool
```

## Post-Upgrade Validation

```bash
# Verify all nodes upgraded
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion

# Test job submission on new nodes
kubectl run test-batch-job --image=busybox --restart=Never \
    --overrides='{"spec":{"nodeSelector":{"cloud.google.com/gke-nodepool":"BATCH_NODE_POOL_NAME"}}}' \
    -- sleep 30

# Confirm batch scheduling works
kubectl describe pod test-batch-job | grep Node:
```

## Key Advantages of This Approach

1. **Zero job kills** — autoscaled blue-green waits for natural completion
2. **Cost control** — old nodes scale down as jobs finish (vs. 2x cost of standard blue-green)
3. **Maintained throughput** — new nodes spin up to handle workload demand
4. **Native GKE support** — no custom scripting required

## Important Notes

- **Autoscaled blue-green is Preview** — monitor GKE release notes for GA status
- **Test in staging first** — verify your batch framework works correctly after upgrade
- **Plan for extended upgrade windows** — 16-hour jobs mean the upgrade could take 16+ hours to complete
- **Checkpoint capability is critical** — ensure jobs can resume from checkpoints if any issues arise

This strategy gives you the control you need while using GKE's native capabilities designed exactly for your use case.
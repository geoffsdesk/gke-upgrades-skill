# GKE Version Skew Recovery Plan

## Current State Analysis

You have a **critical version skew violation**:
- **Control plane:** 1.31
- **Problem node pool:** 1.28
- **Skew:** 3 minor versions behind (violates the 2-version limit)

This is an **unsupported configuration** that can cause:
- Kubelet communication failures with API server
- Pod scheduling issues
- Unpredictable workload behavior
- Potential data plane outages

GKE will **force-upgrade** this node pool soon to bring it into compliance. You need to act quickly.

## Immediate Recovery Options

### Option A: Emergency Skip-Level Upgrade (Recommended)

Upgrade the 1.28 node pool directly to 1.31 in a single jump:

```bash
# First, configure conservative surge settings to minimize disruption
gcloud container node-pools update YOUR_POOL_NAME \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Emergency skip-level upgrade: 1.28 → 1.31
gcloud container node-pools upgrade YOUR_POOL_NAME \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --node-version 1.31.X-gke.XXXX
```

**Why skip-level works:** GKE supports N+2 upgrades within the 2-version skew limit. Since your control plane is at 1.31, you can jump 1.28→1.31 directly.

### Option B: Two-Step Sequential (If Skip-Level Fails)

If the skip-level upgrade fails due to compatibility issues:

```bash
# Step 1: 1.28 → 1.29
gcloud container node-pools upgrade YOUR_POOL_NAME \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --node-version 1.29.X-gke.XXXX

# Wait for completion, then Step 2: 1.29 → 1.31
gcloud container node-pools upgrade YOUR_POOL_NAME \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --node-version 1.31.X-gke.XXXX
```

### Option C: Replace Node Pool (If Upgrades Fail)

If both upgrade paths fail due to workload compatibility:

```bash
# Create new pool at 1.31
gcloud container node-pools create new-pool-1-31 \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --node-version 1.31.X-gke.XXXX \
  --num-nodes YOUR_NODE_COUNT \
  --machine-type YOUR_MACHINE_TYPE

# Cordon old pool and migrate workloads
kubectl cordon -l cloud.google.com/gke-nodepool=YOUR_OLD_POOL_NAME

# Drain nodes one by one
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --grace-period=300

# Delete old pool after migration completes
gcloud container node-pools delete YOUR_OLD_POOL_NAME \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE
```

## Pre-Flight Checks (Critical)

Before starting ANY upgrade path:

```bash
# 1. Check for deprecated API usage (major risk with 3-version jump)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# 2. Verify workloads have proper controllers (no bare pods)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# 3. Check PDB configurations
kubectl get pdb -A -o wide

# 4. Verify available versions
gcloud container get-server-config --zone YOUR_ZONE --format="yaml(validNodeVersions)"
```

## Workload Compatibility Risks

The 1.28→1.31 jump spans **significant Kubernetes changes**:
- **API deprecations:** Several APIs removed in 1.29-1.31
- **CSI driver changes:** Storage behavior differences
- **Network policy updates:** CNI compatibility issues possible
- **RBAC changes:** Permission model updates

**Critical:** Test in a staging cluster first if you have one.

## Monitoring During Upgrade

```bash
# Watch node versions converge
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Monitor problematic pods
kubectl get pods -A | grep -E "Pending|CrashLoop|Error"

# Check upgrade operation status
gcloud container operations list --cluster YOUR_CLUSTER_NAME --zone YOUR_ZONE --limit=5
```

## Prevention Strategy

To avoid this situation in the future:

1. **Enroll in a release channel** if you're on "No channel":
   ```bash
   gcloud container clusters update YOUR_CLUSTER_NAME \
     --zone YOUR_ZONE \
     --release-channel regular
   ```

2. **Set up maintenance exclusions** for controlled upgrades instead of letting nodes drift:
   ```bash
   # Allow patches but control minor versions
   gcloud container clusters update YOUR_CLUSTER_NAME \
     --zone YOUR_ZONE \
     --add-maintenance-exclusion-scope no_minor_upgrades \
     --add-maintenance-exclusion-until-end-of-support
   ```

3. **Configure maintenance windows** for predictable timing:
   ```bash
   gcloud container clusters update YOUR_CLUSTER_NAME \
     --zone YOUR_ZONE \
     --maintenance-window-start "2024-01-06T02:00:00Z" \
     --maintenance-window-duration 4h \
     --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
   ```

## Immediate Action Required

**You need to fix this TODAY.** The longer this skew persists:
- Higher risk of forced upgrade during business hours
- More deprecated API accumulation
- Greater blast radius when the eventual upgrade happens

Start with **Option A (skip-level)** unless you have specific compatibility concerns. The 1.28→1.31 jump is supported and will resolve the violation fastest.

Would you like me to help you adapt these commands to your specific cluster details, or do you need guidance on any particular compatibility concerns?
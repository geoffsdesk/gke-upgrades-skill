You're dealing with **excessive version skew** - your node pool is 3 minor versions behind the control plane, which violates GKE's support policy. Here's what's happening and how to fix it:

## What You're Dealing With

**Critical constraint violation:** Nodes can't be more than 2 minor versions behind the control plane. Your setup (CP: 1.31, Nodes: 1.28) exceeds this limit.

**Immediate risks:**
- **End of Support enforcement:** 1.28 reached EoS in late 2024. GKE will force-upgrade this node pool soon regardless of maintenance exclusions
- **API compatibility issues:** Some 1.31 control plane features may not work with 1.28 nodes
- **Support limitations:** This configuration is outside GKE's supported version skew policy

## Recovery Plan

### Option 1: Skip-Level Node Pool Upgrade (Recommended)

Since your control plane is already at 1.31, you can jump the node pool directly from 1.28 → 1.30 (the maximum allowed skip), then 1.30 → 1.31.

```bash
# Pre-flight check
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].version)"

# Step 1: Skip-level upgrade 1.28 → 1.30
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30.8-gke.1453000  # Use latest 1.30 patch

# Wait for completion, then Step 2: 1.30 → 1.31
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.4-gke.1109000  # Match your control plane version
```

### Option 2: New Node Pool Migration (If upgrade fails)

If the skip-level upgrade fails due to deprecated APIs or other issues:

```bash
# Create new node pool at target version
gcloud container node-pools create NODE_POOL_NAME-new \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.4-gke.1109000 \
  --num-nodes NUM_NODES \
  --machine-type MACHINE_TYPE \
  --disk-size DISK_SIZE

# Cordon old pool to prevent new pods
kubectl cordon -l cloud.google.com/gke-nodepool=NODE_POOL_NAME

# Drain workloads to new pool
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --grace-period=300

# After migration, delete old pool
gcloud container node-pools delete NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE
```

## Pre-Upgrade Checklist

Before starting either option:

```markdown
- [ ] **Deprecated API check:** `kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated`
- [ ] **Backup stateful workloads** - 3 minor version jumps have higher risk
- [ ] **PDBs configured** for critical workloads
- [ ] **Check for 1.29-1.31 breaking changes** in [GKE release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes)
- [ ] **Maintenance window** set for off-peak hours
- [ ] **Surge settings:** Conservative `maxSurge=1, maxUnavailable=0` for the risky jump
```

## How This Happened (And Prevention)

**Common causes:**
- Node pool auto-upgrade was disabled on "No channel" clusters
- Maintenance exclusions applied too long without catch-up plan
- Manual version management without monitoring version skew

**Prevention going forward:**
```bash
# Migrate to a release channel for automated lifecycle management
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular

# Set up maintenance windows instead of disabling auto-upgrade
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-12-01T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SUN"
```

## Immediate Action Required

**This is urgent** - 1.28 is past End of Support and GKE will force-upgrade this node pool soon. Start the skip-level upgrade process immediately to maintain control over the timing and process.

Would you like me to help you check for deprecated APIs or create a more detailed runbook for your specific node pool configuration?
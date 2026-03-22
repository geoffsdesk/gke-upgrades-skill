You're dealing with **version skew violation** - your node pool (1.28) is 3 minor versions behind your control plane (1.31), which exceeds GKE's supported skew of 2 minor versions. This creates stability risks and blocks further upgrades.

## What you're dealing with

- **Supported skew:** Nodes can be up to 2 minor versions behind the control plane
- **Your skew:** 3 minor versions (1.28 → 1.31)
- **Impact:** API compatibility issues, potential pod scheduling problems, blocks auto-upgrades
- **Urgency:** High - this needs immediate attention

## Fix Strategy

You have two options. I recommend **Option A** for safety:

### Option A: Sequential node pool upgrades (Recommended)

Upgrade the node pool through intermediate versions to minimize risk:

```bash
# Check current state
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE

# Upgrade 1.28 → 1.29 first
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.29.latest

# Wait for completion, then 1.29 → 1.30
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30.latest

# Finally 1.30 → 1.31
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.latest
```

### Option B: Skip-level upgrade (Faster but riskier)

GKE supports N+2 node pool upgrades, so you can jump directly:

```bash
# Direct upgrade 1.28 → 1.31
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.latest
```

## Pre-upgrade Safety Checks

Before either approach:

```bash
# Verify no deprecated APIs between 1.28 and 1.31
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Check workload health
kubectl get pods -A | grep -v Running | grep -v Completed

# Verify PDBs won't block drain
kubectl get pdb -A -o wide

# Configure appropriate surge settings for your workload type
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0  # Safe default
```

## How this happened (and prevention)

This typically occurs when:
- Auto-upgrades were disabled on the node pool but not the control plane
- Maintenance exclusions were applied inconsistently
- The cluster is on legacy "No channel" with mixed upgrade policies

**Prevention:** Use release channels with cluster-level maintenance exclusions to keep control plane and nodes synchronized:

```bash
# Check if you're on a release channel
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(releaseChannel.channel)"

# If "No channel", migrate to Regular channel
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular
```

## Timeline expectation

- **Sequential upgrades:** 2-4 hours total (depends on node count and surge settings)
- **Skip-level upgrade:** 45-90 minutes
- Each upgrade includes drain time + node recreation + pod rescheduling

Start with the 1.28 → 1.29 upgrade and monitor closely. If it goes smoothly, you can consider skip-level for the remaining hops. The version skew warnings will disappear once your nodes reach 1.29 or higher.
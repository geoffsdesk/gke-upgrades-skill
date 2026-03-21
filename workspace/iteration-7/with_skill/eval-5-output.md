# GKE Version Skew Issue - Critical Fix Required

## What you're dealing with

You have a **critical version skew violation**. GKE requires node pools to be within **2 minor versions** of the control plane:

- **Control plane:** 1.31
- **Node pool:** 1.28  
- **Skew:** 3 minor versions (1.28 → 1.29 → 1.30 → 1.31)

This violates GKE's supported configuration and can cause:
- API compatibility issues (kubelet can't communicate properly with API server)
- Workload scheduling failures
- Security vulnerabilities (1.28 is likely approaching End of Support)
- Potential cluster instability

## Immediate fix required

You **must** upgrade the 1.28 node pool, but you have options for the upgrade path:

### Option 1: Skip-level upgrade (fastest, recommended)
Upgrade directly from 1.28 → 1.31 in a single step:

```bash
# Check current state
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Upgrade node pool directly to 1.31 (skip-level supported)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.X-gke.XXXX
```

### Option 2: Sequential upgrades (more conservative)
If you prefer staged upgrades: 1.28 → 1.29 → 1.30 → 1.31

```bash
# Upgrade to 1.29 first
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.29.X-gke.XXXX

# Wait for completion, then continue to 1.30, then 1.31
```

## Pre-upgrade checklist for your situation

```
Critical Version Skew Fix
- [ ] Cluster: ___ | Current CP: 1.31 | Problem node pool: ___ at 1.28
- [ ] Target version available: `gcloud container get-server-config --zone ZONE`
- [ ] Workload readiness verified (PDBs, no bare pods, resource requests)
- [ ] Upgrade strategy configured:
      - maxSurge=___ maxUnavailable=___ (recommend maxSurge=2, maxUnavailable=0 for faster resolution)
- [ ] Maintenance window scheduled (this upgrade is required regardless)
- [ ] Monitoring active to track progress
```

## Commands to execute

```bash
# 1. Check available versions for your cluster's release channel
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels)" | grep -A 10 "channel: REGULAR"

# 2. Configure surge settings for faster upgrade
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# 3. Execute skip-level upgrade to 1.31
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.X-gke.XXXX

# 4. Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# 5. Verify completion
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE
kubectl get nodes | grep Ready
```

## How this happened (prevention)

This typically occurs when:
1. **Auto-upgrades disabled** or cluster on legacy "No channel"
2. **Node pool excluded** from maintenance while control plane upgraded
3. **Manual intervention** that broke the upgrade sequence

**Prevention:** Ensure your cluster is on a release channel (Regular/Stable) with proper maintenance windows and exclusions rather than disabling auto-upgrades entirely.

## Timeline expectations

- **Skip-level upgrade (1.28→1.31):** 30-60 minutes depending on node pool size
- **Critical priority:** This isn't just a warning - version skew this severe can impact cluster functionality

Fix this ASAP. The 3-version skew puts you in unsupported territory and the 1.28 nodes are likely approaching End of Support enforcement.
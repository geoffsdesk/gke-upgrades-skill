You're in a **mixed-version state** with 8 nodes at 1.32 and 12 nodes still at the previous version. This is completely **valid and functional** - GKE allows nodes within 2 minor versions of the control plane, and your workloads will continue running normally.

Here's your recovery plan:

## Immediate Status Assessment

First, let's understand what you have:

```bash
# Check current node versions
kubectl get nodes -o wide -L cloud.google.com/gke-nodepool
gcloud container node-pools list --cluster CLUSTER_NAME --region REGION

# Verify workloads are healthy
kubectl get pods -A | grep -v Running | grep -v Completed
```

## Recovery Options

**Option A: Retry the upgrade (recommended)**

This is usually the simplest path - fix the root cause and resume:

```bash
# First diagnose why it failed - check recent operations
gcloud container operations list --cluster CLUSTER_NAME --region REGION --limit=5

# Most common causes and fixes:
# 1. PDB blocking drain
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# 2. Resource constraints  
kubectl get pods -A | grep Pending
kubectl top nodes

# 3. Bare pods blocking drain
kubectl get pods -A -o json | jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

Once you've fixed the root cause, resume the upgrade:

```bash
gcloud container node-pools upgrade MAIN_WORKLOAD_POOL \
  --cluster CLUSTER_NAME \
  --region REGION \
  --node-version 1.32.x-gke.xxxx
```

**Option B: Rollback (only if retry isn't viable)**

If the target version has critical issues or the root cause can't be fixed:

```bash
# Create new node pool at previous version
gcloud container node-pools create MAIN_WORKLOAD_POOL-rollback \
  --cluster CLUSTER_NAME \
  --region REGION \
  --node-version PREVIOUS_VERSION \
  --num-nodes 20 \
  --machine-type MACHINE_TYPE

# Cordon the mixed-version pool
kubectl cordon -l cloud.google.com/gke-nodepool=MAIN_WORKLOAD_POOL

# Drain workloads to new pool
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --grace-period=300

# Delete old pool once migration complete
gcloud container node-pools delete MAIN_WORKLOAD_POOL --cluster CLUSTER_NAME --region REGION
```

## What About the Other Two Node Pools?

**Don't upgrade them yet.** Wait until your main workload pool issue is resolved. Once that's stable at 1.32, proceed with the other pools:

```bash
# Upgrade remaining pools one at a time
gcloud container node-pools upgrade POOL_2_NAME \
  --cluster CLUSTER_NAME \
  --region REGION \
  --node-version 1.32.x-gke.xxxx
```

## Key Points

- **Your cluster is operational** - mixed versions are supported
- **Retry is usually simpler** than rollback since nodes will converge to a single version
- **Fix the root cause first** - otherwise the retry will fail at the same point
- **One pool at a time** - don't start other pool upgrades until this is resolved

What error message did you see when the upgrade failed? That will help pinpoint the exact root cause and the fastest fix.
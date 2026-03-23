I'll help you diagnose and fix the stuck node pool upgrade. Since your control plane is already on 1.32, we need to get your node pools upgraded to maintain version compatibility.

## Immediate Diagnostic Steps

First, let's identify what's blocking the upgrade:

```bash
# Check current upgrade operation status
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES"

# See which nodes are upgraded vs stuck
kubectl get nodes -o wide -L cloud.google.com/gke-nodepool

# Check for stuck/pending pods (most common cause)
kubectl get pods -A | grep -v Running | grep -v Completed

# Look for PDB issues (very common blocker)
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0
```

## Most Common Fixes

**1. PDB Blocking Drain** (happens in ~70% of stuck upgrades)
```bash
# Check which PDBs are preventing eviction
kubectl describe pdb -A | grep -A 10 -B 5 "DisruptionsAllowed.*0"

# Temporarily relax the problematic PDB
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'
```

**2. Resource Constraints** (no room for pods on remaining nodes)
```bash
# Check node resource usage
kubectl top nodes
kubectl describe nodes | grep -A 5 "Allocated resources"

# If nodes are packed, increase surge capacity
gcloud container node-pools update MAIN_WORKLOAD_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

**3. Bare Pods** (can't be rescheduled)
```bash
# Find pods without owner references
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# Delete them (they won't reschedule anyway)
kubectl delete pod POD_NAME -n NAMESPACE
```

## Recovery Steps

1. **Resume the stuck upgrade** - After fixing the blocking issue above:
```bash
# The upgrade should automatically resume
# Monitor progress:
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
```

2. **If upgrade doesn't auto-resume** (rare), you may need to retry:
```bash
# Get the target version from your upgraded nodes
TARGET_VERSION=$(kubectl get nodes -l cloud.google.com/gke-nodepool=MAIN_WORKLOAD_POOL -o jsonpath='{.items[0].status.nodeInfo.kubeletVersion}' | grep -o 'v1\.32\.[0-9]*')

# Retry the node pool upgrade
gcloud container node-pools upgrade MAIN_WORKLOAD_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version ${TARGET_VERSION#v}
```

3. **After main pool completes**, upgrade your remaining node pools:
```bash
# Upgrade remaining pools one at a time
gcloud container node-pools upgrade NODE_POOL_2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

## Validation Commands

```bash
# Confirm all nodes are upgraded and healthy
kubectl get nodes -o wide

# Check all workloads are running
kubectl get pods -A | grep -v Running | grep -v Completed

# Verify no stuck operations
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --limit=5
```

## If Still Stuck

If the above doesn't resolve it after 30 minutes, contact GKE support with:
- Cluster name and zone
- Operation ID from the operations list
- Timeline of when it stuck
- Any error messages from the console

The key insight: **partial upgrades are normal and recoverable**. The most likely cause is a PDB or resource constraint that can be quickly resolved. Once fixed, the upgrade typically resumes automatically.

What specific error message are you seeing, and what does `kubectl get pdb -A` show?
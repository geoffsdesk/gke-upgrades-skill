# GKE Node Pool Upgrade Recovery Plan

Your situation: Control plane at 1.32 ✅, main workload pool partially upgraded (8/20 nodes), upgrade stuck, 2 other pools pending.

## Immediate Diagnosis

First, let's understand why the upgrade stopped:

```bash
# Check current upgrade operation status
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES" --limit=5

# Get detailed error from the failed operation
gcloud container operations describe OPERATION_ID --zone ZONE

# Check node status - identify which nodes are on which versions
kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep MAIN_POOL_NAME
```

## Common Causes & Fixes

Work through these in order:

### 1. PDB Blocking Drain (Most Likely)
```bash
# Check for overly restrictive PDBs
kubectl get pdb -A -o wide
kubectl describe pdb PDB_NAME -n NAMESPACE

# Look for ALLOWED DISRUPTIONS = 0
# If found, temporarily relax:
kubectl patch pdb PDB_NAME -n NAMESPACE -p '{"spec":{"maxUnavailable":"50%"}}'
```

### 2. Pods Stuck Terminating
```bash
# Find stuck pods on nodes being drained
kubectl get pods -A --field-selector=status.phase=Running -o wide | grep NODE_NAME
kubectl get pods -A | grep Terminating

# Check for long termination grace periods
kubectl get pods -A -o json | jq '.items[] | select(.spec.terminationGracePeriodSeconds > 300) | {ns:.metadata.namespace, name:.metadata.name, grace:.spec.terminationGracePeriodSeconds}'
```

### 3. Resource Constraints
```bash
# Check if remaining nodes have capacity for rescheduled pods
kubectl describe nodes | grep -A 5 "Allocated resources"
kubectl get events -A --field-selector reason=FailedScheduling
```

## Recovery Options

### Option A: Resume Current Upgrade (Recommended)

Fix the blocking issue above, then the upgrade should automatically resume:

```bash
# After fixing PDB/stuck pods, monitor for automatic resumption
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# If it doesn't resume after 10-15 minutes, retry the upgrade command:
gcloud container node-pools upgrade MAIN_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

### Option B: Increase Parallelism (If Resource-Constrained)

```bash
# Increase surge to speed up completion
gcloud container node-pools update MAIN_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0

# Then retry upgrade
gcloud container node-pools upgrade MAIN_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

### Option C: Blue-Green Recovery (If Other Options Fail)

```bash
# Create new pool at target version
gcloud container node-pools create MAIN_POOL_NAME-v132 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32 \
  --num-nodes 20 \
  --machine-type MACHINE_TYPE \
  --disk-size DISK_SIZE \
  --enable-autoscaling --min-nodes MIN --max-nodes MAX

# Wait for new pool ready
kubectl get nodes -l cloud.google.com/gke-nodepool=MAIN_POOL_NAME-v132

# Cordon old pool to stop new pods
kubectl cordon -l cloud.google.com/gke-nodepool=MAIN_POOL_NAME

# Drain old nodes gracefully
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --grace-period=60

# After all workloads migrated, delete old pool
gcloud container node-pools delete MAIN_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE
```

## Next Steps for Remaining Pools

Once your main pool is resolved:

1. **Learn from the issue** - apply the same fix (PDB relaxation, etc.) to other pools before upgrading them
2. **Upgrade remaining pools** - you can do them simultaneously if they don't have the same blocking issue:

```bash
# Upgrade both remaining pools (replace with actual names)
gcloud container node-pools upgrade POOL_2_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32 &

gcloud container node-pools upgrade POOL_3_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32 &

# Monitor both
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
```

## Validation Checklist

After recovery:
- [ ] All nodes showing version 1.32: `kubectl get nodes -o wide`
- [ ] No pods stuck: `kubectl get pods -A | grep -v Running | grep -v Completed`
- [ ] Applications responding normally
- [ ] Restore original PDB settings if temporarily modified

**Most likely cause:** Check your PDBs first - that's the #1 reason node pool upgrades get stuck partway through. Once you relax the blocking PDB, the upgrade typically resumes automatically within 10-15 minutes.
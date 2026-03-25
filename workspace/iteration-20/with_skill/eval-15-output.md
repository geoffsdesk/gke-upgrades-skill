# Node Pool Upgrade Recovery Plan

## Current Situation Assessment

**Cluster state:** Mixed-version node pool (8 nodes at 1.32, 12 nodes at previous version)
- **This is a VALID and functional state** — GKE allows nodes within 2 minor versions of control plane
- **No immediate action required** — workloads continue running normally
- **Two recovery options:** Retry (recommended) or rollback

## Option A: Retry Upgrade (Recommended)

This is usually the fastest path to resolution.

### Step 1: Diagnose the failure cause

```bash
# Check recent operations for error details
gcloud container operations list --cluster CLUSTER_NAME --region REGION \
  --filter="operationType=UPGRADE_NODES" --limit=5

# Get specific operation details
gcloud container operations describe OPERATION_ID --region REGION

# Check for common blocking issues
kubectl get pdb -A -o wide  # Look for ALLOWED DISRUPTIONS = 0
kubectl get pods -A | grep -E "Pending|Terminating"
kubectl get events -A --field-selector type=Warning --sort-by='.lastTimestamp' | tail -10
```

### Step 2: Fix the root cause

**Most likely causes and fixes:**

**PDB blocking drain:**
```bash
# Temporarily relax overly restrictive PDBs
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'
```

**Resource constraints (pods can't reschedule):**
```bash
# Reduce surge to fit available quota
gcloud container node-pools update MAIN_WORKLOAD_POOL \
  --cluster CLUSTER_NAME --region REGION \
  --max-surge-upgrade 1 --max-unavailable-upgrade 0

# Or switch to drain-first mode (no extra quota needed)
gcloud container node-pools update MAIN_WORKLOAD_POOL \
  --cluster CLUSTER_NAME --region REGION \
  --max-surge-upgrade 0 --max-unavailable-upgrade 1
```

**Bare pods (not managed by controllers):**
```bash
# Find and delete bare pods
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
kubectl delete pod POD_NAME -n NAMESPACE
```

### Step 3: Resume the upgrade

```bash
# Resume upgrade after fixing root cause
gcloud container node-pools upgrade MAIN_WORKLOAD_POOL \
  --cluster CLUSTER_NAME --region REGION \
  --cluster-version 1.32
```

### Step 4: Monitor progress

```bash
# Watch nodes converge to target version
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Check for stuck pods
kubectl get pods -A | grep -v Running | grep -v Completed
```

## Option B: Rollback (If retry isn't viable)

**When to consider rollback:**
- Root cause can't be fixed quickly
- Target version (1.32) has critical defects discovered post-upgrade
- Business requirements demand immediate version consistency

**Important:** Cannot downgrade already-upgraded nodes in-place. Must create new pool + migrate.

### Step 1: Create replacement pool at old version

```bash
# Create new pool at previous version
gcloud container node-pools create MAIN_WORKLOAD_POOL-rollback \
  --cluster CLUSTER_NAME --region REGION \
  --cluster-version PREVIOUS_VERSION \
  --num-nodes 20 \
  --machine-type ORIGINAL_MACHINE_TYPE \
  --disk-size ORIGINAL_DISK_SIZE \
  --enable-autoscaling --min-nodes MIN --max-nodes MAX
```

### Step 2: Migrate workloads

```bash
# Cordon the mixed-version pool
kubectl cordon -l cloud.google.com/gke-nodepool=MAIN_WORKLOAD_POOL

# Drain workloads (respects PDBs)
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data
```

### Step 3: Delete old pool

```bash
gcloud container node-pools delete MAIN_WORKLOAD_POOL \
  --cluster CLUSTER_NAME --region REGION
```

## Recommended Action Plan

1. **Start with Option A (retry)** — it's simpler and gets you to a consistent state faster
2. **Fix the most likely cause first:** Check PDBs with `kubectl get pdb -A -o wide`
3. **If PDBs look fine:** Check resource constraints with `kubectl get events -A --field-selector reason=FailedScheduling`
4. **Resume the upgrade** once the blocker is resolved
5. **Save rollback for last resort** — it's a longer recovery process

## Next Steps for Remaining Pools

After the main pool converges to 1.32:

```bash
# Upgrade remaining pools (can use skip-level if they're 2+ versions behind)
gcloud container node-pools upgrade OTHER_POOL_1 \
  --cluster CLUSTER_NAME --region REGION \
  --cluster-version 1.32

gcloud container node-pools upgrade OTHER_POOL_2 \
  --cluster CLUSTER_NAME --region REGION \
  --cluster-version 1.32
```

**Skip-level advantage:** If your other pools are at 1.30 or older, you can upgrade them directly to 1.32 (within the 2-version skew limit) instead of stepping through 1.31. This reduces total upgrade time and drain cycles.

## Post-Recovery Validation

```bash
# Confirm all pools at target version
gcloud container node-pools list --cluster CLUSTER_NAME --region REGION

# Verify workload health
kubectl get deployments -A
kubectl get pods -A | grep -v Running | grep -v Completed

# Check system components
kubectl get pods -n kube-system
```

Would you like me to help you diagnose the specific failure cause, or do you need guidance on any of these recovery steps?
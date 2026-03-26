# Node Pool Upgrade Recovery Plan

## Current State Assessment
- **Control plane:** 1.32 ✓ (successfully upgraded)
- **Main workload pool:** Mixed state (8/20 nodes at 1.32, 12 nodes at previous version)
- **Other pools:** Not started
- **Cluster status:** Functional (mixed-version node pools are valid within 2 minor version skew)

## Recovery Options

### Option A: Retry Upgrade (Recommended)
This is typically the fastest path to resolution.

**Steps:**
1. **Diagnose the root cause** (see troubleshooting section below)
2. **Fix the underlying issue** 
3. **Resume the upgrade:**
```bash
gcloud container node-pools upgrade MAIN_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

**Why retry is preferred:**
- Simpler than rollback
- Nodes converge to single version (1.32)
- Leverages the work already completed (8 upgraded nodes)
- Workloads continue running normally during mixed state

### Option B: Rollback (Only if retry not viable)
Use only if the root cause can't be fixed or 1.32 has critical defects.

**Steps:**
1. Create new node pool at previous version:
```bash
gcloud container node-pools create MAIN_POOL_NAME-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version PREVIOUS_VERSION \
  --num-nodes 20 \
  --machine-type MACHINE_TYPE
```

2. Cordon the mixed-version pool and drain workloads:
```bash
kubectl cordon -l cloud.google.com/gke-nodepool=MAIN_POOL_NAME
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --grace-period=300
```

3. Delete old pool after migration completes

**Note:** This is slower and more complex than retry.

## Troubleshooting the Failure

Work through these checks to identify why the upgrade stopped:

### 1. Check for PDB blocking drain
```bash
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0
kubectl get events -A --field-selector reason=EvictionBlocked
```

**Fix if found:**
```bash
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"20%"}}'
```

### 2. Resource constraints
```bash
kubectl get pods -A | grep Pending
kubectl get events -A --field-selector reason=FailedScheduling
kubectl top nodes
```

**Fix if pods can't schedule:**
- Reduce maxSurge: `--max-surge-upgrade 1 --max-unavailable-upgrade 0`
- Scale down non-critical workloads temporarily
- Use drain-first mode: `--max-surge-upgrade 0 --max-unavailable-upgrade 1`

### 3. Bare pods (won't reschedule)
```bash
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```

**Fix:** Delete bare pods or wrap them in Deployments.

### 4. Long-running jobs blocking drain
```bash
kubectl get pods -A -o wide | grep -E "batch|job" | grep -v Completed
```

**Fix:** Wait for jobs to complete or checkpoint and restart them.

## Current Workload Impact

**Good news:** Your cluster is fully functional right now. Mixed-version node pools are normal and supported during upgrades. Workloads will run on whichever nodes they're scheduled to—no action needed to maintain service availability.

## Next Steps

1. **Run the diagnostic commands** above to identify the failure cause
2. **Apply the appropriate fix** for the issue you find
3. **Resume the upgrade** with the retry command
4. **Monitor progress:**
```bash
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
```
5. **Proceed with other node pools** once main pool completes

## Validation After Recovery

```bash
# Confirm all nodes at 1.32
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE

# Check workload health
kubectl get pods -A | grep -v Running | grep -v Completed

# Verify no stuck operations
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --limit=3
```

What error message did you see when the upgrade stopped? This will help pinpoint the exact cause and solution.
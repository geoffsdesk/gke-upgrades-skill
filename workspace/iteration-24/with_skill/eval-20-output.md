# GKE Upgrade Runbook: 1.32 → 1.33

**Cluster:** Standard cluster on Regular channel  
**Current version:** 1.32  
**Target version:** 1.33  
**Location:** us-west1-b  
**Node pools:** default-pool, workload-pool

This is a **minor version upgrade** requiring two phases: control plane first, then node pools. Total time estimate: 2-4 hours depending on cluster size.

## Phase 1: Pre-flight Checks (15 minutes)

### 1.1 Verify current cluster state

```bash
# Check current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"
```
**Expected:** Control plane and nodes both at 1.32.x

### 1.2 Confirm 1.33 is available in Regular channel

```bash
gcloud container get-server-config --zone us-west1-b \
  --format="yaml(channels)" | grep -A 10 "REGULAR"
```
**Expected:** 1.33.x listed under Regular channel

### 1.3 Check for deprecated API usage (critical — most common upgrade failure)

```bash
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
```
**Expected:** No output (good) or deprecated API calls (must fix before proceeding)

**If you see deprecated APIs:** Check the GKE console → your cluster → Insights tab for specific guidance on which APIs to update.

### 1.4 Verify cluster health

```bash
# All nodes should be Ready
kubectl get nodes

# No failing pods (ignore Completed jobs)
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded

# System components healthy
kubectl get pods -n kube-system
```
**Expected:** All nodes Ready, no CrashLoopBackOff pods, kube-system pods Running

### 1.5 Check for problematic workloads

```bash
# Look for bare pods (not managed by Deployments/StatefulSets)
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# Check PodDisruptionBudgets
kubectl get pdb -A -o wide
```
**Expected:** No bare pods, PDBs show ALLOWED DISRUPTIONS > 0

## Phase 2: Control Plane Upgrade (30-45 minutes)

### 2.1 Start control plane upgrade

```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-west1-b \
  --master \
  --cluster-version 1.33
```

**Prompts:** Type `Y` to confirm  
**Duration:** ~10-15 minutes  
**During upgrade:** You cannot modify the cluster, but workloads keep running

### 2.2 Monitor control plane upgrade

```bash
# Check upgrade progress
gcloud container operations list --cluster CLUSTER_NAME --zone us-west1-b --limit 1

# Wait for control plane to complete (repeat every few minutes)
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"
```
**Expected:** Eventually shows 1.33.x

### 2.3 Verify control plane health after upgrade

```bash
# System pods should restart automatically
kubectl get pods -n kube-system

# API should be responsive
kubectl get nodes
```

## Phase 3: Node Pool Upgrades (1-3 hours total)

### 3.1 Configure upgrade strategy for default-pool

We'll use surge upgrade with conservative settings:

```bash
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**What this does:** Upgrades one node at a time, always maintaining capacity (zero downtime)

### 3.2 Start default-pool upgrade

```bash
gcloud container node-pools upgrade default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.33
```

**Prompts:** Type `Y` to confirm  
**Duration:** ~30-90 minutes depending on pool size

### 3.3 Monitor default-pool progress

```bash
# Watch node versions change (run this in a separate terminal)
watch 'kubectl get nodes -L cloud.google.com/gke-nodepool -o wide'

# Check upgrade status
gcloud container operations list --cluster CLUSTER_NAME --zone us-west1-b --limit 1

# Look for any stuck pods
kubectl get pods -A | grep -E "Terminating|Pending|Evicted"
```

### 3.4 Wait for default-pool completion

Keep monitoring until all nodes in default-pool show version 1.33.x:

```bash
# Verify default-pool completed
gcloud container node-pools describe default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(version)"
```

### 3.5 Configure upgrade strategy for workload-pool

```bash
gcloud container node-pools update workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### 3.6 Start workload-pool upgrade

```bash
gcloud container node-pools upgrade workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.33
```

### 3.7 Monitor workload-pool progress

```bash
# Watch progress (same commands as before)
watch 'kubectl get nodes -L cloud.google.com/gke-nodepool -o wide'

# Check for issues
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded
```

## Phase 4: Post-Upgrade Validation (10 minutes)

### 4.1 Verify final versions

```bash
# All components should be at 1.33
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"
```

### 4.2 Validate cluster health

```bash
# All nodes Ready
kubectl get nodes

# No failing pods
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded

# System components healthy
kubectl get pods -n kube-system

# All deployments at desired replica count
kubectl get deployments -A
```

### 4.3 Application smoke tests

Run your application-specific health checks here. Examples:

```bash
# Test a simple service
kubectl run test-pod --image=nginx --rm -i --restart=Never -- curl -I http://SERVICE_NAME.NAMESPACE.svc.cluster.local

# Check ingress endpoints
curl -I https://your-app.example.com

# Verify database connectivity (if applicable)
kubectl exec -it POD_NAME -- your-database-health-check
```

## Troubleshooting Common Issues

### If upgrade gets stuck

**Symptom:** Node upgrade shows no progress for >30 minutes

**Diagnosis:**
```bash
# Check for PDB blocking drain
kubectl get pdb -A -o wide

# Look for resource constraints
kubectl get events -A --field-selector reason=FailedScheduling

# Check for pending pods
kubectl describe pods $(kubectl get pods -A -o wide | grep Pending | awk '{print $2 " -n " $1}')
```

**Fix:** See specific sections below

### PDB blocking drain (most common issue)

**Symptoms:** Upgrade stuck, events show "Cannot evict pod"

**Quick fix:**
```bash
# Find the problematic PDB
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# Temporarily allow more disruptions
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'
```

### Resource constraints

**Symptoms:** Pods stuck Pending, "Insufficient CPU/memory" events

**Quick fix:**
```bash
# Temporarily scale down non-critical workloads
kubectl scale deployment NON_CRITICAL_APP --replicas=0 -n NAMESPACE

# Or reduce surge to use less extra capacity
gcloud container node-pools update POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

### Bare pods found

**Symptoms:** Pre-flight check shows pods without owner references

**Fix:**
```bash
# Delete bare pods (they won't reschedule anyway)
kubectl delete pod POD_NAME -n NAMESPACE
```

## Emergency Rollback (if needed)

**Control plane rollback:** Not possible without GKE support. Contact Google Cloud Support immediately.

**Node pool rollback during upgrade:**
```bash
# Cancel in-progress upgrade
# GKE will complete current nodes then stop

# Check operation status
gcloud container operations list --cluster CLUSTER_NAME --zone us-west1-b

# Create new pool at old version if needed
gcloud container node-pools create POOL_NAME-rollback \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version 1.32 \
  --num-nodes 3 \
  --machine-type e2-medium
```

## Success Criteria

✅ Control plane at 1.33.x  
✅ Both node pools at 1.33.x  
✅ All nodes in Ready state  
✅ No CrashLoopBackOff pods  
✅ All deployments at desired replica count  
✅ Application smoke tests passing  

## Key Commands Reference

```bash
# Check versions
gcloud container clusters describe CLUSTER_NAME --zone us-west1-b --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Monitor nodes during upgrade
watch 'kubectl get nodes -L cloud.google.com/gke-nodepool -o wide'

# Check for problems
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded

# Upgrade control plane
gcloud container clusters upgrade CLUSTER_NAME --zone us-west1-b --master --cluster-version 1.33

# Upgrade node pool
gcloud container node-pools upgrade POOL_NAME --cluster CLUSTER_NAME --zone us-west1-b --cluster-version 1.33
```

---

**Important notes:**
- Replace `CLUSTER_NAME` with your actual cluster name
- This upgrade crosses a minor version boundary (1.32→1.33), so control plane must be upgraded before node pools
- The upgrade will cause brief pod restarts as nodes are drained and recreated
- Total downtime per pod: ~30-60 seconds during the drain/reschedule process
- Schedule during off-peak hours if possible
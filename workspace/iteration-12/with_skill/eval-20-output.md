# GKE Upgrade Runbook: 1.32 → 1.33

**Cluster:** Standard | **Channel:** Regular | **Zone:** us-west1-b  
**Current:** 1.32.x → **Target:** 1.33.x

This is a **minor version upgrade** requiring both control plane and node pool upgrades. Total time: ~2-3 hours depending on cluster size.

## Phase 1: Pre-flight Checks (15 minutes)

### 1.1 Verify current cluster state
```bash
# Check current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Verify all nodes are healthy
kubectl get nodes -o wide
```
**Expected:** All nodes should show `Ready` status.

### 1.2 Check if 1.33 is available in Regular channel
```bash
gcloud container get-server-config --zone us-west1-b \
  --format="yaml(channels.REGULAR.validVersions)" | grep "1\.33"
```
**Expected:** Should show 1.33.x versions available.

### 1.3 Check for deprecated API usage (critical!)
```bash
# Quick check via metrics
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# If any results show, get details
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated | head -10
```
**Expected:** No output (no deprecated APIs). If you see results, **STOP** — contact your platform team before proceeding.

### 1.4 Verify workload health baseline
```bash
# Check all pods are running
kubectl get pods -A | grep -v Running | grep -v Completed

# Check PDBs (Pod Disruption Budgets)
kubectl get pdb -A -o wide
```
**Expected:** Only Running/Completed pods, no overly restrictive PDBs (ALLOWED DISRUPTIONS should be > 0).

### 1.5 Check for bare pods (will cause upgrade failure)
```bash
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
```
**Expected:** No output. If you see pods listed, they need to be managed by Deployments/StatefulSets or deleted.

---

## Phase 2: Configure Node Pool Upgrade Settings (10 minutes)

Before upgrading, configure how each node pool handles the upgrade process.

### 2.1 Configure default-pool upgrade strategy
```bash
# Conservative surge settings for first upgrade
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### 2.2 Configure workload-pool upgrade strategy
```bash
# Same conservative settings
gcloud container node-pools update workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**What this means:** During upgrades, GKE will create 1 new node before draining the old one. This prevents capacity loss but requires temporary extra quota.

---

## Phase 3: Control Plane Upgrade (30-45 minutes)

The control plane must be upgraded before node pools. **Note:** Control plane upgrades cause a brief API server restart (~2-3 minutes of kubectl downtime).

### 3.1 Start control plane upgrade
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-west1-b \
  --master \
  --cluster-version 1.33
```

**What happens:** GKE will prompt for confirmation. Type `Y` and press Enter.

### 3.2 Monitor control plane upgrade progress
```bash
# Check upgrade status (run every 5 minutes)
gcloud container operations list \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --filter="operationType=UPGRADE_MASTER" \
  --limit=1

# When complete, verify new version
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"
```

**Expected:** Operation status progresses from `RUNNING` → `DONE`. Control plane version shows 1.33.x.

### 3.3 Verify control plane health
```bash
# Test API server connectivity
kubectl get nodes

# Check system pods
kubectl get pods -n kube-system | grep -v Running
```
**Expected:** kubectl commands work, all system pods Running.

---

## Phase 4: Node Pool Upgrades (60-90 minutes total)

Upgrade node pools one at a time. **Never upgrade multiple pools simultaneously on your first upgrade.**

### 4.1 Upgrade default-pool first
```bash
gcloud container node-pools upgrade default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b
```

**What happens:** GKE automatically uses the control plane version (1.33.x). Type `Y` to confirm.

### 4.2 Monitor default-pool upgrade
```bash
# Watch nodes being replaced (run in separate terminal)
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Check upgrade operation status
gcloud container operations list \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --filter="operationType=UPGRADE_NODES AND targetId=default-pool" \
  --limit=1
```

**What to watch for:**
- Old nodes show `SchedulingDisabled` (cordoned)
- New nodes appear with 1.33.x version
- Pods migrate from old → new nodes
- Old nodes disappear

### 4.3 Verify default-pool completion
```bash
# All nodes in default-pool should be 1.33.x
kubectl get nodes -l cloud.google.com/gke-nodepool=default-pool -o wide

# Check for any stuck pods
kubectl get pods -A | grep -v Running | grep -v Completed
```

### 4.4 Upgrade workload-pool
```bash
gcloud container node-pools upgrade workload-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b
```

### 4.5 Monitor workload-pool upgrade
```bash
# Watch progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Check operation status
gcloud container operations list \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --filter="operationType=UPGRADE_NODES AND targetId=workload-pool" \
  --limit=1
```

---

## Phase 5: Post-Upgrade Validation (15 minutes)

### 5.1 Verify all components upgraded
```bash
# Control plane version
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"

# All node pool versions
gcloud container node-pools list --cluster CLUSTER_NAME --zone us-west1-b

# All individual nodes
kubectl get nodes -o wide
```
**Expected:** Everything shows 1.33.x versions.

### 5.2 Check workload health
```bash
# No stuck pods
kubectl get pods -A | grep -v Running | grep -v Completed

# Deployments at desired replica count
kubectl get deployments -A -o wide

# StatefulSets healthy (if any)
kubectl get statefulsets -A
```

### 5.3 Test application connectivity
```bash
# Check ingress/services responding
kubectl get ingress -A
kubectl get services -A

# Run your application's health check endpoints
# curl YOUR_APP_HEALTH_CHECK_URL
```

---

## What If Something Goes Wrong?

### Upgrade stuck on "Draining nodes"
**Cause:** Pods can't be evicted, usually due to PDBs.
```bash
# Check PDBs blocking drain
kubectl get pdb -A -o wide

# Temporarily relax restrictive PDBs
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'
```

### Upgrade stuck on "Pending pods"
**Cause:** Not enough resources for surge nodes.
```bash
# Check pending pods
kubectl get pods -A | grep Pending

# Increase surge capacity
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 2
```

### API server temporarily unavailable
**Normal during control plane upgrade.** Wait 2-3 minutes and retry kubectl commands.

### Need help?
1. Check GKE operations: `gcloud container operations list --cluster CLUSTER_NAME --zone us-west1-b`
2. Look at recent events: `kubectl get events -A --sort-by='.lastTimestamp' | tail -20`
3. If stuck >2 hours, contact GKE support with cluster name and operation ID

---

## Completion Checklist

- [ ] Control plane at 1.33.x
- [ ] Both node pools at 1.33.x  
- [ ] All nodes show `Ready`
- [ ] All pods `Running` or `Completed`
- [ ] Application health checks passing
- [ ] Upgrade documented in team changelog

**Estimated total time:** 2-3 hours  
**Next upgrade:** GKE will auto-upgrade to future 1.33.x patches. The next minor (1.34) will arrive in Regular channel ~4-6 weeks after it appears in Rapid.
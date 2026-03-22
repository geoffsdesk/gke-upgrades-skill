# GKE Upgrade Runbook: 1.32 → 1.32 (Latest Patch)

**Cluster:** Standard mode, Regular channel, us-west1-b  
**Current:** 1.32.x → **Target:** 1.32.latest  
**Node pools:** default-pool, workload-pool

This is a **patch upgrade** — much safer than minor version upgrades. Patches contain security fixes and bug fixes with minimal risk of breaking changes.

---

## Phase 1: Pre-Flight Checks (15 minutes)

### 1.1 Check current cluster state

```bash
# See current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Replace CLUSTER_NAME with your actual cluster name for all commands below
```

### 1.2 Check what versions are available

```bash
# See available 1.32 patch versions in Regular channel
gcloud container get-server-config --zone us-west1-b \
  --format="yaml(channels)" | grep -A 20 "Regular"
```

Look for the latest `1.32.x-gke.xxxxx` version listed.

### 1.3 Verify cluster health

```bash
# All nodes should be Ready
kubectl get nodes -o wide

# No unhealthy system pods
kubectl get pods -n kube-system | grep -v Running | grep -v Completed

# Check for any stuck pods
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded
```

**✅ Stop here if any nodes show NotReady or system pods are failing**

### 1.4 Check for PodDisruptionBudgets

```bash
# List all PDBs - these can block upgrades
kubectl get pdb -A -o wide

# If any show ALLOWED DISRUPTIONS = 0, note the names
```

---

## Phase 2: Control Plane Upgrade (20 minutes)

The control plane upgrades first, then node pools. This is the required order.

### 2.1 Start control plane upgrade

```bash
# Replace TARGET_VERSION with the latest 1.32.x-gke.xxxxx from step 1.2
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-west1-b \
  --master \
  --cluster-version TARGET_VERSION
```

**Expected output:** Operation starts, shows operation ID

### 2.2 Monitor control plane upgrade

```bash
# Check upgrade progress (repeat every 2-3 minutes)
gcloud container operations list \
  --zone us-west1-b \
  --filter="operationType=UPGRADE_MASTER" \
  --limit=1

# When status shows DONE, verify new version
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="value(currentMasterVersion)"
```

**⏱️ Control plane upgrades typically take 10-15 minutes**

### 2.3 Verify control plane health

```bash
# System components should restart and be healthy
kubectl get pods -n kube-system

# API should be responsive
kubectl get nodes
```

---

## Phase 3: Node Pool Upgrades (30-60 minutes)

Now upgrade both node pools. We'll do them one at a time for safety.

### 3.1 Configure surge settings for default-pool

```bash
# Set conservative surge settings for first upgrade
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

This means: create 1 extra node at a time, don't make any nodes unavailable until the new one is ready.

### 3.2 Start default-pool upgrade

```bash
gcloud container node-pools upgrade default-pool \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version TARGET_VERSION
```

### 3.3 Monitor default-pool upgrade

```bash
# Watch node versions change (run this in a separate terminal)
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Check upgrade operation status
gcloud container operations list \
  --zone us-west1-b \
  --filter="operationType=UPGRADE_NODES" \
  --limit=1
```

**What you'll see:** Old nodes get cordoned (SchedulingDisabled), new nodes appear, pods migrate, old nodes disappear.

### 3.4 Verify default-pool completed

```bash
# All default-pool nodes should show new version
kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep default-pool

# No pods stuck in Terminating/Pending
kubectl get pods -A | grep -E "Terminating|Pending"
```

### 3.5 Configure surge settings for workload-pool

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
  --cluster-version TARGET_VERSION
```

### 3.7 Monitor workload-pool upgrade

```bash
# Same monitoring commands as before
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

gcloud container operations list \
  --zone us-west1-b \
  --filter="operationType=UPGRADE_NODES" \
  --limit=1
```

---

## Phase 4: Final Validation (10 minutes)

### 4.1 Verify all components at target version

```bash
# Control plane and all node pools should match
gcloud container clusters describe CLUSTER_NAME \
  --zone us-west1-b \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"
```

### 4.2 Cluster health check

```bash
# All nodes Ready
kubectl get nodes

# System pods healthy
kubectl get pods -n kube-system | grep -v Running | grep -v Completed

# Application workloads healthy
kubectl get deployments -A
kubectl get pods -A | grep -v Running | grep -v Completed | grep -v Succeeded
```

### 4.3 Verify ingress/services working

```bash
# Check load balancer services
kubectl get svc -A --field-selector spec.type=LoadBalancer

# Test a sample application endpoint if you have one
# curl http://YOUR_APP_IP/health
```

---

## Troubleshooting Common Issues

### If upgrade gets stuck:

**Problem:** PodDisruptionBudget blocking drain
```bash
# Find restrictive PDBs
kubectl get pdb -A -o wide | grep "0"

# Temporarily relax the PDB
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"minAvailable":null,"maxUnavailable":"100%"}}'
```

**Problem:** Pods won't reschedule due to resources
```bash
# Check for pending pods
kubectl get pods -A | grep Pending

# Increase surge if needed
gcloud container node-pools update POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --max-surge-upgrade 2
```

**Problem:** Bare pods blocking drain
```bash
# Find pods without owners
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# Delete them (they won't reschedule anyway)
kubectl delete pod POD_NAME -n NAMESPACE
```

---

## Rollback Plan

**Control plane:** Contact Google Cloud Support - they can help with downgrades if needed.

**Node pools:** Create new pools at old version and migrate workloads:
```bash
# Only if something goes very wrong
gcloud container node-pools create default-pool-rollback \
  --cluster CLUSTER_NAME \
  --zone us-west1-b \
  --cluster-version OLD_VERSION \
  --num-nodes 3 \
  --machine-type e2-medium
```

---

## Expected Timeline

- **Pre-flight:** 15 minutes
- **Control plane:** 15 minutes  
- **default-pool:** 20-30 minutes (depends on node count)
- **workload-pool:** 20-30 minutes (depends on node count)
- **Validation:** 10 minutes

**Total:** 80-100 minutes for the full upgrade

---

## Key Notes for First-Time Upgraders

1. **This is a patch upgrade** - very safe, just security/bug fixes
2. **One component at a time** - control plane first, then each node pool
3. **Pods will restart** - normal and expected during node upgrades
4. **Surge creates extra nodes** - temporary, they're cleaned up automatically
5. **Monitor each phase** - don't start the next until current is complete
6. **Patch PDBs if stuck** - most common blocker, easy to fix

**Questions or issues?** Check the troubleshooting section or contact your team lead.
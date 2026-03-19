# GKE Cluster Upgrade Plan: 1.28 → 1.30
**Cluster:** production-us-central1-a | **Mode:** Standard | **Release Channel:** Regular
**Current Version:** 1.28.x | **Target Version:** 1.30.x | **Timeline:** Before end of Q2

---

## Executive Summary

Your Standard GKE cluster requires a sequential minor-version upgrade path due to the 2-minor-version skew limit between control plane and nodes. This plan guides you through:

1. **Sequential upgrade path:** 1.28 → 1.29 → 1.30
2. **Control plane first**, then node pools in sequence
3. **Three node pools with tailored upgrade strategies** optimized for general-purpose, stateful (Postgres), and GPU workloads
4. **Pre/post-upgrade checklists** with validation commands
5. **Rollback procedures** and troubleshooting guidance

**Expected timeline:**
- Control plane: ~15 minutes per version
- Node pool upgrades: 30–90 minutes total (depends on workload and surge settings)
- Full completion (1.28→1.30): 3–4 hours

---

## Version Compatibility Assessment

### Target Version Availability
The Regular release channel will have 1.29 and 1.30 available. Confirm with:
```bash
gcloud container get-server-config --zone us-central1-a --format="yaml(channels)"
```

### Version Skew Validation
- **Nodes must not be more than 2 minor versions behind the control plane**
- Current state: All at 1.28
- After control plane upgrade to 1.29: Nodes can remain at 1.28 or upgrade to 1.29
- After control plane upgrade to 1.30: Nodes must be at 1.28–1.30

### Deprecated APIs
Before upgrading, check for deprecated API usage:
```bash
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
```
Review the [GKE 1.29 and 1.30 release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes) for breaking changes. Most migrations (e.g., policy/v1beta1 → policy/v1 for PodDisruptionBudgets) are backward-compatible in Regular channel.

---

## Upgrade Path

### Stage 1: 1.28 → 1.29
### Stage 2: 1.29 → 1.30

Sequential upgrades reduce the risk of cascading incompatibilities between operators, webhooks, and workloads. Although GKE technically supports skipping versions, we recommend going 1.28 → 1.29 → 1.30.

---

## Node Pool Upgrade Strategy

You have three pools with distinct workload characteristics. Each will use **surge upgrade** (the default strategy) with per-pool settings:

### Pool 1: General-Purpose Pool
**Workload:** Stateless services, web apps
**Upgrade Strategy:** Surge with **maxSurge=2, maxUnavailable=0**

**Rationale:**
- Stateless workloads can reschedule freely
- Higher surge allows faster completion without disrupting availability
- `maxUnavailable=0` ensures continuous service

**Commands (1.29 upgrade example):**
```bash
gcloud container node-pools update general-purpose \
  --cluster production-us-central1-a \
  --zone us-central1-a \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade general-purpose \
  --cluster production-us-central1-a \
  --zone us-central1-a \
  --cluster-version 1.29.x
```

**Estimated time:** 20–30 minutes

---

### Pool 2: High-Memory Pool (Postgres Operator)
**Workload:** Stateful database operator
**Upgrade Strategy:** Surge with **maxSurge=1, maxUnavailable=0**

**Rationale:**
- Postgres workloads require careful coordination (PDB, PV reclaim policies, backups)
- `maxSurge=1` minimizes temporary overcapacity while allowing one replacement at a time
- `maxUnavailable=0` ensures the primary replica is always available
- PDBs will protect pods during drain

**Pre-upgrade Requirements for Postgres:**

1. **Verify PDB configuration:**
   ```bash
   kubectl get pdb -n <postgres-namespace> -o wide
   # Ensure minAvailable or maxUnavailable allows at least one pod disruption
   # Example: minAvailable=N-1 (one pod can be disrupted), or maxUnavailable=1
   ```

2. **Confirm PV reclaim policies:**
   ```bash
   kubectl get pv -o json | \
     jq '.items[] | select(.spec.storageClassName=="<your-storage-class>") | {name:.metadata.name, reclaimPolicy:.spec.persistentVolumeReclaimPolicy}'
   # Should be "Retain" or "Recycle", NOT "Delete"
   ```

3. **Verify Postgres operator compatibility:**
   - Check the operator's release notes for 1.29 and 1.30 support
   - Most operators support at least ±1 minor version skew
   - No upgrade of the operator itself is needed unless explicitly required

4. **Backup databases:**
   ```bash
   # Trigger a backup via your operator or manual method
   # Example: kubectl patch -n <postgres-namespace> <postgres-cluster> --type merge -p '{"spec":{"backup":{"enabled":true}}}'
   ```

**Commands (1.29 upgrade example):**
```bash
gcloud container node-pools update high-memory \
  --cluster production-us-central1-a \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade high-memory \
  --cluster production-us-central1-a \
  --zone us-central1-a \
  --cluster-version 1.29.x
```

**Monitoring during upgrade:**
```bash
# Watch pod drains and watch for PDB violations
watch 'kubectl get pods -n <postgres-namespace> -o wide'

# Monitor node pool progression
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep high-memory'
```

**Estimated time:** 30–45 minutes

---

### Pool 3: GPU Pool (ML Inference)
**Workload:** GPU-backed inference services
**Upgrade Strategy:** Surge with **maxSurge=1, maxUnavailable=0**

**Rationale:**
- GPUs are expensive; even temporary overprovision adds cost
- `maxSurge=1` limits extra GPU capacity to one node at a time
- `maxUnavailable=0` keeps inference available during upgrade
- GPU workloads are sensitive to kernel/driver version compatibility

**Pre-upgrade Requirements for GPU:**

1. **Confirm NVIDIA driver compatibility:**
   ```bash
   # Current node image and NVIDIA driver version
   kubectl get nodes -L cloud.google.com/gke-nodepool | grep gpu
   gcloud container node-pools describe gpu \
     --cluster production-us-central1-a \
     --zone us-central1-a \
     --format="value(config.imageType)"

   # Check GKE release notes for GPU driver updates in 1.29 and 1.30
   # Most CUDA 11.x / 12.x compatible drivers support multiple K8s versions
   ```

2. **Verify GPU resource requests:**
   ```bash
   kubectl get pods -A -o json | \
     jq '.items[] | select(.spec.nodeSelector."cloud.google.com/gke-accelerator") | {ns:.metadata.namespace, name:.metadata.name, gpus:.spec.containers[].resources.requests."nvidia.com/gpu"}'
   # All GPU workloads must have explicit GPU requests
   ```

3. **Stagger inference workloads (if needed):**
   - If running real-time inference, consider routing traffic away from GPU pool briefly or accepting reduced capacity during upgrade
   - One GPU node down at a time with `maxSurge=1` should not cause outages

**Commands (1.29 upgrade example):**
```bash
gcloud container node-pools update gpu \
  --cluster production-us-central1-a \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade gpu \
  --cluster production-us-central1-a \
  --zone us-central1-a \
  --cluster-version 1.29.x
```

**Monitoring during upgrade:**
```bash
# Watch GPU workload rescheduling
watch 'kubectl get pods -A -l gpu=true -o wide'

# Confirm no pods stuck in Pending due to GPU resource constraints
kubectl get pods -A --field-selector=status.phase=Pending
```

**Estimated time:** 30–45 minutes

---

## Node Pool Upgrade Sequence (Per Version Cycle)

For each minor version upgrade (1.28→1.29, then 1.29→1.30), follow this sequence:

```
1. Upgrade control plane (master) to next version
2. Wait ~5 minutes for control plane stabilization
3. Upgrade general-purpose pool (fastest, stateless)
4. Upgrade high-memory pool (Postgres, stateful, needs PDB protection)
5. Upgrade GPU pool (GPU workload coordination)
```

**Why this order:**
- General-purpose has no state to protect; upgrade first to unblock developers
- High-memory (Postgres) needs careful coordination but less resource-constrained than GPU
- GPU last to minimize workload disruption and cost

---

## Pre-Upgrade Checklist

```
[ ] Cluster: production-us-central1-a | Mode: Standard | Channel: Regular
[ ] Current version: 1.28.x | Target version: 1.30.x (via 1.29)

Compatibility
[ ] 1.29 available in Regular channel (gcloud container get-server-config)
[ ] 1.30 available in Regular channel
[ ] No deprecated API usage detected (kubectl get --raw /metrics | grep deprecated)
[ ] GKE 1.29 and 1.30 release notes reviewed for breaking changes
[ ] Postgres operator version compatible with 1.29 and 1.30
[ ] Admission webhooks tested with 1.29 (manually if needed)

Workload Readiness — General-Purpose Pool
[ ] No bare pods in general-purpose pool (all managed by Deployment/StatefulSet/DaemonSet)
[ ] terminationGracePeriodSeconds >= 30 seconds on stateless workloads
[ ] Resource requests/limits set on all containers

Workload Readiness — Postgres Pool
[ ] PDB exists and allows at least 1 pod disruption: kubectl get pdb -n <postgres-ns>
[ ] PV reclaim policies set to Retain or Recycle (NOT Delete)
[ ] Postgres operator supports 1.29 and 1.30 (check operator release notes)
[ ] Recent backup taken (manual or operator-managed)
[ ] terminationGracePeriodSeconds >= 60 seconds on Postgres pods

Workload Readiness — GPU Pool
[ ] NVIDIA GPU driver version confirmed compatible with 1.29 and 1.30
[ ] All GPU pods have explicit nvidia.com/gpu resource requests
[ ] terminationGracePeriodSeconds >= 30 seconds on GPU workloads

Infrastructure (Standard)
[ ] Node pool surge settings confirmed for each pool (maxSurge=2/1/1, maxUnavailable=0 for all)
[ ] Sufficient GCP quota for surge nodes (total nodes + surge capacity)
[ ] Maintenance window set to off-peak hours (if not already)

Ops Readiness
[ ] Monitoring (Cloud Monitoring / Prometheus) active and alerting on error rates / latency
[ ] Baseline metrics captured (error rate, latency p50/p95/p99, throughput)
[ ] Upgrade window communicated to stakeholders
[ ] On-call team available during upgrade window
[ ] Rollback procedure documented (below)
```

---

## Upgrade Execution

### Step 1: Pre-Flight Checks (Before Any Upgrade)

```bash
# Verify current state
gcloud container clusters describe production-us-central1-a \
  --zone us-central1-a \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Check cluster health
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Succeeded

# Verify workload PDBs
kubectl get pdb -A -o wide

# Check for bare pods
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
# If any bare pods exist, delete or wrap in Deployment before proceeding

# Deprecated APIs
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
```

### Step 2: 1.28 → 1.29 Upgrade

#### 2a. Upgrade Control Plane (Master) to 1.29

```bash
gcloud container clusters upgrade production-us-central1-a \
  --zone us-central1-a \
  --master \
  --cluster-version 1.29.x
```

**Monitor control plane upgrade (typically 10–15 minutes):**
```bash
# Check status
gcloud container clusters describe production-us-central1-a \
  --zone us-central1-a \
  --format="value(currentMasterVersion)"

# Wait for output to show 1.29.x, then verify system pods
kubectl get pods -n kube-system
# All kube-apiserver, kube-scheduler, kube-controller-manager pods should be Running
```

#### 2b. Configure and Upgrade General-Purpose Pool

```bash
# Set surge settings
gcloud container node-pools update general-purpose \
  --cluster production-us-central1-a \
  --zone us-central1-a \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# Upgrade
gcloud container node-pools upgrade general-purpose \
  --cluster production-us-central1-a \
  --zone us-central1-a \
  --cluster-version 1.29.x

# Monitor progress (watch for nodes transitioning to 1.29.x)
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Verify complete
gcloud container node-pools list \
  --cluster production-us-central1-a \
  --zone us-central1-a \
  --format="table(name, version)"
```

#### 2c. Configure and Upgrade High-Memory Pool (Postgres)

```bash
# Set conservative surge settings for stateful workload
gcloud container node-pools update high-memory \
  --cluster production-us-central1-a \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade
gcloud container node-pools upgrade high-memory \
  --cluster production-us-central1-a \
  --zone us-central1-a \
  --cluster-version 1.29.x

# Monitor: watch PDB compliance and Postgres pod stability
watch 'kubectl get pdb -A && kubectl get pods -n <postgres-namespace>'

# Verify no PDB violations
kubectl describe pdb -n <postgres-namespace>

# Verify complete
gcloud container node-pools list \
  --cluster production-us-central1-a \
  --zone us-central1-a \
  --format="table(name, version)"
```

#### 2d. Configure and Upgrade GPU Pool

```bash
# Conservative surge for GPU cost minimization
gcloud container node-pools update gpu \
  --cluster production-us-central1-a \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade
gcloud container node-pools upgrade gpu \
  --cluster production-us-central1-a \
  --zone us-central1-a \
  --cluster-version 1.29.x

# Monitor GPU workload rescheduling
watch 'kubectl get pods -A -L cloud.google.com/gke-accelerator | grep -v "^kube"'

# Verify complete
gcloud container node-pools list \
  --cluster production-us-central1-a \
  --zone us-central1-a \
  --format="table(name, version)"
```

### Step 3: 1.29 → 1.30 Upgrade

Repeat **Step 2 (2a–2d)** exactly, replacing `--cluster-version 1.29.x` with `--cluster-version 1.30.x`.

---

## Post-Upgrade Checklist

```
Cluster Health
[ ] Control plane at 1.30.x: gcloud container clusters describe production-us-central1-a --zone us-central1-a --format="value(currentMasterVersion)"
[ ] All node pools at 1.30.x: gcloud container node-pools list --cluster production-us-central1-a --zone us-central1-a
[ ] All nodes Ready: kubectl get nodes
[ ] System pods healthy: kubectl get pods -n kube-system
[ ] No stuck PDBs: kubectl get pdb --all-namespaces

Workload Health
[ ] All deployments at desired replicas: kubectl get deployments -A
[ ] No CrashLoopBackOff or Pending pods: kubectl get pods -A --field-selector=status.phase=Pending,status.phase=Failed
[ ] All StatefulSets fully ready: kubectl get statefulsets -A
[ ] Postgres cluster healthy: kubectl get pods -n <postgres-namespace> && kubectl exec <postgres-pod> -- psql -c "SELECT 1;"
[ ] GPU workloads running: kubectl get pods -A -L cloud.google.com/gke-accelerator | grep -v "none"
[ ] Ingress/load balancers responding

Observability
[ ] Cloud Monitoring metrics flowing (no gaps)
[ ] Logs flowing to Cloud Logging or aggregator
[ ] Error rates within baseline (compare with pre-upgrade snapshot)
[ ] Latency (p50/p95/p99) within baseline

Cleanup & Documentation
[ ] Surge quota released (automatic; verify node count returned to baseline)
[ ] Upgrade entry added to team changelog
[ ] Lessons learned captured (any PDB blocks? resource constraints? unexpected latency?)
```

### Validation Commands

```bash
# Quick health check after all upgrades complete
echo "=== Cluster Version ===" && \
gcloud container clusters describe production-us-central1-a \
  --zone us-central1-a \
  --format="value(currentMasterVersion)"

echo "=== Node Pools ===" && \
gcloud container node-pools list \
  --cluster production-us-central1-a \
  --zone us-central1-a \
  --format="table(name, version)"

echo "=== Nodes ===" && \
kubectl get nodes -o wide

echo "=== System Pods ===" && \
kubectl get pods -n kube-system

echo "=== Workload Status ===" && \
kubectl get deployments -A && \
kubectl get statefulsets -A

echo "=== PDBs ===" && \
kubectl get pdb -A
```

---

## Rollback Procedure

### Control Plane Rollback (Rare)
Control plane downgrades are **not recommended** without GKE support involvement. If a control plane upgrade fails catastrophically, contact GKE support immediately with cluster name, zone, and operation ID.

### Node Pool Rollback (Blue-Green Alternative)

If a node pool upgrade causes workload instability, you have two options:

**Option 1: Create a rollback pool at the old version** (requires data migration)
```bash
# Create new pool at 1.28
gcloud container node-pools create general-purpose-v1-28 \
  --cluster production-us-central1-a \
  --zone us-central1-a \
  --cluster-version 1.28.x \
  --num-nodes 3 \
  --machine-type n1-standard-4

# Cordon upgraded pool to stop scheduling
kubectl cordon -l cloud.google.com/gke-nodepool=general-purpose

# Migrate workloads manually or via kubectl drain + rebalance
kubectl drain -l cloud.google.com/gke-nodepool=general-purpose \
  --ignore-daemonsets --delete-emptydir-data

# Delete upgraded pool once empty
gcloud container node-pools delete general-purpose \
  --cluster production-us-central1-a \
  --zone us-central1-a
```

**Option 2: Wait for stability** (recommended)
Most issues resolve within 5–10 minutes as workloads stabilize. Check logs before declaring failure:
```bash
kubectl logs -n <namespace> <pod> --tail 100
kubectl describe pod -n <namespace> <pod>
```

### If Upgrade is Stuck

Check the troubleshooting section below.

---

## Troubleshooting Common Issues

### Issue 1: Node Upgrade Stuck (Nodes Not Transitioning)

**Diagnose:**
```bash
# Check node status
kubectl get nodes -L cloud.google.com/gke-nodepool

# Look for nodes stuck in "SchedulingDisabled" or "NotReady"
kubectl describe nodes <node-name> | grep Conditions -A 5

# Check if pods are being evicted
kubectl get events -A --field-selector involvedObject.kind=Pod | grep -i evict
```

**Most Common Cause: PDB Blocking Drain**

```bash
kubectl get pdb -A -o wide
# If any PDB shows ALLOWED DISRUPTIONS = 0, that pool is blocked
kubectl describe pdb <pdb-name> -n <namespace>
```

**Fix: Temporarily Relax PDB**
```bash
# Save original
kubectl get pdb <pdb-name> -n <namespace> -o yaml > pdb-backup.yaml

# Temporarily allow 100% disruption
kubectl patch pdb <pdb-name> -n <namespace> \
  -p '{"spec":{"minAvailable":null,"maxUnavailable":"100%"}}'

# Node upgrade should resume
# Wait for completion, then restore
kubectl apply -f pdb-backup.yaml
```

### Issue 2: Pending Pods During Upgrade

**Diagnose:**
```bash
kubectl get pods -A --field-selector=status.phase=Pending
kubectl get events -A --field-selector reason=FailedScheduling
kubectl top nodes
```

**Cause: Insufficient surge capacity or resource constraints**

**Fix: Increase Surge**
```bash
gcloud container node-pools update <pool-name> \
  --cluster production-us-central1-a \
  --zone us-central1-a \
  --max-surge-upgrade 3
```

Or temporarily scale down non-critical workloads.

### Issue 3: Postgres Operator or StatefulSet Not Recovering

**Diagnose:**
```bash
kubectl get statefulsets -n <postgres-namespace>
kubectl get pods -n <postgres-namespace>
kubectl logs -n <postgres-namespace> <pod-name> --tail 50
```

**Common Cause: PV attachment delayed or volume lock**

**Check PV status:**
```bash
kubectl get pvc -n <postgres-namespace>
kubectl describe pvc <pvc-name> -n <postgres-namespace>
```

**Fix: Force new pod rollout if stuck**
```bash
kubectl rollout restart statefulset <statefulset-name> -n <postgres-namespace>
# Monitor
kubectl get pods -n <postgres-namespace> -w
```

### Issue 4: GPU Workload Stuck in Pending

**Diagnose:**
```bash
kubectl get pods -A -L cloud.google.com/gke-accelerator | grep Pending
kubectl describe pod <pod-name> -n <namespace> | grep -A 5 "Events:"
```

**Common Cause: GPU resource request not set or insufficient available GPUs**

**Fix: Verify GPU requests**
```bash
kubectl get pods <pod-name> -n <namespace> -o json | \
  jq '.spec.containers[].resources.requests."nvidia.com/gpu"'
# Must be a number > 0

# Check available GPUs
kubectl describe nodes -l cloud.google.com/gke-accelerator | grep -A 5 "nvidia.com/gpu"
```

### Issue 5: Webhooks Rejecting Pod Creation

**Diagnose:**
```bash
kubectl get validatingwebhookconfigurations
kubectl get mutatingwebhookconfigurations
kubectl describe validatingwebhookconfigurations <webhook-name>
```

**Fix: Temporarily disable problematic webhook**
```bash
# Save backup
kubectl get validatingwebhookconfigurations <webhook-name> -o yaml > webhook-backup.yaml

# Delete
kubectl delete validatingwebhookconfigurations <webhook-name>

# Re-create after upgrade succeeds
kubectl apply -f webhook-backup.yaml
```

---

## Additional Guidance

### Maintenance Window (Optional)
If you want to set off-peak upgrade windows for auto-upgrades:
```bash
gcloud container clusters update production-us-central1-a \
  --zone us-central1-a \
  --maintenance-window-start 2026-03-21T06:00:00Z \
  --maintenance-window-end 2026-03-21T08:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

### Monitoring During Upgrade
Enable or verify these are active:
- **Cloud Monitoring:** Set up alerts on node upgrade progress, pod eviction rates
- **Cloud Logging:** Filter logs by `resource.type="gke_cluster"` and `protoPayload.methodName=~"compute.nodes.*"`
- **kubectl watch:** Keep terminals running `watch kubectl get nodes -o wide`

### Release Channel Strategy
Regular channel is ideal for production clusters that want stability without the lag of Stable or the risk of Rapid. Consider this strategy for multi-cluster environments:
- **Dev:** Rapid channel (early access to features, shorter support window)
- **Staging:** Regular channel (validates production path)
- **Production:** Regular or Stable (stability-first)

---

## Summary

| Stage | Duration | Action |
|-------|----------|--------|
| Pre-flight | 15 min | Verify cluster state, run diagnostic commands |
| 1.28 → 1.29: Control plane | 15 min | `gcloud container clusters upgrade --master --cluster-version 1.29.x` |
| 1.28 → 1.29: General-purpose | 25 min | maxSurge=2, upgrade |
| 1.28 → 1.29: High-memory | 35 min | maxSurge=1, monitor PDB, upgrade |
| 1.28 → 1.29: GPU | 35 min | maxSurge=1, monitor GPU workload, upgrade |
| 1.29 → 1.30: All pools | 105 min | Repeat same sequence for 1.30 |
| Post-upgrade validation | 15 min | Run health checks and confirm workloads |
| **Total (both upgrades)** | **~4 hours** | Full 1.28→1.30 completion |

You are now ready to execute the upgrade. Start with pre-flight checks, then proceed through each stage in sequence.

# GKE Cluster Upgrade Plan: 1.28 → 1.30

**Cluster:** Standard GKE cluster in us-central1-a
**Current Version:** 1.28
**Target Version:** 1.30
**Release Channel:** Regular
**Deadline:** End of Q2 2026
**Status:** Ready to execute

---

## Executive Summary

This plan upgrades your Standard GKE cluster from Kubernetes 1.28 to 1.30 on the Regular release channel. The upgrade involves:
- **Control plane upgrade** to 1.28 → 1.29 → 1.30 (sequential minor versions)
- **Three node pool upgrades** with workload-specific surge settings
- **Pre/post-upgrade validation** to ensure stability across stateless, stateful (Postgres), and GPU workloads

**Timeline:** 2-3 business days total (control plane: 1 day, node pools: 1-2 days depending on pool size)

---

## Version Compatibility & Upgrade Path

### Availability in Regular Channel
Version 1.30 is available in the Regular release channel. Sequential upgrades (1.28→1.29→1.30) are safer than direct skipping, as they catch compatibility issues between each minor version.

### Node Version Skew
GKE enforces a 2 minor version skew rule: nodes must be within 2 minor versions of the control plane.
- **Current state:** All nodes at 1.28
- **After control plane upgrade to 1.29:** Nodes can stay at 1.28 (within skew)
- **After control plane upgrade to 1.30:** Nodes must be within 1.28–1.30 range
- **Final state:** All nodes at 1.30

### Breaking Changes & Deprecations
Review the [GKE 1.29 and 1.30 release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes) for:
- Deprecated API removals (e.g., extensions/v1beta1, policy/v1beta1)
- Operator compatibility (especially the Postgres operator — test with target version beforehand)
- GPU driver compatibility with the new node image
- Admission webhook compatibility

**Action:** Before upgrading, run this command to check for deprecated API usage:
```bash
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
```

If results appear, migrate those workloads before upgrading.

---

## Upgrade Path: Sequential Minor Versions

```
1.28 (current)
  ↓
1.29 (intermediate step)
  ↓
1.30 (target)
```

**Why sequential?** Direct jumps (1.28→1.30) are technically supported but sequential upgrades catch incompatibilities early and reduce failure risk.

---

## Node Pool Upgrade Strategy

Your cluster has three node pools with distinct workload profiles. Each gets a tailored surge strategy balancing speed, cost, and stability.

### Pool 1: General-Purpose
**Purpose:** Stateless workloads (web apps, services)
**Upgrade Strategy:** Surge upgrade with aggressive settings
**Configuration:**
- `maxSurge=2`
- `maxUnavailable=0`

**Rationale:** Stateless workloads tolerate temporary overcapacity. Higher surge reduces upgrade time.

### Pool 2: High-Memory (Postgres Operator)
**Purpose:** Stateful database workload
**Upgrade Strategy:** Surge upgrade with conservative settings
**Configuration:**
- `maxSurge=1`
- `maxUnavailable=0`

**Rationale:** Database pods are managed by the Postgres operator with PDBs. Surge=1 minimizes temporary overcapacity while PDBs ensure no disruption. Operator should handle graceful shutdown.

### Pool 3: GPU (ML Inference)
**Purpose:** GPU workloads for inference
**Upgrade Strategy:** Surge upgrade with conservative settings
**Configuration:**
- `maxSurge=1`
- `maxUnavailable=0`

**Rationale:** GPUs are expensive; temporary overcapacity is costly. Surge=1 adds minimal extra GPU nodes. Confirm GPU driver compatibility with target node image before upgrading.

---

## Pre-Upgrade Checklist

Complete these steps **before initiating the upgrade:**

```
PRE-UPGRADE CHECKLIST
Cluster: us-central1-a Standard GKE | Mode: Standard | Channel: Regular
Current version: 1.28 | Target version: 1.30

COMPATIBILITY
- [ ] Target version 1.30 available in Regular channel (verify via: gcloud container get-server-config --zone us-central1-a --format="yaml(channels)")
- [ ] No deprecated API usage (run: kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated)
- [ ] GKE 1.29 and 1.30 release notes reviewed for breaking changes
- [ ] Node version skew confirmed within 2 minor versions
- [ ] Third-party operators (Postgres operator) compatible with 1.30
- [ ] Admission webhooks (if any) tested against 1.30

WORKLOAD READINESS
- [ ] PDBs configured for Postgres operator workloads (check: kubectl get pdb -A)
- [ ] No bare pods in cluster (all pods managed by Deployments, StatefulSets, DaemonSets, etc.)
- [ ] terminationGracePeriodSeconds adequate for Postgres graceful shutdown (>=30s recommended)
- [ ] Postgres PVs backed up and reclaim policies set to Retain
- [ ] GPU driver compatibility confirmed with 1.30 node image
- [ ] Resource requests set on all containers (especially critical for GPU pool)

INFRASTRUCTURE (STANDARD MODE)
- [ ] Node pool surge settings confirmed: general-purpose (maxSurge=2), high-memory (maxSurge=1), GPU (maxSurge=1)
- [ ] Sufficient compute quota for surge nodes (check quota in GCP console)
- [ ] Maintenance window configured for off-peak hours (e.g., Saturday midnight)
- [ ] Maintenance exclusions set for any business freeze periods

OPS READINESS
- [ ] Monitoring and alerting active (Cloud Monitoring / Prometheus)
- [ ] Baseline metrics captured: error rates, latency (p50/p95/p99), throughput
- [ ] Upgrade window (2-3 business days) communicated to stakeholders
- [ ] Rollback plan documented and tested (node pool downgrades require new pool + workload migration)
- [ ] On-call team aware and available during upgrade window
- [ ] Database backups completed and verified (critical for Postgres pool)
```

---

## Upgrade Execution Sequence

### Phase 1: Control Plane Upgrade (1.28 → 1.29)

**Duration:** ~15 minutes (control plane downtime ~5 min, kube-system pod restarts)

```bash
# 1. Verify current state
gcloud container clusters describe my-cluster \
  --zone us-central1-a \
  --format="table(name, currentMasterVersion, nodePools[].version)"

# 2. Upgrade control plane to 1.29
gcloud container clusters upgrade my-cluster \
  --zone us-central1-a \
  --master \
  --cluster-version 1.29

# 3. Wait ~15 minutes and verify
gcloud container clusters describe my-cluster \
  --zone us-central1-a \
  --format="value(currentMasterVersion)"

# 4. Confirm kube-system pods are healthy
kubectl get pods -n kube-system -o wide
```

**Expected outcome:** Control plane at 1.29, nodes still at 1.28 (within skew).

---

### Phase 2: Node Pool Upgrades (1.28 → 1.29)

After control plane is at 1.29, upgrade each node pool. Start with the general-purpose pool, then high-memory, then GPU. This order minimizes stateful workload disruption.

#### Upgrade General-Purpose Pool

```bash
# 1. Configure surge settings
gcloud container node-pools update general-purpose \
  --cluster my-cluster \
  --zone us-central1-a \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# 2. Upgrade to 1.29
gcloud container node-pools upgrade general-purpose \
  --cluster my-cluster \
  --zone us-central1-a \
  --cluster-version 1.29

# 3. Monitor progress (run in separate terminal)
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# 4. Wait for all nodes in pool to reach 1.29 (10-20 min for typical pool)
gcloud container node-pools list --cluster my-cluster --zone us-central1-a

# 5. Verify workload health
kubectl get deployments -A
kubectl get pods -A | grep -v Running | grep -v Completed
```

**Expected outcome:** General-purpose pool at 1.29, workloads running normally.

#### Upgrade High-Memory Pool (Postgres)

```bash
# 1. Configure conservative surge settings
gcloud container node-pools update high-memory \
  --cluster my-cluster \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# 2. Verify Postgres operator and PDBs are healthy
kubectl get pdb -A -o wide
kubectl get pods -n [postgres-namespace] -o wide

# 3. Upgrade to 1.29
gcloud container node-pools upgrade high-memory \
  --cluster my-cluster \
  --zone us-central1-a \
  --cluster-version 1.29

# 4. Monitor progress carefully (PDBs will drain gracefully)
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep high-memory'
watch 'kubectl get pods -n [postgres-namespace] -o wide'

# 5. Wait for upgrade to complete (15-30 min depending on pod count)
gcloud container node-pools list --cluster my-cluster --zone us-central1-a

# 6. Verify Postgres is healthy and accepting connections
# (adjust command for your Postgres monitoring/client setup)
kubectl exec -it [postgres-pod] -n [postgres-namespace] -- psql -c "SELECT 1;"
```

**Expected outcome:** High-memory pool at 1.29, Postgres operator pods running, no disruptions.

#### Upgrade GPU Pool

```bash
# 1. Configure conservative surge settings
gcloud container node-pools update gpu-pool \
  --cluster my-cluster \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# 2. Verify GPU driver compatibility with 1.29 node image
# Check node image release notes for GPU driver versions
gcloud container get-server-config --zone us-central1-a \
  --format="yaml(defaultClusterVersion)"

# 3. Upgrade to 1.29
gcloud container node-pools upgrade gpu-pool \
  --cluster my-cluster \
  --zone us-central1-a \
  --cluster-version 1.29

# 4. Monitor GPU node upgrades
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep gpu'

# 5. Verify GPU availability and workload health (20-40 min)
kubectl get nodes -o wide | grep gpu
nvidia-smi  # If accessible on nodes
kubectl get pods -n [ml-namespace] -o wide

# 6. Confirm no GPU pod scheduling issues
kubectl get events -n [ml-namespace] --field-selector reason=FailedScheduling
```

**Expected outcome:** GPU pool at 1.29, GPU workloads running, no scheduling issues.

---

### Phase 3: Control Plane Upgrade (1.29 → 1.30)

Repeat Phase 1 with target version 1.30.

```bash
# 1. Verify all nodes are at 1.29
gcloud container node-pools list --cluster my-cluster --zone us-central1-a

# 2. Upgrade control plane to 1.30
gcloud container clusters upgrade my-cluster \
  --zone us-central1-a \
  --master \
  --cluster-version 1.30

# 3. Wait ~15 minutes and verify
gcloud container clusters describe my-cluster \
  --zone us-central1-a \
  --format="value(currentMasterVersion)"

# 4. Confirm kube-system pods are healthy
kubectl get pods -n kube-system -o wide
```

**Expected outcome:** Control plane at 1.30, nodes still at 1.29 (within skew).

---

### Phase 4: Node Pool Upgrades (1.29 → 1.30)

Repeat Phase 2 with target version 1.30, upgrading pools in the same order.

#### Upgrade General-Purpose Pool

```bash
gcloud container node-pools upgrade general-purpose \
  --cluster my-cluster \
  --zone us-central1-a \
  --cluster-version 1.30

watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep general-purpose'
```

#### Upgrade High-Memory Pool

```bash
gcloud container node-pools upgrade high-memory \
  --cluster my-cluster \
  --zone us-central1-a \
  --cluster-version 1.30

watch 'kubectl get pods -n [postgres-namespace] -o wide'
```

#### Upgrade GPU Pool

```bash
gcloud container node-pools upgrade gpu-pool \
  --cluster my-cluster \
  --zone us-central1-a \
  --cluster-version 1.30

watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep gpu'
```

---

## Post-Upgrade Checklist

Run these validations immediately after all upgrades complete:

```
POST-UPGRADE CHECKLIST

CLUSTER HEALTH
- [ ] Control plane at 1.30: gcloud container clusters describe my-cluster --zone us-central1-a --format="value(currentMasterVersion)"
- [ ] All node pools at 1.30: gcloud container node-pools list --cluster my-cluster --zone us-central1-a
- [ ] All nodes Ready: kubectl get nodes
- [ ] System pods healthy: kubectl get pods -n kube-system
- [ ] No stuck PDBs: kubectl get pdb --all-namespaces

WORKLOAD HEALTH
- [ ] All deployments at desired replica count: kubectl get deployments -A
- [ ] No CrashLoopBackOff or Pending pods: kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded
- [ ] StatefulSets fully ready: kubectl get statefulsets -A
- [ ] Postgres operator healthy: kubectl get pods -n [postgres-namespace] -o wide
- [ ] Postgres accepting connections: kubectl exec -it [postgres-pod] -n [postgres-namespace] -- psql -c "SELECT 1;"
- [ ] GPU workloads running: kubectl get pods -n [ml-namespace] -o wide
- [ ] Ingress/load balancers responding
- [ ] Application health checks and smoke tests passing

OBSERVABILITY
- [ ] Metrics pipeline active, no collection gaps (check Cloud Monitoring)
- [ ] Logs flowing to aggregation
- [ ] Error rates within pre-upgrade baseline
- [ ] Latency (p50/p95/p99) within pre-upgrade baseline
- [ ] No unexpected alerts or escalations

CLEANUP
- [ ] Surge quota released (automatic once node pool upgrades finish)
- [ ] Upgrade documented in changelog
- [ ] Lessons learned captured
```

---

## Rollback & Contingency Plan

**Control plane rollback** is not recommended without GKE support. If the control plane upgrade fails, contact Google Cloud support immediately.

**Node pool rollback** (if individual pools have issues):

1. Create a new node pool at the previous version
2. Cordon the upgraded pool to prevent new pod scheduling
3. Manually migrate workloads using `kubectl drain`
4. Delete the upgraded pool

Example:
```bash
# Create rollback pool at 1.29
gcloud container node-pools create general-purpose-rollback \
  --cluster my-cluster \
  --zone us-central1-a \
  --cluster-version 1.29 \
  --num-nodes 3 \
  --machine-type n1-standard-4

# Drain upgraded pool
kubectl cordon -l cloud.google.com/gke-nodepool=general-purpose
kubectl drain [node-name] --ignore-daemonsets --delete-emptydir-data

# Delete upgraded pool
gcloud container node-pools delete general-purpose \
  --cluster my-cluster \
  --zone us-central1-a
```

**When to rollback:**
- Critical workloads failing to restart after upgrade
- Persistent data corruption or loss
- Performance degradation that doesn't resolve within 1 hour
- GPU workloads unable to schedule or access devices

---

## Troubleshooting

### Node Pool Upgrade Stuck

**Symptom:** Upgrade running for >30 minutes, no progress.

**Diagnosis:**
```bash
kubectl get pdb -A -o wide  # Look for ALLOWED DISRUPTIONS = 0
kubectl get pods -A | grep Pending
kubectl top nodes
gcloud container operations list --cluster my-cluster --zone us-central1-a --filter="operationType=UPGRADE_NODES"
```

**Most likely cause:** PDB blocking drain (Postgres pool especially).

**Fix:**
```bash
# Temporarily relax the PDB
kubectl patch pdb [PDB_NAME] -n [NAMESPACE] \
  -p '{"spec":{"minAvailable":null,"maxUnavailable":"100%"}}'

# Resume upgrade; restore PDB after upgrade completes
```

### Workloads Pending or CrashLoopBackOff

**Symptom:** Pods not scheduling or restarting after upgrade.

**Diagnosis:**
```bash
kubectl get events -A --field-selector reason=FailedScheduling
kubectl logs [pod-name] -n [namespace]
kubectl describe pod [pod-name] -n [namespace]
```

**Common causes:**
- Resource constraints → increase `maxSurge` or scale down non-critical workloads
- Deprecated APIs → update manifests
- Admission webhook issues → check webhook configs

**Fix:**
```bash
# If resource constrained, increase surge for next upgrade phase
gcloud container node-pools update [POOL] \
  --cluster my-cluster \
  --zone us-central1-a \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0
```

### GPU Workloads Not Detecting GPUs

**Symptom:** GPU pods running but `nvidia-smi` shows no devices.

**Diagnosis:**
```bash
kubectl get nodes -o wide | grep gpu
kubectl describe node [gpu-node]  # Check allocatable resources
kubectl logs -n kube-system [nvidia-driver-pod]  # If daemonset exists
```

**Common cause:** GPU driver version mismatch between node image and workload.

**Fix:**
- Verify GPU driver version in target node image
- Update workload container image if driver is incompatible
- Restart GPU daemonsets if present

---

## Maintenance Window Configuration

Set a recurring maintenance window aligned with your upgrade schedule to prevent auto-upgrade conflicts:

```bash
# Saturday 00:00–08:00 UTC (adjust for your timezone)
gcloud container clusters update my-cluster \
  --zone us-central1-a \
  --maintenance-window-start 2026-03-21T00:00:00Z \
  --maintenance-window-end 2026-03-21T08:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

To exclude a specific period (e.g., end-of-quarter freeze):

```bash
gcloud container clusters update my-cluster \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "q2-freeze" \
  --add-maintenance-exclusion-start-time 2026-06-20T00:00:00Z \
  --add-maintenance-exclusion-end-time 2026-06-30T23:59:59Z
```

---

## Timeline & Owner Assignment

| Phase | Task | Duration | Owner | Notes |
|-------|------|----------|-------|-------|
| Pre-upgrade | Complete checklists, DB backups | 2-4 hours | DevOps/SRE | Block until all items green |
| Day 1 | Control plane 1.28→1.29 | 15 min | DevOps/SRE | Early morning recommended |
| Day 1 | General-purpose pool 1.28→1.29 | 10-20 min | DevOps/SRE | Monitor app metrics |
| Day 1 | High-memory pool 1.28→1.29 | 15-30 min | DevOps/SRE + DBA | Monitor Postgres |
| Day 1 | GPU pool 1.28→1.29 | 20-40 min | DevOps/SRE + ML Eng | Verify GPU availability |
| Day 2 | Control plane 1.29→1.30 | 15 min | DevOps/SRE | Early morning |
| Day 2 | General-purpose pool 1.29→1.30 | 10-20 min | DevOps/SRE | |
| Day 2 | High-memory pool 1.29→1.30 | 15-30 min | DevOps/SRE + DBA | |
| Day 2 | GPU pool 1.29→1.30 | 20-40 min | DevOps/SRE + ML Eng | |
| Day 2-3 | Post-upgrade validation | 4-8 hours | DevOps/SRE + App teams | Smoke tests, metric review |

---

## Key Contacts & Escalation

- **DevOps/SRE Lead:** Primary upgrade executor
- **Database Admin:** Oversee Postgres operator upgrade, verify data integrity
- **ML Engineering:** Verify GPU workload health post-upgrade
- **GKE Support:** Contact if control plane upgrade fails or operations stuck >2 hours
- **On-Call:** Available during upgrade window for immediate incident response

---

## References

- [GKE Release Schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule)
- [GKE 1.29 Release Notes](https://cloud.google.com/kubernetes-engine/docs/release-notes)
- [GKE 1.30 Release Notes](https://cloud.google.com/kubernetes-engine/docs/release-notes)
- [PodDisruptionBudget Best Practices](https://cloud.google.com/kubernetes-engine/docs/concepts/pod-disruption-budgets)
- [Node Pool Upgrade Strategies](https://cloud.google.com/kubernetes-engine/docs/concepts/horizontalpodautoscaler-v2#surge_upgrades)
- [GKE Cluster Upgrade Best Practices](https://cloud.google.com/kubernetes-engine/docs/how-to/upgrading-a-cluster)

---

**Document Version:** 1.0
**Last Updated:** 2026-03-18
**Status:** Ready for execution

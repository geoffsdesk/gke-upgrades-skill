# GKE Cluster Upgrade Plan: 1.28 → 1.30

## Executive Summary

This document outlines the upgrade path for a Standard GKE cluster on the Regular release channel, upgrading from Kubernetes 1.28 to 1.30 in the `us-central1-a` zone. The cluster hosts three distinct workload types (general-purpose, Postgres operator, and GPU inference), requiring careful coordination to minimize disruption.

**Target completion:** End of quarter (Q1 2026)
**Estimated downtime:** < 5 minutes per node pool (with surge upgrades)
**Cluster mode:** Standard (manual node management)
**Release channel:** Regular

---

## Cluster Configuration

| Property | Value |
|----------|-------|
| **Cluster Name** | (to be confirmed) |
| **Zone** | us-central1-a |
| **Release Channel** | Regular |
| **Current Control Plane Version** | 1.28.x |
| **Target Version** | 1.30.x |
| **Node Pools** | 3 |
| **Pool 1: General-Purpose** | Standard compute workloads, stateless services |
| **Pool 2: High-Memory (Postgres)** | PostgreSQL operator & data workloads (stateful) |
| **Pool 3: GPU** | ML inference workloads |

---

## Version Compatibility Checks

### Target Version Availability
- **1.30** is available on the Regular release channel as of Q1 2026
- Confirm availability with: `gcloud container get-server-config --zone us-central1-a --format="yaml(channels)"`
- The Regular channel receives versions after validation in Rapid; 1.30 is stable for production workloads

### Version Skew Requirements
- **Node-to-control-plane skew:** Nodes cannot be more than 2 minor versions behind the control plane
- **Path:** 1.28 → 1.29 → 1.30 (sequential upgrades recommended to avoid compatibility surprises)
- Alternatively, 1.28 → 1.30 direct is technically supported (2-minor-version jump), but sequential is safer for workload compatibility
- **Recommendation:** Upgrade control plane to 1.29 first, let nodes stabilize, then proceed to 1.30

### Deprecated APIs & Breaking Changes

**Key checks for 1.28 → 1.30 upgrade:**

1. **API Server Deprecations**
   - Verify no workloads use deprecated APIs with:
     ```bash
     kubectl get --raw /metrics | grep apiserver_request_total
     ```
   - Check the GKE deprecation insights dashboard for usage patterns
   - Common deprecations to watch for: `extensions/v1beta1` Ingress, `batch/v1beta1` CronJob, `apps/v1beta2`

2. **Third-party Controllers**
   - Confirm Postgres operator version supports Kubernetes 1.30
   - Verify GPU operator / NVIDIA driver support for 1.30 nodes
   - Test any admission webhooks and custom operators in a staging environment

3. **Review Release Notes**
   - Kubernetes 1.29 and 1.30 release notes for breaking changes
   - GKE-specific changes: https://cloud.google.com/kubernetes-engine/docs/release-notes

---

## Upgrade Path & Sequencing

### Recommended Approach: Sequential Upgrade with Staged Node Pool Rollout

**Phase 1: Control Plane Upgrade (1.28 → 1.29)**
- Upgrade the control plane first
- This is the required order; control plane must lead
- Nodes can temporarily run at 1.28 while control plane is at 1.29 (within skew limits)

**Phase 2: Node Pool Upgrades (Staggered by workload)**
1. **General-Purpose Pool** (lowest risk, stateless)
2. **GPU Pool** (moderate risk, batch workloads typically restartable)
3. **High-Memory/Postgres Pool** (highest risk, stateful — last)

**Phase 3: Control Plane + Node Upgrade (1.29 → 1.30)**
- Once all pools are at 1.29, upgrade control plane to 1.30
- Roll out node pools again in the same sequence

**Total duration:** 2–4 weeks (with 3–5 business days soak time between phases for validation)

---

## Maintenance Windows & Exclusions

### Maintenance Window Configuration
Set a regular maintenance window for automatic operations (if enabled):
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone us-central1-a \
  --maintenance-window-start 2026-04-01T22:00:00Z \
  --maintenance-window-end 2026-04-01T23:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

**Suggested timing:** Weekend window (e.g., Saturday 10 PM–11 PM US Eastern), off-peak hours

### Maintenance Exclusions
If there is a business-critical period (e.g., major product launch, year-end close), set a maintenance exclusion (up to 30 days):
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "Q1-end-of-quarter" \
  --add-maintenance-exclusion-start-time 2026-03-20T00:00:00Z \
  --add-maintenance-exclusion-end-time 2026-03-31T23:59:59Z
```

**Note:** Manual upgrades (as outlined in this plan) bypass maintenance windows, so you have full control over timing.

---

## Node Pool Upgrade Strategy

### Surge Upgrade Configuration (Recommended)

All three pools will use **surge upgrades** (rolling update with temporary overcapacity). This minimizes downtime and is suitable for all three workload types when properly configured.

#### General-Purpose Pool
- **Purpose:** Stateless services (web servers, APIs, microservices)
- **Surge settings:** `maxSurge=2, maxUnavailable=0`
- **Rationale:** Safe for stateless workloads; surge capacity ensures zero downtime
- **Duration:** ~10–15 minutes (depends on node count and image pull time)

#### GPU Pool
- **Purpose:** ML inference (batch predictions, model serving)
- **Surge settings:** `maxSurge=1, maxUnavailable=0` (GPUs are expensive; limit temporary overcapacity)
- **Rationale:** Batch workloads are typically resilient to interruption; small surge avoids cost spike
- **Duration:** ~15–20 minutes per node
- **Pre-flight:** Confirm node image supports required NVIDIA driver version for 1.30

#### High-Memory/Postgres Pool
- **Purpose:** PostgreSQL operator, data workloads (stateful)
- **Surge settings:** `maxSurge=1, maxUnavailable=0`
- **Rationale:** Single-node surge to limit temporary cluster size; PDBs will protect the database
- **Duration:** ~20–30 minutes per node (StatefulSets take longer to reschedule)
- **Pre-flight:** Verify Postgres operator and backup system compatibility with 1.30

### Why Not Blue-Green for This Cluster?

Blue-green (create new pool, migrate, delete old) is an option but not recommended here because:
- Temporary 2x node capacity is expensive, especially with high-memory and GPU nodes
- Surge upgrades with PDBs are safe and sufficient for stateful workloads
- Simpler operational procedure (fewer moving parts)

---

## Workload Readiness

### Pod Disruption Budgets (PDBs)

**Critical for Postgres Pool:**
Ensure the Postgres operator has a PDB with `minAvailable=1`:
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: postgres-pdb
  namespace: postgres-namespace
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: postgres-operator
```

GKE respects PDBs for up to one hour during surge upgrades. If a pod is protected by a PDB and cannot be evicted, the upgrade pauses gracefully.

**For other workloads:**
Review and add PDBs for any critical or stateful services:
```bash
kubectl get pdb --all-namespaces
kubectl get pods --all-namespaces -l critical=true  # identify critical workloads
```

### Workload Health Checks

**Bare Pods**
Identify and eliminate bare pods (pods without a controller):
```bash
kubectl get pods --all-namespaces --field-selector=metadata.ownerReferences=null
```
Bare pods will not be rescheduled during node drain. Wrap them in Deployments or StatefulSets.

**Graceful Shutdown**
For long-running processes (especially batch jobs on GPU nodes), ensure adequate `terminationGracePeriodSeconds`:
```yaml
spec:
  terminationGracePeriodSeconds: 120  # Allow 2 minutes for cleanup
```

**Resource Requests & Limits**
Verify all pods have resource requests/limits (especially important for accurate scheduler decisions during surge upgrades):
```bash
kubectl get pods --all-namespaces -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.spec.containers[*].resources}{"\n"}{end}' | grep -v '{}' | wc -l
```

### Postgres Operator Compatibility

**Pre-upgrade steps:**
1. Verify Postgres operator version supports Kubernetes 1.30
2. Check operator release notes for 1.29 and 1.30 compatibility
3. Ensure all CRDs are at compatible versions:
   ```bash
   kubectl get crds | grep postgres
   ```
4. Backup all PostgreSQL databases before node pool upgrades
5. Verify PersistentVolume reclaim policy (`Retain` is safest for data):
   ```bash
   kubectl get pv -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.persistentVolumeReclaimPolicy}{"\n"}{end}'
   ```

### GPU Workload Compatibility

**Pre-upgrade steps:**
1. Verify NVIDIA GPU operator / driver compatibility with 1.30 node images
2. Check for GPU workload hard requirements (specific CUDA versions, driver versions)
3. Identify long-running inference jobs that cannot be interrupted — coordinate shutdown before surge
4. Confirm resource requests are accurate (GPU requests in `.spec.containers[].resources.limits.nvidia.com/gpu`)

---

## Pre-Upgrade Checklist

- [ ] **Cluster identification**
  - [ ] Cluster name confirmed: _______________
  - [ ] Zone: us-central1-a
  - [ ] Release channel: Regular

- [ ] **Version checks**
  - [ ] 1.30 is available on Regular channel (confirmed via `gcloud container get-server-config`)
  - [ ] Release notes for 1.29 and 1.30 reviewed
  - [ ] No deprecated API usage detected (checked deprecation insights)

- [ ] **Workload readiness**
  - [ ] Postgres PDB configured with `minAvailable=1`
  - [ ] All pods have controllers (no bare pods)
  - [ ] GPU workloads can tolerate graceful shutdown (terminationGracePeriod adequate)
  - [ ] All pods have resource requests/limits defined
  - [ ] Postgres operator version supports 1.29 and 1.30
  - [ ] GPU operator / NVIDIA driver supports 1.30

- [ ] **Backup & protection**
  - [ ] All PostgreSQL databases backed up
  - [ ] PersistentVolume reclaim policies verified (`Retain` for critical data)
  - [ ] Current cluster snapshot / backup taken
  - [ ] Rollback procedure documented and tested

- [ ] **Infrastructure**
  - [ ] Maintenance window set to off-peak (e.g., weekend, 10 PM)
  - [ ] Maintenance exclusions set for freeze periods (if applicable)
  - [ ] Surge capacity sufficient: at least 1–2 extra nodes per pool
  - [ ] Quota check: `gcloud compute quotas list --filter="metric:~compute/instances"` shows available quota

- [ ] **Communication & ops readiness**
  - [ ] Upgrade window communicated to stakeholders and on-call team
  - [ ] On-call engineer assigned and available
  - [ ] Monitoring and alerting confirmed active (Prometheus, Cloud Monitoring, Cloud Logging)
  - [ ] Runbook prepared and shared with team

---

## Upgrade Execution Runbook

### Phase 1: Control Plane Upgrade to 1.29

#### Pre-flight Checks
```bash
# Verify current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="table(name, currentMasterVersion, nodePools[].version)"

# Check available versions for Regular channel
gcloud container get-server-config --zone us-central1-a \
  --format="yaml(channels)" | grep -A 20 "Regular"

# Verify cluster is in good state
kubectl get nodes
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed
```

#### Control Plane Upgrade
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-central1-a \
  --master \
  --cluster-version 1.29
```

**Expected duration:** 10–15 minutes. Control plane will be briefly unavailable (~1 min), then nodes reconnect.

#### Validation
```bash
# Confirm control plane version
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="value(currentMasterVersion)"
# Should return 1.29.x

# Check system pods are healthy
kubectl get pods -n kube-system -o wide
kubectl get nodes
```

**Soak time:** Wait 24 hours before proceeding to node upgrades, monitoring for any API changes or workload issues.

---

### Phase 2a: General-Purpose Pool Upgrade to 1.29

#### Configure Surge Settings
```bash
gcloud container node-pools update general-purpose \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

#### Upgrade Node Pool
```bash
gcloud container node-pools upgrade general-purpose \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.29
```

**Expected duration:** 10–15 minutes

#### Validation
```bash
# Monitor upgrade progress
gcloud container node-pools list --cluster CLUSTER_NAME --zone us-central1-a
# Check that all nodes transition to 1.29

# Verify pods are running
kubectl get nodes -L cloud.google.com/gke-nodepool
kubectl get pods --all-namespaces -o wide | grep -v Running | grep -v Completed
```

---

### Phase 2b: GPU Pool Upgrade to 1.29

#### Pre-flight for GPU Pool
```bash
# Check for active GPU workloads
kubectl get pods --all-namespaces -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.spec.containers[*].resources.limits.nvidia\.com/gpu}{"\n"}{end}' | grep -v '^[[:space:]]*$'

# Gracefully drain long-running jobs (if needed)
# Coordinate with team to pause inference jobs
```

#### Configure Surge Settings
```bash
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

#### Upgrade Node Pool
```bash
gcloud container node-pools upgrade gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.29
```

**Expected duration:** 15–20 minutes per GPU node (depends on number of nodes)

#### Validation
```bash
# Verify all GPU nodes are ready
kubectl get nodes -L cloud.google.com/gke-nodepool | grep gpu
kubectl get nodes -L nvidia.com/gpu

# Confirm GPU workloads are rescheduling
kubectl get pods --all-namespaces -o wide | grep gpu-pool
```

---

### Phase 2c: High-Memory/Postgres Pool Upgrade to 1.29

#### Pre-flight for Postgres Pool
```bash
# Verify Postgres operator is ready
kubectl get pods -n postgres-namespace -o wide
kubectl get statefulsets -n postgres-namespace

# Check PDB is in place
kubectl get pdb -n postgres-namespace

# Verify database is healthy
# (run operator-specific health check; example: `kubectl exec -it <pod> -- psql -c "SELECT 1"`)
```

#### Configure Surge Settings
```bash
gcloud container node-pools update postgres-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

#### Upgrade Node Pool
```bash
gcloud container node-pools upgrade postgres-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.29
```

**Expected duration:** 20–30 minutes (StatefulSets take longer to reschedule due to PDB protection)

#### Validation
```bash
# Check all Postgres pods are running on new nodes
kubectl get pods -n postgres-namespace -o wide
kubectl describe statefulset -n postgres-namespace

# Verify database connectivity
# (run operator-specific health check)

# Check node pool status
kubectl get nodes -L cloud.google.com/gke-nodepool | grep postgres
```

---

### Phase 3: Control Plane Upgrade to 1.30

#### Pre-flight Checks
```bash
# All node pools should be at 1.29
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="table(name, currentMasterVersion, nodePools[].version)"

# Wait for cluster to stabilize (~24 hours since last upgrade)
kubectl get nodes
kubectl get pods --all-namespaces | grep -v Running | grep -v Completed
```

#### Control Plane Upgrade
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-central1-a \
  --master \
  --cluster-version 1.30
```

**Expected duration:** 10–15 minutes

#### Validation
```bash
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="value(currentMasterVersion)"
# Should return 1.30.x

kubectl get pods -n kube-system
```

---

### Phase 4: Node Pool Upgrades to 1.30

Repeat Phase 2a, 2b, 2c procedures, but upgrade to 1.30:

- **General-Purpose Pool** (lowest risk, stateless) — proceed first
- **GPU Pool** (moderate risk) — second
- **Postgres Pool** (highest risk, stateful) — last

For each pool:
1. Configure surge settings (same as Phase 2)
2. Run upgrade command with `--cluster-version 1.30`
3. Validate node version and workload health
4. Wait 24 hours before next pool

---

## Post-Upgrade Checklist

- [ ] **Cluster health**
  - [ ] Control plane version is 1.30: `gcloud container clusters describe CLUSTER_NAME --zone us-central1-a --format="value(currentMasterVersion)"`
  - [ ] All node pools at 1.30: `gcloud container node-pools list --cluster CLUSTER_NAME --zone us-central1-a`
  - [ ] All nodes in Ready state: `kubectl get nodes`
  - [ ] System pods healthy: `kubectl get pods -n kube-system -o wide`
  - [ ] No PDBs blocking operations: `kubectl get pdb --all-namespaces`

- [ ] **Workload health**
  - [ ] All deployments at desired replica count: `kubectl get deployments --all-namespaces`
  - [ ] No CrashLoopBackOff pods: `kubectl get pods --all-namespaces --field-selector=status.phase!=Running`
  - [ ] Postgres operator healthy: `kubectl get pods -n postgres-namespace`
  - [ ] GPU workloads resuming: `kubectl get pods --all-namespaces -o wide | grep gpu`
  - [ ] Ingress/load balancers healthy: `kubectl get ingress --all-namespaces`
  - [ ] Application health checks passing (smoke tests)

- [ ] **Observability**
  - [ ] Metrics pipeline active (Cloud Monitoring, Prometheus)
  - [ ] Logs flowing (Cloud Logging, external logging)
  - [ ] Error rates within baseline
  - [ ] Latency within baseline
  - [ ] No alerts firing related to upgrade

- [ ] **Cleanup & documentation**
  - [ ] Temporary surge nodes released (automatic at end of pool upgrades)
  - [ ] Upgrade documented in changelog/runbook
  - [ ] Lessons learned captured (what went well, what could improve)
  - [ ] Team debriefing scheduled (optional but recommended)

---

## Rollback Procedure

If critical issues arise during the upgrade, follow this rollback sequence:

### Rollback Node Pools (if in-progress)
```bash
# Stop ongoing node pool upgrade
gcloud container node-pools update POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --no-enable-autoupgrade
```

**Limitation:** Once a node pool has completed upgrading to 1.30, you cannot automatically rollback the nodes to 1.29. You must either:
- Create a new node pool at 1.29 and migrate workloads
- Or, accept the upgrade and troubleshoot the issue

### Rollback Control Plane (if critical)
If the control plane upgrade introduces a critical bug:
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-central1-a \
  --master \
  --cluster-version 1.29
```

**Important:** Control plane downgrades are rare and not recommended unless there is a critical security or stability issue. Contact GKE support before attempting.

### Recovery from Postgres Data Issues
If the Postgres upgrade causes data corruption or operator issues:
1. Restore from backup: `kubectl apply -f <backup-manifest>`
2. Verify data integrity before proceeding
3. Document root cause and escalate to support if needed

---

## Common Issues & Troubleshooting

### Upgrade Stuck on Node Pool

**Symptom:** Node pool upgrade hangs, no nodes transitioning to new version

**Root cause:** PDB is too restrictive; GKE cannot drain nodes

**Resolution:**
```bash
# Check for blocking PDBs
kubectl get pdb --all-namespaces

# Identify which workloads are protected
kubectl get pdb -n <namespace> -o yaml

# If PDB is blocking safely-upgradeable workloads, temporarily adjust:
kubectl patch pdb <pdb-name> -n <namespace> -p '{"spec":{"minAvailable":0}}'

# Retry upgrade after adjustment (then restore PDB afterward)
```

### Pods Not Rescheduling After Node Drain

**Symptom:** Pods remain in `Pending` state after nodes are cordoned

**Root cause:** Cluster is at capacity; no room for pods to reschedule

**Resolution:**
```bash
# Check resource availability
kubectl describe nodes | grep -A 5 "Allocated resources"

# Increase surge capacity temporarily
gcloud container node-pools update POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 3  # Increase surge

# Restart the upgrade
gcloud container node-pools upgrade POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version TARGET_VERSION
```

### GPU Nodes Not Joining Cluster

**Symptom:** GPU nodes stay in NotReady state after upgrade

**Root cause:** NVIDIA driver mismatch between node image and workload requirement

**Resolution:**
```bash
# SSH to a GPU node and check driver version
gcloud compute ssh <node-name> --zone us-central1-a -- nvidia-smi

# Verify expected driver version matches workload requirement
# If mismatch, contact GKE support to confirm node image includes correct driver for 1.30

# Alternatively, create a new GPU node pool with correct image
gcloud container node-pools create gpu-pool-v130 \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --num-nodes 0 \
  --machine-type n1-highmem-4 \
  --accelerator=type=nvidia-tesla-v100,count=1 \
  --cluster-version 1.30
```

### API Deprecation Errors After Upgrade

**Symptom:** Workloads fail with `the server could not find the requested resource` or similar API errors

**Root cause:** Client or admission webhook is calling a deprecated API that was removed in 1.30

**Resolution:**
```bash
# Identify deprecated API usage
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Check validating webhooks
kubectl get validatingwebhookconfigurations
kubectl get mutatingwebhookconfigurations

# Update manifests to use non-deprecated API versions
# Restart affected workloads after manifest update
kubectl rollout restart deployment <deployment-name> -n <namespace>

# If an admission webhook is blocking, check logs:
kubectl logs -n <webhook-namespace> <webhook-pod> -f
```

### Postgres Operator Reconciliation Delays

**Symptom:** Postgres StatefulSet pods stay in Pending for extended period (>5 minutes)

**Root cause:** Operator is slow to react to node drain, or PDB is too restrictive

**Resolution:**
```bash
# Check operator logs
kubectl logs -n postgres-namespace -l app=postgres-operator -f

# Verify PDB allows at least 1 pod to run
kubectl get pdb -n postgres-namespace -o yaml

# If operator is stuck, restart it
kubectl rollout restart deployment postgres-operator -n postgres-namespace

# Retry upgrade
```

---

## Timeline & Milestones

| Phase | Duration | Target Completion | Notes |
|-------|----------|-------------------|-------|
| **Phase 1:** Control plane 1.28 → 1.29 | ~20 min | Week 1 (by Mar 24) | Includes 24h soak time |
| **Phase 2a:** General-purpose pool 1.29 | ~15 min | Week 2 (by Mar 31) | Lowest risk, proceed quickly |
| **Phase 2b:** GPU pool 1.29 | ~20 min | Week 2 (by Mar 31) | Coordinate ML workload downtime |
| **Phase 2c:** Postgres pool 1.29 | ~30 min | Week 3 (by Apr 7) | Includes 24h soak time |
| **Phase 3:** Control plane 1.29 → 1.30 | ~20 min | Week 3 (by Apr 7) | Includes 24h soak time |
| **Phase 4a–4c:** Node pools 1.29 → 1.30 | ~1 hour total | Week 4 (by Apr 14) | Final push to 1.30 |
| **Post-upgrade validation & signoff** | ~1 week | By Apr 21 | Smoke tests, monitoring, documentation |

**End of quarter deadline (Mar 31):** Cluster should be at 1.30 by this date.

---

## Decision Checkpoints

Before each phase, confirm:

1. **No production incidents in progress** — upgrade during stable operational period
2. **Workloads are healthy** — no CrashLoopBackOff pods or alerts
3. **Monitoring is active** — metrics, logs, and alerts in place
4. **Stakeholder approval** — team lead/SRE confirms green light
5. **On-call team ready** — engineer assigned and available for post-upgrade monitoring

---

## Contacts & Escalation

| Role | Responsibility |
|------|-----------------|
| **Cluster owner** | Approves timeline, communicates to stakeholders |
| **SRE/Platform engineer** | Executes upgrade, monitors progress, troubleshoots |
| **Postgres team** | Verifies operator compatibility, backup status |
| **ML/Data team** | Coordinates GPU workload pause/resume |
| **On-call engineer** | Monitors post-upgrade for 24 hours |
| **GKE support** | Escalation point for driver issues, critical bugs |

---

## Appendix: Useful Commands

```bash
# Get cluster version info
gcloud container clusters describe CLUSTER_NAME --zone us-central1-a

# List available versions for release channel
gcloud container get-server-config --zone us-central1-a --format="yaml(channels)"

# Check node pool versions
gcloud container node-pools list --cluster CLUSTER_NAME --zone us-central1-a

# Monitor node pool upgrade progress (in real-time)
watch 'kubectl get nodes -L cloud.google.com/gke-nodepool'

# Check PDB status
kubectl get pdb --all-namespaces

# Check for pods without controllers
kubectl get pods --all-namespaces --field-selector=metadata.ownerReferences=null

# Monitor system pods
kubectl get pods -n kube-system -o wide --watch

# Check API server metrics for deprecated API calls
kubectl get --raw /metrics | grep apiserver_request_total

# Restart a deployment to force pod rescheduling
kubectl rollout restart deployment <name> -n <namespace>

# Drain a node manually (if needed for emergency)
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data
```

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-03-18 | GKE Upgrade Planner | Initial plan (1.28 → 1.30 sequential upgrade) |

---

**This plan should be reviewed and approved by the cluster owner and on-call team before execution. Update placeholder fields (CLUSTER_NAME, namespaces, contact names) with actual values.**

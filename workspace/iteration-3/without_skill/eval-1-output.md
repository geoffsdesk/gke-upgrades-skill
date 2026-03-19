# GKE Cluster Upgrade Plan: 1.28 to 1.30
**Cluster:** Standard GKE | **Release Channel:** Regular | **Location:** us-central1-a
**Timeline:** Before end of Q2 2026 | **Target Version:** 1.28 → 1.30

---

## Executive Summary
This upgrade plan outlines the steps to safely upgrade your GKE cluster from Kubernetes 1.28 to 1.30 across three node pools with varying workload requirements. The upgrade path is straightforward (1.28 → 1.29 → 1.30) and accounts for stateful workloads (Postgres operator) and GPU infrastructure.

---

## Pre-Upgrade Readiness Checklist

### Cluster Health Verification
- [ ] Run `kubectl get nodes` and verify all nodes are in Ready state
- [ ] Run `kubectl top nodes` and confirm CPU/memory headroom on all pools
- [ ] Verify cluster autoscaler is functioning correctly across all node pools
- [ ] Check for any pending or stuck workloads via `kubectl get pods --all-namespaces | grep -E "Pending|CrashLoop"`
- [ ] Review current GKE cluster configuration (enable network policies, Workload Identity, Binary Authorization if not present)

### Backup and Disaster Recovery
- [ ] Create snapshots of persistent volumes used by Postgres operator
- [ ] Verify etcd backup policy is enabled (automatic in Standard GKE)
- [ ] Document current cluster state (version, add-ons, node configurations)
- [ ] Test restore procedures for Postgres operator databases

### Dependency and Compatibility Checks
- [ ] Review Kubernetes 1.29 and 1.30 release notes for deprecations
- [ ] Audit custom CNI plugins or network policies for compatibility
- [ ] Check Postgres operator version compatibility with K8s 1.30
- [ ] Verify GPU drivers and NVIDIA CUDA operator compatibility with target K8s version
- [ ] Validate all third-party add-ons and operators (Helm charts, CRDs)
- [ ] Review API deprecations: confirm no workloads use deprecated APIs (e.g., policy/v1beta1 PodDisruptionBudget)

### Load Testing and Staging
- [ ] If possible, create a staging cluster at 1.28 and upgrade it first to validate workload behavior
- [ ] Perform load testing on the staging cluster to ensure Postgres operator and ML inference workloads function correctly
- [ ] Document any issues found and remediate before production upgrade

---

## Upgrade Path and Timeline

### Phase 1: Control Plane Upgrade to 1.29 (Week 1)
**Duration:** 1-2 hours downtime expected for managed control plane

1. **Enable Maintenance Window (Optional but Recommended)**
   - Configure a maintenance window in GKE to schedule upgrade outside business hours
   - GKE will perform rolling control plane updates automatically

2. **Initiate Control Plane Upgrade to 1.29**
   ```bash
   gcloud container clusters upgrade CLUSTER_NAME \
     --master \
     --cluster-version 1.29 \
     --zone us-central1-a
   ```
   - GKE control plane upgrades are transparent; no user-facing downtime if using multiple control plane replicas
   - Monitor upgrade progress via GCP Console or `gcloud container operations list`

3. **Validation Post-Upgrade**
   - Verify control plane is healthy: `kubectl get nodes` and `kubectl get componentstatuses`
   - Check cluster add-ons are running (metrics-server, DNS, etc.)
   - Ensure no pending workloads or node issues

---

### Phase 2: Node Pool Upgrades to 1.29 (Week 1-2)
**Recommended order:** General-purpose pool → High-memory pool (Postgres) → GPU pool

#### General-Purpose Node Pool Upgrade
1. **Initiate Node Pool Upgrade**
   ```bash
   gcloud container node-pools update general-purpose \
     --cluster CLUSTER_NAME \
     --zone us-central1-a \
     --node-version 1.29
   ```

2. **Monitor Rolling Update**
   - GKE performs rolling node replacement (respects PodDisruptionBudgets)
   - Typical time: 15-30 minutes per node depending on workload density
   - Watch: `kubectl get nodes -w` to observe node cycling

3. **Validation**
   - All pods remain running during update due to graceful termination
   - Check pod logs for any startup issues post-upgrade

#### High-Memory Node Pool (Postgres Operator) Upgrade
1. **Pre-Upgrade Checks for Postgres**
   - Verify Postgres operator version compatibility with K8s 1.29
   - Ensure database replicas are healthy: `kubectl get postgresql -A`
   - Confirm backup snapshots are recent

2. **Initiate Upgrade with Extended Drain Time**
   ```bash
   gcloud container node-pools update high-memory \
     --cluster CLUSTER_NAME \
     --zone us-central1-a \
     --node-version 1.29 \
     --max-surge 1 \
     --max-unavailable 1
   ```
   - Use conservative surge/unavailable settings to minimize Postgres disruption
   - Allow 5-10 minutes per node for graceful connection draining

3. **Monitor Postgres Operator Behavior**
   - Watch replica sync status: `kubectl logs -f -n postgres <operator-pod>`
   - Verify no data loss: run test queries against databases

#### GPU Node Pool Upgrade
1. **Pre-Upgrade GPU Checks**
   - Verify NVIDIA GPU Operator is compatible with K8s 1.29
   - Confirm all GPU workloads can tolerate node restarts
   - Check ML inference jobs are checkpointing/resumable

2. **Initiate GPU Node Pool Upgrade**
   ```bash
   gcloud container node-pools update gpu \
     --cluster CLUSTER_NAME \
     --zone us-central1-a \
     --node-version 1.29 \
     --max-unavailable 1
   ```
   - GPU node cycling may cause brief inference job interruptions
   - Ensure model serving containers have restart policies set to Always

3. **Validation**
   - Run GPU availability check: `kubectl get nodes -L gpu=true`
   - Verify CUDA workloads initialize correctly on upgraded nodes

---

### Phase 3: Control Plane Upgrade to 1.30 (Week 2-3)
**Duration:** 1-2 hours downtime expected

1. **Initiate Control Plane Upgrade**
   ```bash
   gcloud container clusters upgrade CLUSTER_NAME \
     --master \
     --cluster-version 1.30 \
     --zone us-central1-a
   ```

2. **Validation**
   - Verify control plane components: `kubectl get nodes`
   - Check all cluster add-ons operational
   - Review any 1.30-specific feature gates or API changes in logs

---

### Phase 4: Node Pool Upgrades to 1.30 (Week 3)
**Follow same order and procedures as Phase 2, but targeting version 1.30**

#### Parallel Upgrade Opportunity
- If confident, upgrade general-purpose and GPU pools in parallel (different node pool operations)
- Keep high-memory (Postgres) pool sequential and monitored closely

---

## Risk Mitigation Strategies

### For Postgres Operator Workloads
- **PodDisruptionBudget:** Ensure PDB exists allowing at most 0 simultaneous evictions during upgrade
- **Pod Antiaffinity:** Verify Postgres pods are spread across different nodes for resilience
- **Replica Quorum:** Monitor primary-replica synchronization during node transitions
- **Failover Testing:** Pre-test manual failover procedures to ensure rapid recovery if issues occur

### For GPU Inference Workloads
- **Model Serving Replicas:** Use multiple replicas of inference services for fault tolerance during node churn
- **Gradual Traffic Shift:** Route traffic via load balancer with session affinity if applicable
- **Batch Job Checkpointing:** Enable checkpointing for long-running batch ML jobs
- **Monitoring:** Track GPU utilization, inference latency, and error rates during upgrade

### General Cluster Resilience
- **Resource Buffers:** Maintain 20-30% spare capacity on each node pool to absorb pod relocations
- **Node Affinity:** Review and adjust pod scheduling to avoid "blast radius" of single-node failures
- **Monitoring and Alerts:** Set up alerts for node NotReady conditions, pod eviction rates, and API latency
- **Rollback Plan:** GKE doesn't support cluster downgrade, but have tested restore-from-snapshot procedures ready

---

## Monitoring and Validation Throughout Upgrade

### Key Metrics to Watch
- **Node Status:** All nodes transition through NotReady → Ready states smoothly
- **Pod Churn:** Monitor eviction rate; should not exceed 5-10 pods/minute
- **API Latency:** `kube-apiserver` latency should remain < 100ms during upgrade
- **Persistent Volume I/O:** Ensure database and storage workloads continue operating
- **GPU Utilization:** Inference workloads maintain throughput during GPU node cycling

### Health Checks
```bash
# Monitor node upgrade progress
kubectl get nodes -L kubernetes.io/os -w

# Check all pod status
kubectl get pods --all-namespaces | grep -v Running

# Verify PV mounts and database health
kubectl get pvc --all-namespaces

# Monitor Postgres operator
kubectl get postgresql -A -o wide

# Check GPU availability
kubectl get nodes -o json | jq '.items[] | {name:.metadata.name, gpus:.status.allocatable["nvidia.com/gpu"]}'
```

### Post-Upgrade Validation
- [ ] All nodes report `1.30` in `kubectl version --short`
- [ ] All workloads are Running and Ready
- [ ] Postgres replication is caught up and healthy
- [ ] GPU inference workloads are serving requests without latency degradation
- [ ] Persistent volumes are mounted and accessible
- [ ] No unexplained pod restarts in audit logs

---

## Rollback Procedure

**Important:** Kubernetes does not support cluster downgrade. If critical issues arise:

1. **Rollback Approach:** Restore from pre-upgrade backup snapshot
   - If using persistent volume snapshots, restore Postgres from backup
   - Recreate cluster from backup or use Terraform/IaC to redeploy at previous version

2. **Mitigation:** This is why pre-upgrade testing on a staging cluster is critical

3. **Decision Point:** If 1.29 or 1.30 introduces blocking issues, roll back entire cluster to 1.28 via restore

---

## Timeline Summary

| Phase | Target Version | Node Pool | Estimated Duration | Week |
|-------|-----------------|-----------|-------------------|------|
| 1     | 1.29            | Control Plane | 1-2 hours | Week 1 |
| 2     | 1.29            | General Purpose | 30 min | Week 1 |
| 2     | 1.29            | High Memory (Postgres) | 30-45 min | Week 1-2 |
| 2     | 1.29            | GPU | 30 min | Week 2 |
| 3     | 1.30            | Control Plane | 1-2 hours | Week 2-3 |
| 4     | 1.30            | General Purpose | 30 min | Week 3 |
| 4     | 1.30            | High Memory (Postgres) | 30-45 min | Week 3 |
| 4     | 1.30            | GPU | 30 min | Week 3 |

**Total Estimated Time:** 3-4 weeks elapsed time (comfort margin included)
**Total Active Downtime:** 2-4 hours (control plane only)

---

## Post-Upgrade Steps

1. **Update Node Image Types (if applicable)**
   - Review if newer GKE node image types are available for improved security and performance

2. **Verify New Features in 1.30**
   - Review Kubernetes 1.30 release notes for new features beneficial to your workloads
   - Example features: improved scheduling, API enhancements, security updates

3. **Update kubectl Clients**
   - Recommend all developers update their local `kubectl` to 1.30
   - No breaking changes, but features and diagnostics improve with version match

4. **Update CI/CD Pipelines**
   - Update Kubernetes base image versions in container builds if hardcoding K8s version
   - Verify Helm charts and operators are compatible with 1.30

5. **Documentation Update**
   - Update cluster documentation to reflect new version
   - Publish post-upgrade lessons learned and any workarounds discovered

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Postgres replica lag during node eviction | Medium | High | Pre-test failover; use conservative max-unavailable settings |
| GPU inference job interruption | Medium | Medium | Use multi-replica deployment; implement job checkpointing |
| etcd corruption during upgrade | Low | Critical | Verify backup policies; test restore procedures |
| Incompatible third-party operator | Low-Medium | Medium | Test staging cluster upgrade first |
| API timeout during high workload transitions | Low | Low | Monitor API latency; scale back jobs during upgrade window |

---

## Sign-Off Checklist

Before proceeding with production upgrade:
- [ ] Staging cluster upgrade completed successfully
- [ ] Load testing confirms all workloads (Postgres, ML inference) function correctly
- [ ] Backup and disaster recovery tested and documented
- [ ] On-call team briefed on upgrade timeline and rollback procedures
- [ ] Monitoring and alerting configured for upgrade window
- [ ] Maintenance window scheduled outside peak traffic hours
- [ ] All node pool configurations reviewed and validated

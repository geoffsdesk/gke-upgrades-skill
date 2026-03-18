# GKE Cluster Upgrade Plan: 1.28 → 1.30

**Cluster Details:**
- Cluster Type: Standard GKE
- Release Channel: Regular
- Region: us-central1-a
- Current Version: 1.28
- Target Version: 1.30
- Deadline: End of Q1 2026 (March 31, 2026)
- Node Pools: 3 (General-Purpose, High-Memory, GPU)

---

## Executive Summary

This plan outlines the safe migration of your GKE cluster from Kubernetes 1.28 to 1.30, accounting for two minor version upgrades with careful attention to workload compatibility and zero-downtime principles. The upgrade must be completed by March 31, 2026 (13 days from today).

---

## Pre-Upgrade Assessment

### 1.1 Timeline Considerations

**Critical:** Only 13 days remain until the deadline. Recommend immediate action to avoid delays.

- Pre-upgrade testing should begin immediately
- Schedule upgrade windows during off-peak hours
- Allocate 2-3 days for the full upgrade process (control plane + 3 node pools)

### 1.2 API Deprecations Review

**Between 1.28 and 1.30, monitor for:**

- **Kubernetes 1.29 changes:**
  - ValidatingAdmissionPolicy graduates to stable (watch for webhook configurations)
  - PodDisruptionBudget v1beta1 deprecated (use v1)
  - Node feature discovery API updates
  - Windows container runtime improvements

- **Kubernetes 1.30 changes:**
  - Further PDB API stabilization
  - Pod resources API improvements
  - Enhanced workload identity features
  - Potential container runtime updates on nodes

**Action Items:**
- Audit your applications for PodDisruptionBudget v1beta1 usage → migrate to v1
- Review any ValidatingAdmissionPolicy webhook configurations
- Test webhook and CustomResourceDefinition compatibility
- Check for deprecated APIs: `kubectl api-resources --verbs=list --namespaced=false | grep -i deprecated`

### 1.3 Cluster Readiness Checklist

- [ ] Backup critical cluster configurations and etcd (if using custom etcd)
- [ ] Verify GKE Backup & Disaster Recovery is enabled
- [ ] Document current workload resource utilization (CPU/memory)
- [ ] Identify critical workloads requiring Pod Disruption Budgets
- [ ] Verify PodDisruptionBudget coverage for Postgres operator and ML services
- [ ] Test cluster autoscaling behavior under load
- [ ] Confirm adequate node pool capacity for rolling updates
- [ ] Review and test any custom DaemonSets compatibility with new Kubernetes versions
- [ ] Document current network policies and ingress configurations
- [ ] Verify all operator versions are compatible with target Kubernetes versions

---

## Upgrade Strategy

### 2.1 Recommended Approach: Phased Control Plane + Rolling Node Pool Upgrades

This strategy minimizes risk and ensures workload continuity:

1. **Phase 1 (Day 1-2):** Control plane upgrade (1.28 → 1.30)
2. **Phase 2 (Day 3-4):** General-purpose node pool upgrade
3. **Phase 3 (Day 5-6):** High-memory node pool upgrade (Postgres)
4. **Phase 4 (Day 7):** GPU node pool upgrade
5. **Phase 5 (Day 8):** Validation and post-upgrade testing

**Rationale:**
- Control plane upgrade is rapid and has minimal impact during rolling updates
- General-purpose pool typically handles diverse workloads (safe to upgrade first)
- Postgres pool has lower tolerance for disruption (upgrade with careful PDB validation)
- GPU pool typically has fewer/larger workloads (upgrade last, monitor carefully)

### 2.2 GKE Automatic Upgrades Consideration

**Important Decision Point:**

If you have automatic upgrades enabled:
- Control plane auto-upgrades occur on a fixed schedule
- You can choose to manually initiate immediately or wait for automatic window
- **Recommendation:** Manually trigger upgrade now to control the timing given your tight deadline

To manually initiate: Navigate to GKE cluster details → "Upgrade Now" button on the cluster

### 2.3 Node Pool Upgrade Windows

Recommended upgrade sequence and estimated duration:

```
Day 1-2:   Control plane: 1.28 → 1.30 (1-2 hours, nodes continue running)
Day 3-4:   General-purpose pool (rolling 33% at a time, ~2-4 hours)
Day 5-6:   High-memory pool (rolling 33% at a time, ~2-4 hours)
Day 7:     GPU pool (rolling 25% at a time, ~2-3 hours)
Day 8:     Post-upgrade validation and rollback plan deactivation
```

---

## Phase-by-Phase Implementation

### Phase 1: Control Plane Upgrade (1.28 → 1.30)

**Duration:** 1-2 hours (expect 30-60 minutes of brief API server unavailability during transition)

**Steps:**

1. **Pre-upgrade validation:**
   ```bash
   # Check current API server and components
   kubectl get nodes -o wide
   kubectl get componentstatuses

   # Verify cluster can schedule pods
   kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded
   ```

2. **Trigger control plane upgrade via gcloud CLI:**
   ```bash
   gcloud container clusters upgrade CLUSTER_NAME \
     --master \
     --cluster-version=1.30.0-gke.0 \
     --zone=us-central1-a
   ```

   OR use Google Cloud Console → Cluster Details → "Upgrade" button

3. **Monitor upgrade progress:**
   ```bash
   # Watch control plane status (will briefly show unavailability)
   watch kubectl get nodes

   # Monitor system pod restarts
   kubectl get pods -n kube-system -w
   ```

4. **Post-upgrade verification:**
   ```bash
   # Verify control plane version
   kubectl version --short

   # Check cluster health
   kubectl cluster-info
   kubectl top nodes

   # Verify system pods are running
   kubectl get pods -n kube-system
   ```

### Phase 2: General-Purpose Node Pool Upgrade

**Duration:** 2-4 hours

**Node pool name:** `general-purpose` (adjust if different)

**Steps:**

1. **Pre-upgrade health check:**
   ```bash
   # Verify pod distribution across nodes
   kubectl get pods -A -o wide | grep general-purpose-pool

   # Check for any pending pods
   kubectl get pods -A --field-selector=status.phase=Pending
   ```

2. **Enable surge upgrade to speed up process (optional but recommended):**
   ```bash
   gcloud container node-pools update general-purpose \
     --cluster=CLUSTER_NAME \
     --zone=us-central1-a \
     --surge-upgrade \
     --max-surge-upgrade=1 \
     --max-unavailable-upgrade=0
   ```

3. **Trigger node pool upgrade:**
   ```bash
   gcloud container node-pools upgrade general-purpose \
     --cluster=CLUSTER_NAME \
     --zone=us-central1-a \
     --cluster-version=1.30.0-gke.0
   ```

4. **Monitor upgrade:**
   ```bash
   # Watch node status in real-time
   watch kubectl get nodes -L cloud.google.com/gke-nodepool

   # Monitor pod rescheduling
   kubectl get events -A --sort-by='.lastTimestamp' -w
   ```

5. **Verify upgrade completion:**
   ```bash
   gcloud container node-pools describe general-purpose \
     --cluster=CLUSTER_NAME \
     --zone=us-central1-a | grep version
   ```

### Phase 3: High-Memory Node Pool Upgrade (Postgres Operator)

**Duration:** 2-4 hours (upgrade more conservatively due to database workload)

**Node pool name:** `high-memory` (adjust if different)

**Pre-upgrade considerations:**

- Postgres operator typically runs with StatefulSets and persistent volumes
- Ensure PodDisruptionBudgets are configured for your Postgres instances
- Coordinate with database team to prepare for potential pod restarts

**Steps:**

1. **Validate Postgres operator readiness:**
   ```bash
   # Identify Postgres instances on this pool
   kubectl get statefulsets -A -o wide | grep postgres

   # Check PodDisruptionBudget coverage
   kubectl get pdb -A

   # Verify persistent volume availability
   kubectl get pvc -A
   ```

2. **Ensure Postgres has failover capability (if applicable):**
   ```bash
   # Check for replicas in high-memory pool
   kubectl get pods -A -L cloud.google.com/gke-nodepool | grep high-memory
   ```

3. **Optional: Update surge settings for controlled rollout:**
   ```bash
   gcloud container node-pools update high-memory \
     --cluster=CLUSTER_NAME \
     --zone=us-central1-a \
     --max-surge-upgrade=1 \
     --max-unavailable-upgrade=0
   ```

4. **Trigger upgrade:**
   ```bash
   gcloud container node-pools upgrade high-memory \
     --cluster=CLUSTER_NAME \
     --zone=us-central1-a \
     --cluster-version=1.30.0-gke.0
   ```

5. **Monitor with focus on database health:**
   ```bash
   # Watch for Pod restarts
   kubectl get pods -A -w -L cloud.google.com/gke-nodepool | grep high-memory

   # Check database logs
   kubectl logs -n POSTGRES_NAMESPACE -l app=postgres -f --tail=50

   # Monitor persistent volumes
   kubectl get pv
   ```

6. **Post-upgrade database validation:**
   ```bash
   # Connect to database and validate
   kubectl exec -it POD_NAME -n POSTGRES_NAMESPACE -- psql -c "SELECT version();"
   ```

### Phase 4: GPU Node Pool Upgrade

**Duration:** 2-3 hours

**Node pool name:** `gpu` (adjust if different)

**Pre-upgrade considerations:**

- GPU workloads are often long-running ML inference jobs
- Pod eviction during upgrade may interrupt in-flight predictions
- Ensure adequate PodDisruptionBudgets for critical ML services

**Steps:**

1. **Assess current GPU workload:**
   ```bash
   # Check GPU utilization
   kubectl top nodes -L cloud.google.com/gke-nodepool | grep gpu

   # List GPU-bound pods
   kubectl get pods -A -o json | jq '.items[] | select(.spec.containers[].resources.limits."nvidia.com/gpu") | {namespace: .metadata.namespace, name: .metadata.name}'
   ```

2. **Configure upgrade parameters (conservative for stateful workloads):**
   ```bash
   gcloud container node-pools update gpu \
     --cluster=CLUSTER_NAME \
     --zone=us-central1-a \
     --max-surge-upgrade=1 \
     --max-unavailable-upgrade=0
   ```

3. **Trigger upgrade:**
   ```bash
   gcloud container node-pools upgrade gpu \
     --cluster=CLUSTER_NAME \
     --zone=us-central1-a \
     --cluster-version=1.30.0-gke.0
   ```

4. **Monitor upgrade:**
   ```bash
   # Watch GPU node status
   watch kubectl get nodes -L cloud.google.com/gke-nodepool,nvidia.com/gpu

   # Monitor GPU workload rescheduling
   kubectl get pods -A -w -L cloud.google.com/gke-nodepool | grep gpu

   # Check for GPU allocation errors
   kubectl describe nodes | grep -A 10 "nvidia.com/gpu"
   ```

5. **Post-upgrade GPU validation:**
   ```bash
   # Verify GPU availability
   kubectl describe nodes -l cloud.google.com/gke-nodepool=gpu | grep nvidia.com/gpu

   # Run a test GPU workload
   kubectl run gpu-test --image=nvidia/cuda:11.0.3-runtime-ubuntu20.04 --limits='nvidia.com/gpu=1' -- nvidia-smi
   ```

---

## Risk Mitigation & Rollback

### 3.1 Pre-Upgrade Backup Strategy

1. **Create GKE cluster backup:**
   ```bash
   # If using GKE Backup & Disaster Recovery
   gcloud container backup-restore backups create pre-upgrade-backup \
     --cluster=CLUSTER_NAME \
     --location=us-central1
   ```

2. **Backup critical resources:**
   ```bash
   # Export key resources
   kubectl get all,cm,secrets,pvc -A -o yaml > cluster-backup-$(date +%Y%m%d).yaml
   ```

3. **Document current state:**
   ```bash
   # Save cluster configuration
   gcloud container clusters describe CLUSTER_NAME --zone=us-central1-a > cluster-config.json

   # Export node pool configurations
   gcloud container node-pools list --cluster=CLUSTER_NAME --zone=us-central1-a
   ```

### 3.2 Handling Pod Disruptions

**Best Practices:**

1. **Ensure Pod Disruption Budgets (PDB) are defined:**
   - Critical services: `minAvailable: 1`
   - General services: `maxUnavailable: 1`
   - Non-critical: Can omit or set `maxUnavailable: 100%`

2. **Verify PDB coverage:**
   ```bash
   # List all PDBs
   kubectl get pdb -A

   # Identify workloads without PDB
   kubectl get deployments,statefulsets -A -o json | \
     jq '.items[] | select(.metadata.labels.pdb == null) | {namespace: .metadata.namespace, name: .metadata.name}'
   ```

3. **Create PDBs for critical workloads before upgrade:**
   ```yaml
   apiVersion: policy/v1
   kind: PodDisruptionBudget
   metadata:
     name: postgres-pdb
     namespace: default
   spec:
     minAvailable: 1
     selector:
       matchLabels:
         app: postgres
   ```

### 3.3 Rollback Plan

**If critical issues arise:**

1. **GKE does NOT support downgrading cluster versions directly**. Instead:

   - Use GKE Backup & Disaster Recovery to restore to pre-upgrade backup
   - Create a new cluster from snapshot if backup available
   - Migrate workloads back if partial rollback needed

2. **Abort upgrade process:**
   - Stop node pool upgrades immediately (gcloud CLI)
   - Wait for ongoing upgrades to complete/fail
   - Revert to 1.28 control plane only if critical issues detected (contact GKE support)

3. **Contact Google Cloud Support if:**
   - Control plane upgrade fails or gets stuck
   - Critical APIs become unavailable post-upgrade
   - Multiple node pools fail upgrade simultaneously
   - Production workloads show critical errors

---

## Compatibility & Testing

### 4.1 Pre-Upgrade Testing

**Recommended test sequence (run immediately, before production upgrade):**

1. **Test cluster upgrade in non-prod environment:**
   - Create a temporary test cluster with same configuration
   - Upgrade test cluster from 1.28 → 1.30
   - Deploy sample workloads from production
   - Verify workload behavior

2. **Application compatibility testing:**
   ```bash
   # Test deployments
   kubectl rollout restart deployment/DEPLOYMENT_NAME -n NAMESPACE

   # Verify application health checks
   kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded
   ```

3. **Custom resource compatibility:**
   ```bash
   # Check for CRD conflicts
   kubectl api-resources | grep -v kubeadm

   # Validate all CRDs
   kubectl get crd -o json | jq '.items[].metadata.name'
   ```

### 4.2 Known Compatibility Issues (1.28 → 1.30)

**Container Runtime:**
- Node image will be updated (likely GKE Ubuntu or COS)
- Existing containers continue running
- Monitor daemon processes during node upgrade

**Networking:**
- Network policies remain compatible
- Service mesh (if used) may have minor version requirements
- CNI plugins (Calico, Weave, etc.) should be compatible

**Storage:**
- PersistentVolume APIs remain stable
- StatefulSet behavior unchanged
- Verify backup/restore procedures work post-upgrade

**Monitoring & Logging:**
- Prometheus/Grafana: Monitor scrape targets post-upgrade
- Fluent Bit/Logstash: Verify log delivery continues
- GKE Metrics: System metrics dashboards should show no gaps

---

## Post-Upgrade Validation

### 5.1 Cluster Health Verification

**Immediately after entire upgrade:**

```bash
# 1. Verify cluster version
kubectl version --short

# 2. Check node health
kubectl get nodes -o wide
kubectl top nodes

# 3. Verify system pods
kubectl get pods -n kube-system -o wide
kubectl get pods -n gke-system -o wide

# 4. Check persistent volumes
kubectl get pv,pvc -A

# 5. Verify networking
kubectl get services -A
kubectl get ingress -A

# 6. Check for API deprecation warnings
kubectl api-resources

# 7. Monitor cluster events for errors
kubectl get events -A --sort-by='.lastTimestamp' | tail -20
```

### 5.2 Workload Health Verification

**By workload type:**

**General-purpose workloads:**
```bash
# Check deployment replicas are ready
kubectl get deployments -A

# Verify no pending pods
kubectl get pods -A --field-selector=status.phase=Pending
```

**Postgres Operator:**
```bash
# Check statefulset status
kubectl get statefulsets -n POSTGRES_NAMESPACE

# Verify database connections working
kubectl exec -it POSTGRES_POD -n POSTGRES_NAMESPACE -- psql -c "SELECT 1;"

# Check for replication lag
kubectl exec -it POSTGRES_POD -n POSTGRES_NAMESPACE -- psql -c "SELECT pg_last_wal_receive_lsn();"
```

**GPU workloads:**
```bash
# Verify GPU allocation
kubectl describe nodes -l cloud.google.com/gke-nodepool=gpu | grep nvidia.com/gpu

# Test GPU availability
kubectl run gpu-test --image=nvidia/cuda:11.0.3-runtime-ubuntu20.04 \
  --limits='nvidia.com/gpu=1' -- nvidia-smi
```

### 5.3 Performance Baseline

**Compare against pre-upgrade metrics:**

```bash
# Memory usage
kubectl top nodes

# CPU usage
kubectl top pods -A | head -20

# Network throughput
# (use your monitoring solution - Prometheus, Cloud Monitoring, etc.)

# Disk I/O for Postgres
# (monitor PersistentVolume performance in Cloud Monitoring)
```

---

## Timeline Summary

| Date | Phase | Tasks | Duration | Owner |
|------|-------|-------|----------|-------|
| **Day 1** | Pre-Upgrade | Create backup, verify PDBs, test compatibility | 4-6 hours | DevOps/SRE |
| **Day 2** | Control Plane | Upgrade control plane 1.28 → 1.30, validate APIs | 1-2 hours | DevOps/SRE |
| **Day 3-4** | General Pool | Upgrade general-purpose node pool | 2-4 hours | DevOps/SRE |
| **Day 5-6** | High-Memory Pool | Upgrade Postgres node pool with database team | 2-4 hours | DevOps/SRE + DB Team |
| **Day 7** | GPU Pool | Upgrade GPU node pool, validate ML services | 2-3 hours | DevOps/SRE + ML Team |
| **Day 8** | Post-Upgrade | Full validation, performance testing, cleanup | 4-6 hours | DevOps/SRE + App Teams |
| **Day 9-13** | Buffer | Monitoring, hotfix window if needed | Ongoing | On-call |

**Total Active Time:** 13-25 hours over 8 days
**Deadline:** March 31, 2026 (13 days remaining)

---

## Communication Plan

### 6.1 Pre-Upgrade Announcements

**48 hours before control plane upgrade:**
- Notify all teams: upgrade window scheduled
- Expected maintenance window: 1-2 hours for each phase
- Possible pod restarts on non-critical workloads

**24 hours before:**
- Final confirmation of maintenance window
- Request teams run health checks on their workloads

### 6.2 During Upgrade

- Real-time status updates on #incident or #sre-operations Slack channel
- Post updates every 15-30 minutes during active upgrade windows
- Alert teams immediately if issues detected

### 6.3 Post-Upgrade

- Announcement when each node pool is fully upgraded
- Request feedback on workload health
- Schedule retrospective if any issues occurred

---

## Troubleshooting Guide

### Common Issues & Solutions

| Issue | Symptoms | Solution |
|-------|----------|----------|
| **Pod eviction failures** | Pods stuck in `Terminating` state | Check PDB configurations; increase grace period if needed |
| **Node upgrade timeout** | Nodes stuck in `NotReady` state after 30+ min | Check node system logs; restart kubelet if needed |
| **GPU allocation errors** | GPU pods can't schedule post-upgrade | Restart GPU device plugin: `kubectl delete pod -n kube-system -l app=nvidia-device-plugin` |
| **API deprecation errors** | Workloads fail with API version errors | Migrate resources to stable API versions (v1 instead of v1beta1) |
| **Postgres connection loss** | Database pods become unreachable | Check PersistentVolume mounting; verify network policies |
| **Control plane timeout** | API server unavailable during upgrade | Wait 5-10 minutes; control plane typically recovers automatically |

---

## Approval & Sign-Off

**Plan Prepared By:** GKE DevOps Team
**Date Prepared:** 2026-03-18
**Review Required From:**
- [ ] Platform Engineering Lead
- [ ] Database Administrator (Postgres)
- [ ] ML Engineering Lead (GPU workloads)
- [ ] Security/Compliance (if applicable)

**Final Approval:** _____________________ Date: _______

**Execution Lead:** _____________________ Date: _______

---

## References & Documentation

- [GKE Release Notes for 1.29 & 1.30](https://cloud.google.com/kubernetes-engine/docs/release-notes)
- [GKE Cluster Upgrades Guide](https://cloud.google.com/kubernetes-engine/docs/how-to/upgrading-a-cluster)
- [Kubernetes 1.29 Deprecations](https://kubernetes.io/docs/reference/using-api/deprecation-guide/#v1-29)
- [Kubernetes 1.30 Release Notes](https://kubernetes.io/blog/2024/04/release-kubernetes-v1-30/)
- [Pod Disruption Budgets](https://kubernetes.io/docs/tasks/run-application/configure-pdb/)
- [GKE Node Pool Management](https://cloud.google.com/kubernetes-engine/docs/concepts/node-pools)

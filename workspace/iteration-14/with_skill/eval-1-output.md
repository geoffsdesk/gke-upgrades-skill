# GKE Upgrade Plan: Standard Cluster 1.32 → 1.33

## Cluster Overview
- **Cluster**: Standard GKE on Regular release channel
- **Current version**: 1.32
- **Target version**: 1.33
- **Location**: us-central1-a
- **Node pools**: General-purpose, high-memory (Postgres), GPU (ML inference)

## Version Compatibility Check

First, verify 1.33 availability in Regular channel:
```bash
gcloud container get-server-config --zone us-central1-a \
  --format="yaml(channels.REGULAR)"
```

**Expected timeline**: If 1.33 is not yet available in Regular, it typically takes 2-4 weeks after Rapid release. Check the [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule) for current status.

## Recommended Upgrade Strategy

### 1. Control Plane First (Required Order)
- Sequential minor upgrade: 1.32 → 1.33
- Duration: ~10-15 minutes
- Zero workload impact during control plane upgrade

### 2. Node Pool Upgrade Strategy by Pool Type

**General-purpose pool**:
- **Strategy**: Surge upgrade
- **Settings**: `maxSurge=5%` (minimum 1), `maxUnavailable=0`
- **Rationale**: Zero-downtime rolling replacement for stateless workloads

**High-memory pool (Postgres)**:
- **Strategy**: Surge upgrade (conservative)
- **Settings**: `maxSurge=1`, `maxUnavailable=0`
- **Rationale**: Databases need careful handling; let PDBs protect data consistency
- **Special consideration**: Verify Postgres operator compatibility with K8s 1.33 before upgrading

**GPU pool (ML inference)**:
- **Strategy**: Drain-first approach
- **Settings**: `maxSurge=0`, `maxUnavailable=1`
- **Rationale**: GPU reservations typically have no surge capacity; primary lever is `maxUnavailable`
- **Note**: Every GPU upgrade requires pod restart (no live migration)

### 3. Skip-Level Node Pool Upgrades
Since nodes can be up to 2 minor versions behind the control plane, consider skip-level upgrades if any pools are behind:
- If any pool is at 1.31: upgrade directly 1.31 → 1.33 (saves time)
- If at 1.30 or older: upgrade to 1.32 first, then 1.32 → 1.33

## Pre-Upgrade Checklist

```markdown
Pre-Upgrade Checklist
- [ ] Cluster: Standard GKE | Channel: Regular | Zone: us-central1-a
- [ ] Current version: 1.32 | Target version: 1.33

Compatibility
- [ ] 1.33 available in Regular channel (`gcloud container get-server-config --zone us-central1-a --format="yaml(channels.REGULAR)"`)
- [ ] No deprecated API usage (check GKE deprecation insights dashboard)
- [ ] GKE release notes reviewed for breaking changes 1.32 → 1.33
- [ ] Postgres operator compatibility confirmed with K8s 1.33
- [ ] ML inference frameworks tested against 1.33 node image
- [ ] GPU driver compatibility verified (GKE auto-installs matching drivers)

Workload Readiness
- [ ] PDBs configured for Postgres workloads (not overly restrictive)
- [ ] No bare pods — all managed by controllers
- [ ] terminationGracePeriodSeconds adequate for ML inference graceful shutdown
- [ ] Postgres PV backups completed, reclaim policies verified
- [ ] Resource requests/limits set on all containers

Infrastructure
- [ ] Surge settings planned per pool (see strategy above)
- [ ] Sufficient compute quota for general + high-memory surge nodes
- [ ] GPU pool understands drain-first behavior (temporary capacity loss)
- [ ] Maintenance window configured for off-peak hours
- [ ] Consider "no minor or node upgrades" exclusion if precise timing control needed

Ops Readiness
- [ ] Monitoring active, baseline metrics captured
- [ ] Upgrade window communicated to ML and database teams
- [ ] Rollback plan documented
- [ ] On-call team available during upgrade window
```

## Upgrade Runbook

### Phase 1: Control Plane Upgrade

```bash
# Verify current state
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Upgrade control plane
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-central1-a \
  --master \
  --cluster-version 1.33

# Verify (wait ~10-15 min)
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="value(currentMasterVersion)"

# Check system health
kubectl get pods -n kube-system
```

### Phase 2: Node Pool Upgrades (Sequential)

**Step 1: General-purpose pool**
```bash
# Configure surge settings (assuming 20+ node pool → 5% = 1+ nodes)
gcloud container node-pools update general-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade
gcloud container node-pools upgrade general-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33

# Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
```

**Step 2: High-memory pool (Postgres)**
```bash
# Conservative surge for database workloads
gcloud container node-pools update high-memory-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade
gcloud container node-pools upgrade high-memory-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33

# Verify Postgres pods healthy during upgrade
kubectl get pods -n postgres-namespace -w
```

**Step 3: GPU pool (ML inference)**
```bash
# Drain-first approach (no surge capacity assumed)
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1

# Upgrade
gcloud container node-pools upgrade gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33

# Note: GPU workloads will restart, brief inference downtime expected
kubectl get pods -n ml-namespace -w
```

## Timeline Estimates

- **Control plane**: 10-15 minutes
- **General pool** (assuming 10-20 nodes): 30-60 minutes
- **High-memory pool** (assuming 3-5 nodes): 15-30 minutes  
- **GPU pool** (assuming 2-4 nodes): 20-40 minutes
- **Total**: 75-145 minutes (~1.5-2.5 hours)

**Note**: GPU pool upgrade includes brief inference service interruption as pods restart on new nodes.

## Validation Steps

```bash
# Verify all components at 1.33
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="table(currentMasterVersion, nodePools[].name, nodePools[].version)"

# Check workload health
kubectl get deployments -A
kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded
kubectl get statefulsets -A  # Postgres health

# ML inference smoke test
kubectl run test-inference --image=nginx --rm -it --restart=Never --node-selector="cloud.google.com/gke-accelerator=nvidia-tesla-*" -- echo "GPU node accessible"

# Database connectivity test
kubectl exec -it postgres-pod-name -- psql -c "SELECT version();"
```

## Risk Mitigation

**Postgres workload protection**:
- Upgrade high-memory pool during low-traffic window
- Verify database backups before starting
- Monitor connection pools during node replacement

**GPU inference considerations**:
- Brief service interruption expected (pods restart, no live migration)
- Test inference endpoints after upgrade
- GPU driver version may change with 1.33 node image

**General rollback approach**:
- Control plane: Contact GKE support for minor version downgrade
- Node pools: Create new pools at 1.32, migrate workloads, delete upgraded pools

## Post-Upgrade Actions

- [ ] Update internal documentation with new version
- [ ] Verify GPU driver compatibility with ML models
- [ ] Confirm Postgres operator functions normally
- [ ] Update CI/CD pipelines if they reference specific K8s versions
- [ ] Document any GPU driver changes for ML team

Would you like me to adjust any of the surge settings based on your actual node pool sizes, or add specific considerations for your Postgres or ML workloads?
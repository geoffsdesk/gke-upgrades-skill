# GKE Upgrade Plan: Large-Scale LLM Training Cluster

**Cluster:** 512x A3 Mega nodes (4,096 H100 GPUs total)  
**Current:** GKE 1.31 → **Target:** GKE 1.32  
**Workload:** Multi-week LLM training with GPUDirect-TCPXO  

## Critical Constraints for Your Environment

### 1. GPUDirect-TCPXO Compatibility
- **Your current setup is safe**: GPUDirect-TCPXO requires GKE 1.27.7-gke.1121000+, and you're already on 1.31
- **Upgrading to 1.32 maintains compatibility** — no interconnect breaking changes
- **Network validation required**: Post-upgrade, verify high-MTU VPC config and RDMA topology remain intact

### 2. Active Training Protection
Your 2-3 week training runs are incompatible with GKE's default upgrade behavior:
- **Default eviction timeout**: 1 hour during surge upgrades
- **PDB timeout**: GKE respects PDBs for up to 1 hour, then force-drains
- **Node pool upgrades require pod restart** — GPU VMs don't support live migration

## Recommended Upgrade Strategy

### Phase 1: Control Plane Upgrade (Low Risk)
The control plane can be upgraded without affecting running training pods.

```bash
# Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version 1.32.x-gke.XXXX
```

**Impact:** ~15 minutes downtime for kubectl/API access only. Training pods continue running.

### Phase 2: Node Pool Protection During Active Training

Since you have active 2-3 week runs, **do NOT upgrade node pools immediately**. Instead:

```bash
# Block all node pool upgrades during training campaign
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "training-campaign-q1" \
  --add-maintenance-exclusion-start-time "2024-01-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-02-28T23:59:59Z" \
  --add-maintenance-exclusion-scope "no_minor_or_node_upgrades"
```

This prevents auto-upgrades while allowing control plane security patches.

### Phase 3: Node Pool Upgrade During Training Gap

Schedule node pool upgrade between training runs:

#### Option A: Parallel Strategy (Recommended for Training Workloads)
Best when you can tolerate a full cluster restart:

```bash
# 1. Save training checkpoint
# 2. Scale training workload to zero
kubectl scale deployment llm-training --replicas=0

# 3. Configure for parallel upgrade (all nodes at once)
# For GPU pools with no surge capacity available:
gcloud container node-pools update training-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 20

# 4. Trigger upgrade
gcloud container node-pools upgrade training-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --cluster-version 1.32.x-gke.XXXX
```

**Timeline:** ~4-6 hours for 512 nodes (GKE's max parallelism is ~20 nodes simultaneously)

#### Option B: Autoscaled Blue-Green (If Capacity Available)
If you have reservation headroom for 2x capacity:

```bash
gcloud container node-pools update training-pool \
  --cluster CLUSTER_NAME \
  --region REGION \
  --enable-autoscaling \
  --blue-green-settings-autoscale-enabled \
  --blue-green-settings-node-pool-soak-duration 3600s
```

**Timeline:** Longer (6-8 hours) but allows graceful migration

### Phase 4: Post-Upgrade Validation

Critical checks for your environment:

```bash
# 1. Verify all nodes upgraded
kubectl get nodes -o wide | grep -v "1.32"

# 2. Check GPU driver version (may have changed)
kubectl debug node/NODE_NAME -it --image=busybox -- cat /host/proc/driver/nvidia/version

# 3. Validate RDMA/GPUDirect topology
# Run this on a training pod:
kubectl exec -it training-pod -- nvidia-smi topo -m

# 4. Test inter-node communication
# Verify high-bandwidth, low-latency connectivity between nodes
kubectl apply -f nccl-test-job.yaml  # Your NCCL bandwidth test
```

### Phase 5: Compact Placement Verification

A3 Mega machines rely on compact placement for optimal RDMA performance:

```bash
# Verify nodes remain in same placement group
gcloud compute instances list \
  --filter="name~'gke-CLUSTER_NAME-training-pool.*'" \
  --format="table(name,zone,resourcePolicies)"
```

If placement is broken, you may need to recreate the node pool rather than upgrade in-place.

## Timeline & Risk Mitigation

### Recommended Schedule:
1. **Week 1**: Control plane upgrade (15 min maintenance window)
2. **Weeks 2-4**: Continue training with node upgrade exclusion
3. **Training gap**: Node pool upgrade (4-6 hours)
4. **Week 5+**: Resume training on upgraded infrastructure

### Emergency Procedures:

**If upgrade breaks during training run:**
```bash
# 1. Immediate: Apply 30-day exclusion to stop further upgrades
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --add-maintenance-exclusion-name "emergency-stop" \
  --add-maintenance-exclusion-start-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-end-time "$(date -u -d '+30 days' +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-scope "no_upgrades"

# 2. Contact GKE support with cluster details for assistance
```

## Infrastructure Considerations

### GPU Reservation Impact
- **No surge capacity assumption**: A3 Mega reservations are typically exact-fit
- **Upgrade strategy**: Use `maxUnavailable` mode, not surge
- **Capacity planning**: Coordinate with Google Cloud account team if you need temporary expansion

### Network Configuration Preservation
Your high-MTU VPC and RDMA topology must survive the upgrade:
- **Pre-upgrade**: Document current network configuration
- **Post-upgrade**: Validate MTU settings and RDMA connectivity
- **Fallback**: Keep network config backups for rapid restoration

This approach protects your active training while ensuring a safe upgrade path. The key is timing the node pool upgrade during natural training gaps rather than forcing interruption.
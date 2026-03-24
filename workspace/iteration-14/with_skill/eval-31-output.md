# GKE Upgrade Plan for Large-Scale LLM Training Cluster

## Executive Summary

Your 512-node H100 training cluster requires special handling due to:
- **Active 2-3 week training runs** that cannot tolerate mid-job eviction
- **GPUDirect-TCPXO dependency** on specific GKE versions
- **Fixed GPU reservations** with no surge capacity for standard upgrades
- **Massive scale** where standard upgrade timelines don't work

**Recommended approach:** Maintenance exclusions + training gap scheduling with custom upgrade strategy.

---

## Current Environment Assessment

```
Cluster Profile:
- Scale: 512 H100 nodes (A3 Mega, 8 GPUs each = 4,096 GPUs total)
- Current version: GKE 1.31
- Target version: GKE 1.32
- Interconnect: GPUDirect-TCPXO
- Training duration: 2-3 weeks per run
- Node pool type: GPU (fixed reservation, no surge capacity)
```

## GPUDirect-TCPXO Version Compatibility

✅ **Good news:** GPUDirect-TCPXO is supported on both GKE 1.31 and 1.32. The upgrade won't break your interconnect functionality.

⚠️ **Verification required:** Test the exact 1.32 version in a smaller staging cluster first to confirm:
- TCPXO performance characteristics remain stable
- NCCL/CUDA compatibility with the new node image
- Compact placement policies still work correctly
- Custom high-MTU VPC configuration survives upgrade

---

## Upgrade Strategy: Training Gap + Parallel AI Host Maintenance

### Phase 1: Immediate Protection (Apply Now)

**Block auto-upgrades during active training:**

```bash
# Add "no minor or node upgrades" exclusion to prevent disruption
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

This allows control plane security patches but blocks all node disruption until you're ready.

### Phase 2: Training Gap Scheduling

**Wait for natural training completion:**
- Monitor current training job progress
- Identify the next scheduled gap between training runs
- Plan upgrade during this window (typically days to weeks between runs)

### Phase 3: Parallel Upgrade Strategy

For a 512-node cluster, standard surge upgrades would take weeks. Use **parallel AI host maintenance** instead:

**Option A: Full Parallel (Fastest - 4 hours total)**
```bash
# Scale training workloads to zero
kubectl scale deployment/statefulset TRAINING_WORKLOAD --replicas=0

# Apply maintenance label to ALL nodes simultaneously
kubectl label nodes -l cloud.google.com/gke-nodepool=GPU_POOL_NAME \
  cloud.google.com/perform-maintenance=true

# Wait for host maintenance completion (~4 hours)
# All 512 nodes update in parallel batches of ~20-100 nodes

# Restart training workloads
kubectl scale deployment/statefulset TRAINING_WORKLOAD --replicas=ORIGINAL_COUNT
```

**Option B: Rolling by Failure Domain (Slower - maintains partial capacity)**
Only use if you need to maintain some inference capacity during upgrade.

### Phase 4: Validation Checklist

```bash
# Verify all nodes at target version
kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep 1.32

# Confirm GPUDirect-TCPXO functionality
# Run NCCL all-reduce test across nodes:
kubectl create job nccl-test --image=NCCL_TEST_IMAGE

# Verify compact placement maintained
kubectl get pods -o wide | grep training-pod
# Confirm pods are co-located in same placement group

# Test training job startup
# Start a short test training run to verify interconnect performance
```

---

## Timeline and Resource Planning

### Upgrade Duration
- **Control plane:** 10-15 minutes
- **Node pool (parallel):** ~4 hours (all nodes simultaneously)
- **Total maintenance window:** 6 hours (including validation)

### Resource Requirements
- **No additional GPU quota needed** (parallel maintenance, not surge)
- **Checkpoint storage:** Ensure training checkpoints are saved before maintenance
- **Network connectivity:** Verify RDMA/interconnect config survives node recreation

---

## Risk Mitigation

### Backup Plans
1. **Staging validation:** Test 1.32 on a smaller A3 cluster first
2. **Checkpoint recent:** Save training state <1 hour before upgrade
3. **Rollback path:** If issues arise, create new node pool at 1.31 and migrate
4. **Support contact:** Have GKE support case open for 512-node cluster upgrades

### Interconnect Protection
```bash
# Verify high-MTU VPC settings survive upgrade
gcloud compute networks describe NETWORK_NAME
# MTU should remain 8896 for RDMA traffic

# Confirm placement policies after upgrade
gcloud compute resource-policies list --filter="name~compact-placement"
```

---

## Alternative: Blue-Green with New Cluster

If in-place upgrade risks are too high for production training:

**Option:** Deploy a new 1.32 cluster in parallel, migrate training jobs during natural completion, decommission old cluster.

**Pros:** Zero risk to active training, full validation before cutover
**Cons:** Requires 2x quota temporarily, more complex migration

---

## Maintenance Commands

### Pre-Upgrade Checkpoint
```bash
# Ensure training job has recent checkpoint
kubectl exec -it TRAINING_POD -- python save_checkpoint.py

# Verify placement group assignments
kubectl get pods -o json | jq '.items[] | {name: .metadata.name, node: .spec.nodeName}' | head -20
```

### Upgrade Execution
```bash
# 1. Control plane upgrade
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32

# 2. Scale down training workloads
kubectl scale statefulset TRAINING_WORKLOAD --replicas=0

# 3. Parallel node maintenance
kubectl label nodes -l cloud.google.com/gke-nodepool=GPU_POOL_NAME \
  cloud.google.com/perform-maintenance=true

# 4. Monitor progress
watch 'kubectl get nodes -o wide | grep -c 1.32'

# 5. Restart training after all nodes updated
kubectl scale statefulset TRAINING_WORKLOAD --replicas=ORIGINAL_COUNT
```

---

## Post-Upgrade Validation

- [ ] All 512 nodes at GKE 1.32
- [ ] GPUDirect-TCPXO performance baseline maintained
- [ ] Compact placement policies intact
- [ ] Training job restarts successfully from checkpoint
- [ ] NCCL all-reduce performance within 5% of pre-upgrade baseline
- [ ] Multi-week training run validated (start next production run)

**Key Success Metric:** Next 2-3 week training run completes without interconnect issues.

This strategy minimizes risk while handling the unique constraints of your large-scale training environment. The parallel maintenance approach is the only practical way to upgrade 512 GPU nodes in a reasonable timeframe.
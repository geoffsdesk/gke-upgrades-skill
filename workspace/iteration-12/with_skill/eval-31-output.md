# GKE 1.31→1.32 Upgrade Plan for Large-Scale LLM Training Cluster

## Executive Summary

Your 512-node H100 training cluster requires a **staged upgrade approach** that protects active training runs and preserves GPUDirect-TCPXO interconnect. The key is using **maintenance exclusions** to block node upgrades during training campaigns while allowing control plane security patches.

## Current Environment Assessment

- **Cluster**: 512 H100 nodes (A3 Mega, 4,096 GPUs total)
- **Interconnect**: GPUDirect-TCPXO (requires GKE 1.27.7-gke.1121000+)
- **Training duration**: 2-3 weeks per campaign
- **Current version**: GKE 1.31 → Target: 1.32
- **Risk factors**: GPU VMs don't support live migration, RDMA topology sensitivity, limited surge capacity

## Upgrade Strategy

### Phase 1: Control Plane Upgrade (Safe During Training)

The control plane can be upgraded safely during active training runs. It doesn't affect running pods or GPU interconnect.

```bash
# Upgrade control plane only
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.X-gke.XXXXX
```

**Timeline**: ~15-20 minutes, zero training impact.

### Phase 2: Node Pool Protection During Training

Apply maintenance exclusions to prevent automatic node upgrades while training is active:

```bash
# Block node upgrades during training campaign (allows CP patches)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-campaign-Q1-2024" \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time "2024-04-01T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

**Key benefit**: Control plane receives security patches, nodes stay stable for training.

### Phase 3: Node Pool Upgrade (Between Training Runs)

Schedule node upgrades during planned gaps between training campaigns using the **parallel strategy** for maximum efficiency:

#### Pre-Upgrade Preparation

```bash
# 1. Verify training job completion and checkpoint saved
kubectl get pods -A | grep training

# 2. Scale training workloads to zero
kubectl scale deployment training-job --replicas=0

# 3. Remove maintenance exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "training-campaign-Q1-2024"
```

#### GPU Node Pool Upgrade Configuration

For your H100 cluster, use **maxUnavailable** as the primary lever (surge capacity for H100s is extremely limited):

```bash
# Configure for parallel upgrade (max GKE concurrency)
gcloud container node-pools update h100-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 20
```

**Rationale**: 
- `maxSurge=0`: No extra H100 capacity needed
- `maxUnavailable=20`: Matches GKE's ~20 node upgrade parallelism limit
- **Estimated duration**: 512 nodes ÷ 20 parallel = ~26 batches × 15min = **6-8 hours total**

#### Execute Node Upgrade

```bash
# Upgrade node pool
gcloud container node-pools upgrade h100-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.X-gke.XXXXX

# Monitor progress
watch 'kubectl get nodes -o wide | grep -E "Ready|NotReady|VERSION"'
```

### Phase 4: Post-Upgrade Validation

Critical checks for your GPU interconnect environment:

```bash
# 1. Verify all nodes at target version
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE

# 2. Check GPU driver version (auto-installed by GKE)
kubectl describe nodes | grep -A 10 "nvidia.com/gpu"

# 3. Verify RDMA/GPUDirect-TCPXO functionality
# Test inter-node communication with your training framework

# 4. Validate compact placement policy preserved
# Check that nodes are still co-located as expected

# 5. Test training workload startup
kubectl scale deployment training-job --replicas=1
# Verify successful pod scheduling and GPU allocation
```

## GPUDirect-TCPXO Considerations

**Version compatibility**: Both GKE 1.31 and 1.32 support GPUDirect-TCPXO for A3 Mega instances. The upgrade should preserve interconnect functionality.

**Critical risks to test**:
- **GPU driver version change**: GKE may install a different CUDA version
- **Network MTU preservation**: Verify high-MTU VPC config survives upgrade  
- **Compact placement**: Confirm replacement nodes maintain physical topology

**Pre-production testing**: Test the exact upgrade path (1.31→1.32) on a smaller staging cluster with the same A3 Mega + GPUDirect-TCPXO setup.

## Timeline & Scheduling

| Phase | Duration | Training Impact | When to Execute |
|-------|----------|-----------------|-----------------|
| Control plane upgrade | 15-20 min | **None** | Anytime |
| Maintenance exclusion setup | 2 min | **None** | Before/during training |
| Node pool upgrade | 6-8 hours | **Full cluster down** | Between training campaigns only |
| Validation | 1-2 hours | Partial (testing) | After node upgrade |

## Risk Mitigation

### Training Run Protection
```bash
# Set persistent exclusion that tracks End of Support
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-until-end-of-support \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

This exclusion automatically renews when you upgrade to 1.32, protecting future training runs.

### Rollback Plan
- **Control plane**: Contact GKE support for minor version rollback (not customer-initiated)
- **Node pools**: Create new pool at 1.31, migrate workloads, delete upgraded pool
- **Training checkpoints**: Ensure comprehensive checkpointing before upgrade window

### Emergency Scenarios
```bash
# If upgrade stalls or fails, cancel operation
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE
# Contact GKE support with operation ID for large GPU clusters
```

## Recommended Execution Window

1. **End current training campaign** - allow natural completion
2. **Save comprehensive checkpoint** 
3. **Execute control plane upgrade** (can be done immediately)
4. **Schedule 8-hour maintenance window** for node upgrade
5. **Validate interconnect** thoroughly before starting next campaign
6. **Begin next training run** once validation passes

This approach minimizes risk to your multi-million dollar training campaigns while keeping the cluster updated and secure.
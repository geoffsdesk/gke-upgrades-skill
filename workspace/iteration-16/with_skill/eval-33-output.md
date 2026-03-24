# GKE Upgrade Plan: ML Inference Platform (1.31 → 1.32)

## Executive Summary
- **Cluster**: Standard cluster with mixed GPU workloads (inference + fine-tuning)
- **Upgrade path**: 1.31 → 1.32 (single minor version jump)
- **Key challenge**: GPU nodes don't support live migration; every upgrade requires pod restart
- **Strategy**: Autoscaled blue-green for inference pools + fine-tuning job protection

## Version Compatibility Assessment

✅ **Compatible upgrade**: 1.31 → 1.32 is a supported single minor version upgrade
- Check target version availability: `gcloud container get-server-config --zone ZONE --format="yaml(channels)"`
- Review [GKE 1.32 release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes) for GPU/ML-specific changes
- **GPU driver coupling**: GKE will auto-install drivers matching 1.32 - verify CUDA compatibility with your inference frameworks

## Pre-Upgrade: Fine-Tuning Job Protection

**Critical**: Fine-tuning jobs (4-8 hours) will be force-evicted after GKE's 1-hour PDB timeout during standard surge upgrades.

```bash
# Apply maintenance exclusion to A100 pool BEFORE upgrading
gcloud container node-pools update a100-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "fine-tuning-protection" \
  --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-end-time $(date -u -d '+7 days' +%Y-%m-%dT%H:%M:%SZ) \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

This blocks auto-upgrades on the A100 pool while allowing you to upgrade it manually during planned gaps.

## Upgrade Strategy: Autoscaled Blue-Green

For GPU inference workloads, **autoscaled blue-green** is optimal because:
- Maintains serving capacity throughout upgrade (no inference downtime)
- Scales down old nodes as workloads migrate (cost-efficient vs standard blue-green)
- Respects longer graceful termination if needed
- Works well with autoscaling workloads

### L4 Inference Pool (Upgrade First)

```bash
# Configure autoscaled blue-green for L4 pool
gcloud container node-pools update l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 10 \
  --total-max-nodes 250 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s

# Upgrade L4 pool
gcloud container node-pools upgrade l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.X-gke.XXXX
```

**Parameters explained**:
- `blue-green-initial-node-percentage=0.25`: Start with 25% of nodes in the new (green) pool
- `blue-green-full-batch-timeout=3600s`: Wait up to 1 hour for green pool readiness
- Green pool scales up as traffic shifts; blue pool scales down automatically

### A100 Fine-Tuning Pool (Upgrade During Job Gap)

**Wait for fine-tuning jobs to complete naturally**, then:

```bash
# Verify no running fine-tuning jobs
kubectl get pods -n NAMESPACE -l app=fine-tuning --field-selector=status.phase=Running

# Remove maintenance exclusion
gcloud container node-pools update a100-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "fine-tuning-protection"

# Configure autoscaled blue-green
gcloud container node-pools update a100-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 5 \
  --total-max-nodes 120 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.3,blue-green-full-batch-timeout=1800s

# Upgrade A100 pool
gcloud container node-pools upgrade a100-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.X-gke.XXXX
```

## Execution Timeline

### Phase 1: Control Plane (30 minutes)
```bash
# Regional clusters remain highly available during CP upgrade
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.X-gke.XXXX

# Verify
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

### Phase 2: L4 Pool (1-2 hours)
- Autoscaled blue-green maintains inference capacity
- Monitor inference latency during migration
- Green pool scales up as blue pool drains

### Phase 3: A100 Pool (2-3 hours) 
- Execute during scheduled fine-tuning gap
- Shorter timeout (30min) since no long-running jobs

## Pre-Flight Checklist

```markdown
Infrastructure
- [ ] Sufficient GPU quota for blue-green (verify reservation headroom)
- [ ] L4 pool autoscaling: min=10, max=250
- [ ] A100 pool autoscaling: min=5, max=120
- [ ] Maintenance exclusion applied to A100 pool
- [ ] Current fine-tuning jobs identified and tracked

Workload Readiness
- [ ] PDBs configured for inference services (e.g., `minAvailable: 50%`)
- [ ] No bare pods on GPU nodes
- [ ] Inference framework compatibility with CUDA version in 1.32 verified
- [ ] Fine-tuning jobs have checkpointing enabled
- [ ] Monitoring baselines captured (inference latency P95, throughput)

GPU-Specific
- [ ] GPU driver compatibility confirmed for 1.32
- [ ] CUDA version change impacts assessed
- [ ] GPUDirect/networking requirements verified (if using TCPX)
```

## Monitoring During Upgrade

```bash
# Track node versions across pools
watch 'kubectl get nodes -L cloud.google.com/gke-nodepool,kubernetes.io/arch -o wide'

# Monitor inference pod distribution
kubectl get pods -n NAMESPACE -o wide -L app=inference

# Check autoscaler events
kubectl get events -n kube-system --field-selector involvedObject.name=cluster-autoscaler

# GPU utilization
kubectl top nodes --selector='cloud.google.com/gke-accelerator'
```

## Risk Mitigation

**Inference availability**: Blue-green maintains capacity; inference traffic continues on blue nodes until green nodes are ready and validated.

**Fine-tuning jobs**: Maintenance exclusion prevents forced eviction. Upgrade only during natural job gaps.

**Cost optimization**: Autoscaled blue-green scales down blue pool as green scales up - no sustained 2x cost like standard blue-green.

**Quick rollback**: During blue-green upgrade, you can rollback by uncordoning the blue pool if issues arise with green nodes.

## Success Criteria

- [ ] All nodes at 1.32.X-gke.XXXX
- [ ] Inference latency P95 within 10% of baseline
- [ ] Inference throughput maintained
- [ ] Fine-tuning jobs can start successfully on upgraded A100 nodes
- [ ] GPU utilization metrics flowing correctly
- [ ] No CrashLoopBackOff or GPU allocation failures

## Rollback Plan

If critical issues arise:
```bash
# During blue-green upgrade - uncordon blue pool
kubectl uncordon -l cloud.google.com/gke-nodepool=POOL_NAME

# Post-upgrade - create new pool at 1.31 and migrate
gcloud container node-pools create POOL_NAME-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.X-gke.XXXX
```

**Estimated total duration**: 4-6 hours including validation time.
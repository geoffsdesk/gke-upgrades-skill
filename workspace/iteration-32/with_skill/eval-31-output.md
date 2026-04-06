# GKE Upgrade Plan for Large-Scale LLM Training Cluster

## Cluster Profile
- **Cluster**: 512 H100 nodes (A3 Mega, 4,096 total GPUs)
- **Workload**: 2-3 week LLM training runs
- **Network**: GPUDirect-TCPXO interconnect
- **Current**: GKE 1.31 → **Target**: GKE 1.32

## Executive Summary

For your disruption-intolerant LLM training workload, we'll use **staged upgrades with maintenance exclusions** to protect active training while allowing security patches:

1. **Control plane upgrade during training gap** (5-10 min downtime)
2. **Node pool upgrade during planned training restart** using GPU-optimized settings
3. **GPUDirect-TCPXO compatibility validation** before production

## Version Compatibility & GPUDirect

✅ **Good news**: GPUDirect-TCPXO is fully supported in GKE 1.32. Your interconnect should survive the upgrade.

⚠️ **Critical validation required**: GPU driver version changes with GKE upgrades can affect CUDA compatibility. Create a staging node pool with GKE 1.32 first to validate:

```bash
# Create staging validation pool (2-4 nodes)
gcloud container node-pools create staging-132-validation \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxxx \
  --machine-type a3-megagpu-8g \
  --num-nodes 2 \
  --placement-type COMPACT \
  --placement-policy-name PLACEMENT_POLICY_NAME

# Test GPUDirect-TCPXO connectivity
kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: tcpxo-test
spec:
  nodeSelector:
    cloud.google.com/gke-nodepool: staging-132-validation
  containers:
  - name: test
    image: gcr.io/PROJECT/training-image
    # Run your NCCL/TCPXO connectivity tests here
EOF
```

## Upgrade Strategy: Maintenance Exclusions + Controlled Timing

### Phase 1: Control Plane Upgrade (Safe During Training)

Control plane upgrades don't restart nodes or pods - safe to do during active training:

```bash
# Apply "no node upgrades" exclusion to protect training nodes
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "protect-training-nodes" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support

# Upgrade control plane (5-10 minutes, no pod restarts)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.xxxx

# Verify control plane upgraded, nodes protected
gcloud container clusters describe CLUSTER_NAME --zone ZONE \
  --format="table(currentMasterVersion, nodePools[].version)"
```

**Result**: Control plane at 1.32, nodes stay at 1.31, training continues uninterrupted.

### Phase 2: Node Pool Upgrade (During Training Restart Window)

Wait for your next planned training restart (checkpoint save), then upgrade nodes:

**Pre-upgrade preparation:**
```bash
# Checkpoint and stop training workloads
kubectl scale statefulset training-job --replicas=0

# Verify all training pods terminated
kubectl get pods -l app=training-job

# Configure GPU-optimized upgrade settings
gcloud container node-pools update gpu-training-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 4
```

**Why `maxUnavailable=4, maxSurge=0`**: 
- A3 Mega reservations typically have **no surge capacity** for H100s
- `maxUnavailable=4` drains 4 nodes at a time (no extra GPUs needed)
- With GKE's ~20 node parallelism limit, 512 nodes = ~26 batches
- **Estimated duration**: 4-6 hours for full pool upgrade

**Execute node upgrade:**
```bash
# Remove node upgrade exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "protect-training-nodes"

# Trigger node pool upgrade
gcloud container node-pools upgrade gpu-training-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxxx

# Monitor progress (expect 4-6 hours)
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool | grep -E "Ready|NotReady"'
```

## GPU-Specific Considerations

### Compact Placement Preservation
Verify replacement nodes maintain your RDMA topology:
```bash
# Check placement policy after first batch
kubectl get nodes -o yaml | grep -A 10 "cloud.google.com/placement-group"
```

### Driver Version Validation
New GKE version = new GPU driver. Validate compatibility:
```bash
# Check driver version on upgraded nodes
kubectl debug node/NODE_NAME -it --image=ubuntu -- nvidia-smi

# Test CUDA version compatibility with your training framework
kubectl run cuda-test --image=gcr.io/PROJECT/training-image --rm -it \
  --overrides='{"spec":{"nodeSelector":{"cloud.google.com/gke-nodepool":"gpu-training-pool"}}}' \
  -- python -c "import torch; print(torch.cuda.is_available(), torch.version.cuda)"
```

## Alternative: AI Host Maintenance Strategy

If you need maximum control over node replacement timing, consider GKE's AI host maintenance pattern:

```bash
# Label all nodes for parallel maintenance (during training gap only)
kubectl label nodes --selector="cloud.google.com/gke-nodepool=gpu-training-pool" \
  cloud.google.com/perform-maintenance=true

# This triggers ~4 hour host maintenance per node
# All 512 nodes get maintenance simultaneously
```

**Use this approach when:**
- You have a specific 4-6 hour training restart window
- You want all nodes refreshed at once vs rolling
- You're comfortable with cluster-wide maintenance

## Validation & Restart Checklist

```markdown
Post-Upgrade Validation
- [ ] All nodes at GKE 1.32: `kubectl get nodes -L kubernetes.io/version`
- [ ] GPU driver loaded: `kubectl get pods -n kube-system -l name=nvidia-device-plugin-daemonset`
- [ ] TCPXO topology preserved: Test NCCL allreduce across nodes
- [ ] Placement groups intact: Verify physical node co-location
- [ ] Training pod resource allocation: `nvidia-smi` shows expected GPU counts
- [ ] Resume training from checkpoint: Validate loss continues from last checkpoint
```

## Risk Mitigation

**Training Protection:**
- Maintenance exclusions prevent accidental auto-upgrades during training
- Control plane upgrade doesn't restart any pods/nodes
- Node upgrade only happens during your planned restart window

**Rollback Plan:**
- If 1.32 has critical issues: create new pool at 1.31, migrate workloads
- Control plane minor version rollback requires GKE support engagement
- Keep 1.31 training images available as fallback

**Communication:**
- Notify training team of 4-6 hour upgrade window
- Have on-call engineer available during node pool upgrade
- Test full training restart procedure in staging first

## Timeline

**Week 1**: Stage validation pool, test GPUDirect-TCPXO + CUDA compatibility
**Week 2**: Upgrade control plane (5 min), apply node exclusions  
**Week 3+**: During next training restart window, execute node pool upgrade (4-6 hours)

This approach minimizes risk while ensuring your LLM training infrastructure stays current and secure. The key insight is that maintenance exclusions let you control **exactly when** disruptive changes happen, rather than avoiding upgrades entirely.
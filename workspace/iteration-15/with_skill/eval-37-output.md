# GKE AI/ML Platform Upgrade Plan: 1.31 → 1.32

**Fleet Overview:** 5,000 nodes across mixed AI/ML workloads  
**Target:** Kubernetes 1.31 → 1.32  
**Priority:** Training continuity (H100) > Inference availability (A100) > Dev velocity (T4) > Service reliability (CPU)

## Pre-Upgrade Assessment

### Version Compatibility Check
```bash
# Verify 1.32 availability in your release channel
gcloud container get-server-config --zone ZONE --format="yaml(channels)"

# Check current cluster versions and channels
for cluster in training-h100 inference-a100 dev-t4 services-cpu; do
  gcloud container clusters describe $cluster --zone ZONE \
    --format="table(name,currentMasterVersion,releaseChannel.channel)"
done

# Critical: Check for deprecated API usage across all clusters
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
```

### GPU Driver Compatibility Verification
- **H100 Training:** GKE 1.32 ships with CUDA 12.x — verify PyTorch/JAX compatibility in staging
- **A100 Inference:** Test inference framework compatibility with new driver version
- **T4 Dev:** Lower impact but verify development toolchain compatibility

## Phase 1: CPU Services Cluster (Lowest Risk)
**Timeline:** Week 1 | **Duration:** 2-3 days | **Nodes:** 1,000

```bash
# Configure maintenance window (off-peak)
gcloud container clusters update services-cpu \
  --zone ZONE \
  --maintenance-window-start 2024-12-15T02:00:00Z \
  --maintenance-window-end 2024-12-15T06:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"

# CPU nodes: Use percentage-based surge for faster upgrades
gcloud container node-pools update cpu-services-pool \
  --cluster services-cpu \
  --zone ZONE \
  --max-surge-upgrade 25 \
  --max-unavailable-upgrade 0
  # 25 nodes = 2.5% of 1,000-node pool, well within ~20 node parallelism limit

# Upgrade control plane first
gcloud container clusters upgrade services-cpu \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.latest

# After CP upgrade, upgrade node pools
gcloud container node-pools upgrade cpu-services-pool \
  --cluster services-cpu \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**Validation:** Service mesh, ingress controllers, monitoring stack all functional before proceeding.

## Phase 2: T4 Development Cluster
**Timeline:** Week 2 | **Duration:** 3-4 days | **Nodes:** 500

```bash
# T4 nodes: Mixed surge/drain strategy
gcloud container node-pools update t4-dev-pool \
  --cluster dev-t4 \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 2
  # No surge capacity assumed for GPU nodes; drain 2 nodes at a time

# Control plane upgrade
gcloud container clusters upgrade dev-t4 \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.latest

# Node pool upgrade
gcloud container node-pools upgrade t4-dev-pool \
  --cluster dev-t4 \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**Validation:** Development workflows, Jupyter environments, and model experimentation pipelines working. This serves as final GPU driver compatibility validation before production inference.

## Phase 3: A100 Inference Cluster (Business Critical)
**Timeline:** Week 3 | **Duration:** 5-7 days | **Nodes:** 1,500

**Strategy:** Rolling maintenance with capacity preservation using maxUnavailable

```bash
# Set maintenance exclusion during peak traffic hours
gcloud container clusters update inference-a100 \
  --zone ZONE \
  --add-maintenance-exclusion-name "peak-traffic-exclusion" \
  --add-maintenance-exclusion-start-time 2024-12-22T14:00:00Z \
  --add-maintenance-exclusion-end-time 2024-12-22T22:00:00Z \
  --add-maintenance-exclusion-scope no_upgrades

# Conservative A100 upgrade: maxUnavailable is the primary lever
gcloud container node-pools update a100-inference-pool \
  --cluster inference-a100 \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 3
  # Drain 3 A100 nodes at a time; ~500 batches total with ~20 node parallelism
  # Expect 5-7 days total upgrade time for 1,500 nodes

# Control plane upgrade (off-peak)
gcloud container clusters upgrade inference-a100 \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.latest

# Node pool upgrade with extended monitoring
gcloud container node-pools upgrade a100-inference-pool \
  --cluster inference-a100 \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**Monitoring During A100 Upgrade:**
```bash
# Track inference capacity and latency
watch 'kubectl top nodes | grep a100'
# Monitor request success rates
curl -s "http://monitoring-endpoint/metrics" | grep inference_success_rate
```

**Rollback Plan for A100:** If inference latency degrades >20% or error rates spike, pause upgrade and create new pool at 1.31 for immediate capacity recovery.

## Phase 4: H100 Training Cluster (Highest Value)
**Timeline:** Week 4-5 | **Duration:** 7-10 days | **Nodes:** 2,000

**Strategy:** AI Host Maintenance with parallel strategy during training gaps

### Pre-Training Checkpoint
```bash
# Ensure all training jobs checkpoint before upgrade window
kubectl patch deployment training-coordinator \
  -p '{"spec":{"template":{"spec":{"containers":[{"name":"coordinator","env":[{"name":"FORCE_CHECKPOINT","value":"true"}]}]}}}}'

# Verify checkpoints saved
kubectl logs -l app=training-coordinator | grep "checkpoint_saved"
```

### Maintenance Exclusion Strategy
```bash
# Block upgrades during active training campaigns
gcloud container clusters update training-h100 \
  --zone ZONE \
  --add-maintenance-exclusion-name "training-campaign-jan" \
  --add-maintenance-exclusion-start-time 2024-01-02T00:00:00Z \
  --add-maintenance-exclusion-end-time 2024-01-08T00:00:00Z \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

### H100 Upgrade During Training Gap
```bash
# Scale training workloads to zero during upgrade
kubectl scale deployment training-workload --replicas=0
kubectl scale statefulset distributed-training --replicas=0

# H100 parallel maintenance strategy (all nodes updated simultaneously)
# Apply maintenance label to ALL H100 nodes at once
kubectl label nodes -l node-type=h100 cloud.google.com/perform-maintenance=true

# Monitor host maintenance progress (~4 hours per update)
watch 'kubectl get nodes -l node-type=h100 -o wide'

# Control plane upgrade first (during host maintenance window)
gcloud container clusters upgrade training-h100 \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.latest
```

**Critical H100 Considerations:**
- **Compact Placement:** Verify surge/replacement nodes maintain RDMA topology
- **GPUDirect-TCPX:** Confirm 1.32 supports current GPUDirect version
- **Multi-host training:** All pods on a slice restart simultaneously — plan accordingly

### Post-Upgrade Training Validation
```bash
# Restart training workloads
kubectl scale deployment training-workload --replicas=ORIGINAL_COUNT
kubectl scale statefulset distributed-training --replicas=ORIGINAL_COUNT

# Verify GPU interconnect and RDMA
kubectl exec -it training-pod -- nvidia-smi topo -m
kubectl exec -it training-pod -- ib_write_bw  # RDMA bandwidth test
```

## Cross-Cutting Upgrade Controls

### Fleet-wide Maintenance Windows
```bash
# Stagger windows across clusters to prevent simultaneous issues
# Services: Sunday 2-6 AM
# Dev: Tuesday 2-6 AM  
# Inference: Wednesday 2-6 AM
# Training: Saturday 2-6 AM (during training gaps only)
```

### Monitoring & Alerting
```bash
# Set up upgrade progress monitoring
gcloud logging sinks create gke-upgrade-sink \
  bigquery.googleapis.com/projects/PROJECT/datasets/gke_upgrades \
  --log-filter='resource.type="gke_cluster" AND protoPayload.methodName="google.container.v1.ClusterManager.UpdateCluster"'

# Create upgrade failure alerts
gcloud alpha monitoring policies create --policy-from-file=upgrade-alerts.yaml
```

### Rollout Sequence Constraints
**Important:** This fleet uses different node types but should be on the same release channel. Do NOT use rollout sequencing across different channels (won't work). Instead, use the phased manual approach above with maintenance exclusions to control timing.

## Emergency Procedures

### Critical Training Job Protection
If an H100 training run cannot be interrupted:
```bash
# Emergency "no upgrades" exclusion (overrides everything)
gcloud container clusters update training-h100 \
  --zone ZONE \
  --add-maintenance-exclusion-name "emergency-freeze" \
  --add-maintenance-exclusion-start-time NOW \
  --add-maintenance-exclusion-end-time END_OF_TRAINING_RUN \
  --add-maintenance-exclusion-scope no_upgrades
```

### Inference Capacity Emergency
If A100 upgrade causes inference capacity crisis:
```bash
# Create emergency node pool at old version
gcloud container node-pools create a100-emergency-pool \
  --cluster inference-a100 \
  --zone ZONE \
  --cluster-version 1.31.x-gke.current \
  --num-nodes 100 \
  --machine-type a2-ultragpu-1g \
  --accelerator type=nvidia-tesla-a100,count=1

# Scale critical inference workloads to emergency pool
kubectl patch deployment critical-inference \
  -p '{"spec":{"template":{"spec":{"nodeSelector":{"cloud.google.com/gke-nodepool":"a100-emergency-pool"}}}}}'
```

## Success Criteria & Validation

### Per-Phase Gates
- **Services:** All ingress healthy, monitoring gaps <5 minutes
- **Dev:** Jupyter/notebooks functional, model training experiments successful  
- **Inference:** Latency within 10% of baseline, error rate <0.1%
- **Training:** Multi-node training jobs complete successfully, GPU interconnect verified

### Fleet-wide Completion
```bash
# Verify all clusters at 1.32
for cluster in training-h100 inference-a100 dev-t4 services-cpu; do
  gcloud container clusters describe $cluster --zone ZONE \
    --format="value(currentMasterVersion,nodePools[].version)" | \
    grep -q "1.32" && echo "$cluster: ✓ 1.32" || echo "$cluster: ✗ Mixed versions"
done
```

**Total Timeline:** 4-5 weeks with built-in buffers for training campaign coordination and inference validation.

**Risk Mitigation:** Each phase validates the next — services validates basic 1.32 compatibility, T4 validates GPU drivers, A100 validates inference stability, H100 completes during planned training gaps.
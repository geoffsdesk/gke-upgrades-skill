# GKE Upgrade Plan: ML Inference Platform (1.31 → 1.32)

## Cluster Overview
- **Mode:** GKE Standard
- **Current version:** 1.31
- **Target version:** 1.32
- **Workload type:** GPU inference (latency-sensitive) + fine-tuning (4-8hr jobs)
- **Node pools:** 
  - L4 pool: 200 nodes (inference, auto-scaling)
  - A100 pool: 100 nodes (inference + fine-tuning)

## Upgrade Strategy Summary

**Recommended approach:** Sequential control plane → node pool upgrades with GPU-specific surge settings and fine-tuning job protection.

**Key considerations:**
- GPU VMs don't support live migration — every upgrade requires pod restart
- L4 inference needs rapid recovery to minimize latency impact
- A100 fine-tuning jobs need protection from mid-job eviction
- Auto-scaling interaction during upgrade

---

## Version Compatibility & Path

### Pre-flight Checks
```bash
# Verify 1.32 availability in your release channel
gcloud container get-server-config --zone ZONE --format="yaml(channels)"

# Check current cluster state
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# GPU driver compatibility check
# GKE 1.32 will auto-install drivers matching the target version
# Test in staging first to verify CUDA version compatibility
```

### Upgrade Path
- **Control plane:** 1.31 → 1.32 (single step supported)
- **Node pools:** Can skip-level upgrade directly to 1.32
- **Required sequence:** Control plane first, then node pools

---

## Node Pool Upgrade Strategy

### L4 Inference Pool (Latency-Critical)
**Strategy:** Surge upgrade with aggressive parallelism

```bash
# Configure surge settings for fast recovery
gcloud container node-pools update l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 10 \
  --max-unavailable-upgrade 0
```

**Rationale:**
- `maxSurge=10`: Creates 10 replacement L4 nodes simultaneously for faster recovery
- `maxUnavailable=0`: No capacity dip — inference traffic can immediately move to new nodes
- **Critical:** Verify you have L4 surge quota for 10 additional nodes before proceeding

**Alternative if surge quota unavailable:**
```bash
# Conservative approach using maxUnavailable
gcloud container node-pools update l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 3
```

### A100 Fine-tuning Pool (Job-Sensitive)
**Strategy:** Conservative surge + fine-tuning job protection

```bash
# Conservative surge settings
gcloud container node-pools update a100-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

**Rationale:**
- `maxUnavailable=1`: Only 1 A100 node upgrading at a time
- A100 machines typically have fixed reservations with no surge capacity
- Slower upgrade but protects running fine-tuning jobs

---

## Fine-tuning Job Protection

### Option 1: Maintenance Exclusion (Recommended)
```bash
# Block node pool upgrades during active fine-tuning campaigns
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "fine-tuning-campaign" \
  --add-maintenance-exclusion-start-time "2024-02-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-02-22T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

This allows control plane security patches while blocking disruptive node upgrades.

### Option 2: Job-Aware Upgrade Timing
```bash
# Check for running fine-tuning jobs
kubectl get pods -n fine-tuning --field-selector=status.phase=Running

# If jobs are running, cordon A100 nodes and wait for natural completion
kubectl cordon -l cloud.google.com/gke-nodepool=a100-pool

# Monitor job completion, then upgrade empty pool
kubectl get pods -n fine-tuning --watch
```

### PDB Configuration
```yaml
# Protect fine-tuning jobs from eviction
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: fine-tuning-pdb
  namespace: fine-tuning
spec:
  minAvailable: "100%"  # Prevent any eviction
  selector:
    matchLabels:
      workload-type: fine-tuning
```

**Important:** Remove or relax this PDB after fine-tuning jobs complete, or the A100 upgrade will be blocked.

---

## Auto-scaling Considerations

### Before Upgrade
```bash
# Review current auto-scaling policies
kubectl describe hpa -A
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="yaml(nodePools[].autoscaling)"

# Consider temporarily reducing max node counts to control upgrade scope
gcloud container node-pools update l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-nodes 150  # Reduce from normal max during upgrade
```

### During Upgrade
- Cluster autoscaler can only scale one node pool at a time
- New traffic spikes during upgrade will create new nodes at the target version
- Monitor that inference latency SLAs are maintained as nodes cycle

### After Upgrade
```bash
# Restore normal auto-scaling limits
gcloud container node-pools update l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-nodes 300  # Restore normal max
```

---

## Step-by-Step Runbook

### Phase 1: Pre-flight (30 minutes)

```bash
# 1. Verify cluster health
kubectl get nodes | grep -E "NotReady|SchedulingDisabled"
kubectl get pods -A | grep -v Running | grep -v Completed

# 2. Check for active fine-tuning jobs
kubectl get pods -n fine-tuning --field-selector=status.phase=Running
# If jobs are running, apply maintenance exclusion or wait for completion

# 3. Capture baseline metrics
# Note current inference latency, throughput, error rates

# 4. Verify GPU driver compatibility in staging cluster first
# Test inference workloads on 1.32 to confirm CUDA/driver compatibility
```

### Phase 2: Control Plane Upgrade (15 minutes)

```bash
# Upgrade control plane
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version "1.32.x-gke.xxxx"  # Use specific patch version

# Verify control plane health
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"

kubectl get pods -n kube-system
```

### Phase 3: L4 Inference Pool Upgrade (45-60 minutes)

```bash
# Configure aggressive surge (if quota available)
gcloud container node-pools update l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 10 \
  --max-unavailable-upgrade 0

# Start upgrade
gcloud container node-pools upgrade l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version "1.32.x-gke.xxxx"

# Monitor progress and inference latency
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=l4-inference-pool'
# Monitor your inference latency dashboards during this phase
```

### Phase 4: A100 Pool Upgrade (2-3 hours)

```bash
# Wait for any fine-tuning jobs to complete naturally
kubectl get pods -n fine-tuning --field-selector=status.phase=Running

# Configure conservative upgrade
gcloud container node-pools update a100-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1

# Start upgrade
gcloud container node-pools upgrade a100-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version "1.32.x-gke.xxxx"

# Monitor (will be slow - 1 node at a time)
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=a100-pool'
```

### Phase 5: Validation (15 minutes)

```bash
# Verify all nodes upgraded
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE

# Check workload health
kubectl get pods -A | grep -v Running | grep -v Completed
kubectl get hpa -A  # Verify auto-scaling active

# Test inference endpoints
# Run your standard inference health checks
# Verify latency is back to baseline levels

# Check GPU driver version
kubectl get nodes -l accelerator=nvidia-l4 -o yaml | grep -A5 "nvidia.com/gpu"
```

---

## Rollback Plan

**Control plane:** Contact GKE support for minor version rollback (not customer-initiated).

**Node pools:** Create new pools at 1.31 and migrate workloads:

```bash
# Create rollback L4 pool
gcloud container node-pools create l4-inference-pool-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version "1.31.x-gke.xxxx" \
  --machine-type g2-standard-24 \
  --accelerator type=nvidia-l4,count=1 \
  --num-nodes 50 \
  --enable-autoscaling \
  --min-nodes 0 \
  --max-nodes 300

# Cordon upgraded pool and wait for traffic to migrate
kubectl cordon -l cloud.google.com/gke-nodepool=l4-inference-pool
```

---

## Timeline & Maintenance Window

**Total estimated duration:** 3-4 hours
- Control plane: 15 minutes
- L4 pool: 45-60 minutes  
- A100 pool: 2-3 hours (conservative 1-node-at-a-time)
- Validation: 15 minutes

**Recommended window:** Weekend or low-traffic period, 4-hour maintenance window.

---

## Monitoring During Upgrade

### Key Metrics to Watch
- **Inference latency:** p50, p95, p99 response times
- **Throughput:** Requests per second, successful responses
- **GPU utilization:** Ensure new nodes are receiving traffic
- **Auto-scaling events:** New node creation during traffic spikes
- **Fine-tuning job health:** Job completion rates, checkpoint frequency

### Alerts to Configure
- Inference latency exceeds baseline + 50%
- Error rate > 1% for inference workloads
- Any fine-tuning jobs in CrashLoopBackOff
- Node pool upgrade stuck for > 30 minutes

This plan prioritizes your inference SLAs while protecting long-running fine-tuning jobs. The key is using different surge strategies per pool type and timing the A100 upgrade around job completion cycles.
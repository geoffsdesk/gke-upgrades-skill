# GKE Upgrade Plan: 1.32 → 1.33

**Cluster:** Standard GKE on Regular release channel  
**Current version:** 1.32  
**Target version:** 1.33  
**Location:** us-central1-a (zonal)  
**Deadline:** End of quarter  

## Executive Summary

This is a **minor version upgrade** requiring sequential control plane upgrade followed by node pool upgrades. Each node pool has different upgrade considerations:
- **General-purpose:** Standard surge upgrade
- **High-memory (Postgres):** Conservative settings with PDB protection
- **GPU (ML inference):** Autoscaled blue-green strategy to minimize inference downtime

**Estimated duration:** 4-6 hours total (2-3 hours for node pools)

## Pre-Upgrade Validation

### Version Compatibility
```bash
# Verify 1.33 available in Regular channel
gcloud container get-server-config --zone us-central1-a --format="yaml(channels)"

# Check current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="table(name, currentMasterVersion, nodePools[].version)"
```

### Critical Checks
- **Deprecated APIs:** Check for removed APIs in 1.33 (most common upgrade blocker)
  ```bash
  # Quick check
  kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
  
  # Comprehensive check via GKE recommender
  gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=us-central1-a \
    --project=PROJECT_ID \
    --filter="category.category:RELIABILITY"
  ```

- **GPU driver compatibility:** Test target GKE 1.33 + driver combination in staging before production
- **Postgres operator compatibility:** Verify your Postgres operator version supports Kubernetes 1.33

## Upgrade Strategy by Node Pool

### 1. General-Purpose Pool
**Strategy:** Surge upgrade (default)
```bash
# Configure surge settings (5% of pool size, minimum 1)
gcloud container node-pools update general-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### 2. High-Memory Pool (Postgres)
**Strategy:** Conservative surge with PDB protection
```bash
# Conservative settings for database workloads
gcloud container node-pools update high-memory-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**Required PDB for Postgres:**
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: postgres-pdb
spec:
  minAvailable: 1  # Adjust based on your replica count
  selector:
    matchLabels:
      app: postgres-operator  # Match your Postgres pod labels
```

### 3. GPU Pool (ML Inference)
**Strategy:** Autoscaled blue-green (recommended for inference to minimize downtime)

**Why autoscaled blue-green for GPU inference:**
- GPU VMs don't support live migration — every surge upgrade causes pod restarts
- Keeps old pool serving while new pool warms up
- Avoids inference latency spikes from drain-and-restart

```bash
# Enable autoscaled blue-green upgrade
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --enable-autoscaling \
  --total-min-nodes 1 \
  --total-max-nodes MAX_NODES \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.25,blue-green-full-batch-timeout=3600s
```

**Alternative if capacity constraints:** If you have fixed GPU reservations with no extra capacity:
```bash
gcloud container node-pools update gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

## Step-by-Step Upgrade Process

### Phase 1: Control Plane Upgrade (15-20 minutes)
```bash
# Upgrade control plane first (required order)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone us-central1-a \
  --master \
  --cluster-version 1.33

# Verify completion
gcloud container clusters describe CLUSTER_NAME \
  --zone us-central1-a \
  --format="value(currentMasterVersion)"
```

**Note:** During CP upgrade on zonal clusters, you cannot deploy new workloads or modify cluster config. Existing workloads continue running.

### Phase 2: Node Pool Upgrades (Sequential)

**Order:** General → High-memory → GPU (lowest to highest risk)

```bash
# 1. General-purpose pool
gcloud container node-pools upgrade general-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33

# Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# 2. High-memory pool (after general completes)
gcloud container node-pools upgrade high-memory-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33

# 3. GPU pool (after high-memory completes)
gcloud container node-pools upgrade gpu-pool \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.33
```

### Phase 3: Validation

```bash
# Verify all components at 1.33
gcloud container node-pools list --cluster CLUSTER_NAME --zone us-central1-a
kubectl get nodes -o wide

# Check workload health
kubectl get pods -A | grep -v Running | grep -v Completed
kubectl get deployments -A
kubectl get statefulsets -A

# Test inference endpoints
# Run your ML inference health checks here

# Verify Postgres operator status
kubectl get postgresql -A  # Adjust based on your operator
```

## Pre-Upgrade Checklist

```markdown
- [ ] 1.33 available in Regular channel confirmed
- [ ] Deprecated API usage checked (zero findings required)
- [ ] Postgres operator version supports Kubernetes 1.33
- [ ] GPU driver compatibility tested in staging
- [ ] PDBs configured for Postgres workloads
- [ ] Inference endpoint monitoring active
- [ ] Maintenance window scheduled (4-6 hour block)
- [ ] Rollback plan documented
- [ ] On-call team available
```

## Rollback Plan

**Control plane:** Minor version rollback requires GKE support involvement. Not self-service.

**Node pools:** Create new pools at 1.32 and migrate workloads:
```bash
# Create rollback pool
gcloud container node-pools create POOL_NAME-rollback \
  --cluster CLUSTER_NAME \
  --zone us-central1-a \
  --cluster-version 1.32 \
  --num-nodes NUM_NODES \
  --machine-type MACHINE_TYPE

# Migrate and cleanup
```

## Troubleshooting Quick Reference

**Most likely issues:**
1. **PDB blocking drain:** `kubectl get pdb -A` → temporarily relax overly restrictive PDBs
2. **GPU surge capacity unavailable:** Switch to `maxSurge=0, maxUnavailable=1`
3. **Postgres pods stuck terminating:** Check `terminationGracePeriodSeconds`, may need to increase
4. **Inference latency spikes:** Autoscaled blue-green should prevent this, but monitor closely

## Timeline Estimate

- **Pre-flight checks:** 30 minutes
- **Control plane upgrade:** 15-20 minutes
- **General pool:** 45-60 minutes
- **High-memory pool:** 30-45 minutes  
- **GPU pool:** 60-90 minutes (autoscaled blue-green)
- **Validation:** 30 minutes

**Total:** 4-6 hours

## Next Steps

1. Schedule maintenance window during off-peak hours
2. Run deprecated API check immediately
3. Test GPU driver compatibility in staging
4. Configure PDBs for Postgres workloads
5. Set up monitoring for inference endpoints during upgrade

This plan prioritizes workload availability while progressing through the upgrade systematically. The autoscaled blue-green strategy for GPU inference should minimize service disruption for your ML workloads.
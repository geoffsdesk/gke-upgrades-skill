# GKE Upgrade Plan: Mixed Spot/On-Demand Node Pool (1.31→1.32)

## Spot VM Upgrade Considerations

Spot instances have unique characteristics that actually make them **lower risk** for upgrades compared to on-demand instances:

### Key Advantages
- **Workloads are preemption-tolerant by design** — your applications already handle interruption gracefully
- **Lower upgrade risk** — since workloads expect node loss, upgrade-induced restarts are less disruptive
- **Cost-effective testing** — spot pools make excellent canaries for validating upgrade procedures

### Recommended Upgrade Strategy

**1. Upgrade Spot Pool First (Canary Strategy)**
```bash
# Configure more aggressive surge settings for spot pool
gcloud container node-pools update SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5% \
  --max-unavailable-upgrade 2

# Upgrade spot pool first
gcloud container node-pools upgrade SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

**2. Conservative Settings for On-Demand Pool**
```bash
# More conservative settings for on-demand workloads
gcloud container node-pools update ONDEMAND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade after spot validation
gcloud container node-pools upgrade ONDEMAND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

### Spot-Specific Surge Configuration

**Recommended for spot pools:**
- **maxSurge**: 2-5% of pool size (higher than on-demand)
- **maxUnavailable**: 1-2 nodes (workloads tolerate interruption)
- **Reasoning**: Since spot workloads already handle preemption, they can tolerate more concurrent disruption during upgrades

**Example for a 20-node spot pool:**
```bash
# 5% of 20 nodes = 1 node surge (minimum 1)
gcloud container node-pools update spot-pool \
  --cluster my-cluster \
  --zone us-central1-a \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 2
```

## Pre-Upgrade Checklist

```markdown
- [ ] Control plane upgrade: 1.31→1.32 completed first
- [ ] Spot workloads have proper PDBs (even preemption-tolerant workloads benefit from orderly drain)
- [ ] Sufficient compute quota for spot surge nodes
- [ ] On-demand pool upgrade planned after spot validation
- [ ] Monitoring baseline captured for both pool types
```

## Upgrade Sequence

**Phase 1: Control Plane**
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.latest
```

**Phase 2: Spot Pool (Canary)**
```bash
# Monitor spot pool upgrade
watch 'kubectl get nodes -l cloud.google.com/gke-preemptible=true -o wide'

# Validate workload health on upgraded spot nodes
kubectl get pods -A -o wide | grep spot-pool-node-names
```

**Phase 3: On-Demand Pool (After Validation)**
```bash
# Conservative upgrade after spot validation passes
gcloud container node-pools upgrade ONDEMAND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

## Monitoring During Upgrade

**Spot-specific metrics to watch:**
```bash
# Check preemption rates don't spike during upgrade
kubectl get events -A --field-selector reason=Preempted

# Verify spot workloads reschedule properly
kubectl get pods -A -o wide | grep -E "(spot|preemptible)"

# Monitor node readiness across both pool types
kubectl get nodes -L cloud.google.com/gke-preemptible,cloud.google.com/gke-nodepool
```

## Validation Steps

**Post-upgrade verification:**
- [ ] Both spot and on-demand nodes at version 1.32
- [ ] Spot workloads rescheduled and healthy
- [ ] No pods stuck in Pending due to node affinity issues
- [ ] Cluster autoscaler functioning across both pool types

## Key Takeaway

**Spot instances are actually EASIER to upgrade** than on-demand because the workloads are already designed for node volatility. Use them as your canary — upgrade spot pools first with more aggressive settings, validate the procedure, then apply conservative settings to your on-demand pools.

The main risk is ensuring your PDBs and resource requests are properly configured so workloads can reschedule smoothly between pool types during the upgrade process.
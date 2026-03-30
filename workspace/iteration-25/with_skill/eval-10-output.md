# GKE Node Pool Upgrade Plan: Mixed Spot & On-Demand

## Spot VM Upgrade Considerations

Spot instances have unique characteristics that actually make upgrades **lower risk** than on-demand instances:

### Key Advantages
- **Workloads are preemption-tolerant by design** — your applications already handle interruption gracefully
- **Lower upgrade risk** — since workloads expect sudden termination, drain/restart during upgrade is less disruptive
- **Faster upgrade settings** — you can use more aggressive surge parameters safely

## Recommended Upgrade Strategy

### 1. Upgrade Sequencing
```bash
# Upgrade spot pools FIRST, then on-demand pools
# Spot carries lower risk and validates your surge settings
```

**Order:**
1. Spot node pools (validation run)
2. On-demand node pools (after spot validation succeeds)

### 2. Surge Configuration for Mixed Pools

**For spot-only node pools:**
```bash
gcloud container node-pools update SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5 \
  --max-unavailable-upgrade 2
```

**For on-demand pools:**
```bash
gcloud container node-pools update ONDEMAND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

### 3. Rationale for Higher Surge on Spot
- **2-5% maxSurge** (higher than typical 1-2%) is safe because workloads already tolerate interruption
- **maxUnavailable 1-2** allows faster drain since workloads handle termination well
- **Validates drain patterns** before applying to more sensitive on-demand workloads

## Pre-Upgrade Checklist

```markdown
Mixed Spot/On-Demand Upgrade Checklist
- [ ] Cluster: ___ | Current: 1.31 | Target: 1.32
- [ ] Spot workloads confirmed preemption-tolerant
- [ ] PDBs configured (even for spot workloads - ensures orderly drain)
- [ ] Upgrade order: spot pools → on-demand pools
- [ ] Surge settings: spot (higher) vs on-demand (conservative)
- [ ] Maintenance window during off-peak hours
- [ ] Monitoring active for both pool types
```

## Upgrade Runbook

### Phase 1: Control Plane
```bash
# Upgrade control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.latest

# Verify (wait ~10-15 min)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

### Phase 2: Spot Node Pools (First)
```bash
# Configure aggressive surge for spot pools
gcloud container node-pools update SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5 \
  --max-unavailable-upgrade 2

# Upgrade spot pool
gcloud container node-pools upgrade SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.latest

# Monitor progress
watch 'kubectl get nodes -l cloud.google.com/gke-preemptible=true -o wide'
```

### Phase 3: On-Demand Pools (After Spot Success)
```bash
# Conservative surge for on-demand
gcloud container node-pools update ONDEMAND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# Upgrade on-demand pool
gcloud container node-pools upgrade ONDEMAND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.latest

# Monitor progress
watch 'kubectl get nodes -l cloud.google.com/gke-preemptible=false -o wide'
```

## Validation Commands

```bash
# Check all nodes upgraded
kubectl get nodes -o wide -L cloud.google.com/gke-preemptible

# Verify workload health on both pool types
kubectl get pods -A | grep -v Running | grep -v Completed

# Confirm no stuck pods
kubectl get pdb -A -o wide
```

## Why This Approach Works

1. **Risk mitigation:** Spot pools validate upgrade process with lower-risk workloads
2. **Faster feedback:** Higher surge on spot gives quicker upgrade completion
3. **Pattern validation:** Successful spot upgrade confirms surge/drain settings work
4. **Workload alignment:** Matches upgrade aggressiveness to workload tolerance

## Important Notes

- **PDBs still matter:** Even spot workloads benefit from PDBs for orderly drain during upgrades
- **No special GKE handling:** GKE treats spot and on-demand nodes identically during upgrades
- **Cost efficiency:** Spot pool upgrades are faster due to higher maxSurge, reducing overall maintenance window

This strategy leverages the inherent resilience of spot workloads to validate your upgrade process before applying it to more sensitive on-demand workloads.
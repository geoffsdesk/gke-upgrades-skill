# GKE Upgrade Plan: Mixed Spot/On-Demand Node Pool

## Spot VM Upgrade Strategy

Spot instances have unique characteristics that actually make upgrades **lower risk** than on-demand:

### Key Advantages
- **Workloads are preemption-tolerant by design** — they already handle interruption gracefully
- **Lower upgrade risk** — if something goes wrong during drain, the impact is similar to normal spot preemption
- **Faster upgrade velocity** — can use more aggressive surge settings

### Recommended Upgrade Approach

**1. Upgrade spot pools FIRST, then on-demand**
```bash
# Upgrade spot node pool first (lower risk, validates settings)
gcloud container node-pools upgrade spot-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Then upgrade on-demand pool
gcloud container node-pools upgrade on-demand-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

**2. Optimized surge settings for spot pools:**
```bash
# Configure more aggressive settings for spot pools
gcloud container node-pools update spot-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 1

# More conservative for on-demand pools
gcloud container node-pools update on-demand-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**Reasoning:** 
- Spot: `maxSurge=3` (higher than typical 1-2% because workloads tolerate interruption)
- Spot: `maxUnavailable=1` (safe to drain since workloads handle preemption)
- On-demand: Conservative settings since these likely run more critical workloads

## Pre-Upgrade Checklist

```markdown
Spot/Mixed Pool Upgrade Checklist
- [ ] Control plane upgraded to 1.32 first
- [ ] Spot workloads have proper restart policies and health checks
- [ ] PDBs configured even for spot workloads (ensures orderly drain vs random preemption)
- [ ] Adequate compute quota for surge nodes
- [ ] Spot pool surge settings: maxSurge=3, maxUnavailable=1
- [ ] On-demand pool surge settings: maxSurge=1, maxUnavailable=0
- [ ] Upgrade sequence: spot pools → on-demand pools
```

## Upgrade Commands

```bash
# 1. Control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32

# 2. Configure spot pool (more aggressive)
gcloud container node-pools update spot-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 1

# 3. Upgrade spot pool first
gcloud container node-pools upgrade spot-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# 4. Monitor and validate spot pool upgrade
kubectl get nodes -l cloud.google.com/gke-preemptible=true
kubectl get pods -A | grep -v Running | grep -v Completed

# 5. Configure on-demand pool (conservative)
gcloud container node-pools update on-demand-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# 6. Upgrade on-demand pool
gcloud container node-pools upgrade on-demand-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

## Why Upgrade Spot First?

1. **Lower blast radius** — spot workloads already handle node loss
2. **Validates surge/drain settings** — if issues arise, they're contained to preemption-tolerant workloads  
3. **Tests the upgrade path** — spot pools act as a "canary" for the on-demand upgrade
4. **Faster recovery** — spot workloads restart quickly after any issues

## Important Notes

- **PDBs still matter** — even for spot workloads, PDBs ensure controlled drain rather than random interruption during upgrades
- **Mixed pools are not recommended** — if your pool contains both spot and on-demand in a single node pool, consider separating them into dedicated pools for better upgrade control
- **Version compatibility** — both pool types follow the same N+2 node version skew rules

This strategy leverages spot instances' inherent resilience to make your overall upgrade safer and faster.
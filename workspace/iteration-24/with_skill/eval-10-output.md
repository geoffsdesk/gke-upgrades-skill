# Spot VM Node Pool Upgrade Plan

## Special considerations for spot instances

Spot VMs have unique characteristics that actually **simplify** upgrade planning:

### Key advantages
- **Workloads are preemption-tolerant by design** — your applications already handle interruption, so upgrade risk is inherently lower
- **Less conservative settings needed** — you can use more aggressive surge parameters since workloads tolerate disruption
- **Lower upgrade risk** — ideal for testing surge/drain settings before upgrading critical on-demand pools

### Recommended upgrade strategy

**For your spot node pools:**
```bash
# More aggressive surge settings (higher than typical on-demand)
gcloud container node-pools update SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5 \
  --max-unavailable-upgrade 2

# Upgrade spot pool
gcloud container node-pools upgrade SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

**Surge calculation:** For spot pools, recommend 2-5% of pool size for `maxSurge` (vs 1-2% for on-demand). If you have a 40-node spot pool, use `maxSurge=2, maxUnavailable=2`.

**For your on-demand pools (upgrade second):**
```bash
# Conservative settings for critical workloads
gcloud container node-pools update ON_DEMAND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

## Upgrade sequencing strategy

**Upgrade spot pools FIRST, then on-demand:**

1. **Control plane:** 1.31 → 1.32
2. **Spot pools:** Upgrade with aggressive surge settings
3. **Validate:** Monitor workload behavior on upgraded spot nodes
4. **On-demand pools:** Upgrade with conservative settings

This sequence lets you validate the 1.31→1.32 upgrade impact on lower-risk workloads before touching critical on-demand infrastructure.

## Still use PDBs for spot workloads

Even though spot workloads handle preemption, **still configure PDBs** to ensure orderly drain during upgrades:

```bash
# Example PDB for spot batch workloads
kubectl apply -f - <<EOF
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: spot-batch-pdb
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: batch-processor
      node-type: spot
EOF
```

PDBs prevent **too many** pods from draining simultaneously, even if individual pods can tolerate restart.

## Pre-upgrade checklist additions

- [ ] Spot workloads have checkpoint/resume capability
- [ ] Batch jobs can restart from last checkpoint
- [ ] No long-running state that can't be recreated
- [ ] PDBs configured to prevent excessive simultaneous eviction
- [ ] Spot pool upgrade scheduled during lower-demand period

## Monitoring during upgrade

```bash
# Watch spot node upgrades (typically faster due to higher maxSurge)
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=SPOT_POOL_NAME -o wide'

# Monitor preempted vs drained pods
kubectl get events -A --field-selector reason=Killing,reason=Preempted
```

The key insight: **leverage spot's inherent resilience** to use more aggressive upgrade settings and validate your 1.32 upgrade on lower-risk infrastructure first.
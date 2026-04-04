# GKE Upgrade Plan: Mixed Spot + On-Demand Node Pool (1.31 → 1.32)

## Spot VM Upgrade Considerations

Spot instances have unique characteristics that actually make upgrades **less risky** than regular on-demand nodes:

### Key Advantages
- **Workloads are already preemption-tolerant** by design — they handle interruption gracefully
- **Lower blast radius** — upgrade failures have less impact since workloads expect node loss
- **Natural resilience testing** — if your workloads survive spot preemption, they'll handle upgrade drain

### Recommended Strategy

**Use more aggressive surge settings for spot pools:**
```bash
# For spot node pools - higher concurrency is safe
gcloud container node-pools update SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5% \
  --max-unavailable-upgrade 2

# For on-demand pools - more conservative
gcloud container node-pools update ON_DEMAND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### Upgrade Sequencing

**Upgrade spot pools FIRST, then on-demand:**

1. **Spot pools first** — validate your surge/drain settings with lower-risk workloads
2. **Soak period** — wait 30-60 minutes, monitor for issues
3. **On-demand pools** — apply lessons learned from spot pool upgrade

### Mixed Pool Architecture Considerations

If you're running **mixed spot + on-demand in the same pool** (via node taints/tolerations):

**Option A: Split into separate pools (recommended for upgrades)**
```bash
# Create dedicated spot pool
gcloud container node-pools create spot-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --spot \
  --node-taints=cloud.google.com/gke-spot=true:NoSchedule \
  --num-nodes 3

# Create dedicated on-demand pool  
gcloud container node-pools create on-demand-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --num-nodes 2
```

**Option B: Single mixed pool upgrade**
- Use conservative settings: `maxSurge=1, maxUnavailable=0`
- Expect some workloads may migrate between spot/on-demand during upgrade
- Monitor for cost implications (temporary shift to more on-demand nodes)

## Pre-Upgrade Checklist

```markdown
Mixed Spot/On-Demand Upgrade Checklist
- [ ] Workloads have spot tolerations configured
- [ ] PDBs account for spot preemption (not overly restrictive)
- [ ] Cost monitoring active (upgrade may temporarily increase on-demand usage)
- [ ] Separate surge settings configured per pool type
- [ ] Upgrade sequence planned: spot pools → on-demand pools
```

## Upgrade Commands

```bash
# 1. Control plane first
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32

# 2. Spot node pools (aggressive settings)
gcloud container node-pools upgrade SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor and wait for completion, then:

# 3. On-demand pools (conservative settings)  
gcloud container node-pools upgrade ON_DEMAND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

## Cost Considerations

- **Temporary cost increase** — surge nodes may default to on-demand if spot capacity unavailable
- **Rebalancing period** — after upgrade, cluster autoscaler will rebalance to preferred spot/on-demand ratio
- **Monitor during upgrade** — watch for unexpected shifts to higher-cost instances

## Troubleshooting Spot-Specific Issues

**Spot capacity unavailable during surge:**
```bash
# Check events for capacity issues
kubectl get events -A --field-selector reason=FailedCreatePodSandBox

# If persistent, switch to drain-first mode
gcloud container node-pools update SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

The main advantage with spot workloads is that they're **designed for disruption** — your upgrade risk is inherently lower than with traditional on-demand workloads that expect stable nodes.
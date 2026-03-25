# GKE Upgrade Plan: Spot VM Node Pool Considerations

## Key Spot VM Upgrade Characteristics

Spot instances have unique properties that actually make them **lower risk** for upgrades:

- **Workloads are preemption-tolerant by design** — your applications already handle sudden instance termination
- **Upgrade risk is inherently lower** — spot workloads tolerate interruption better than on-demand
- **Higher surge settings are safe** — since workloads handle disruption, more aggressive upgrade parallelism is acceptable

## Recommended Upgrade Strategy

### 1. Upgrade Sequencing
**Upgrade spot pools FIRST, then on-demand pools:**
```bash
# Upgrade spot pool first (lower risk)
gcloud container node-pools upgrade spot-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxx

# Then upgrade on-demand pool
gcloud container node-pools upgrade on-demand-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxx
```

This approach validates your surge/drain settings on the more fault-tolerant workloads first.

### 2. Optimized Surge Settings for Spot Pools

**For spot node pools:**
```bash
gcloud container node-pools update spot-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5 \
  --max-unavailable-upgrade 2
```

**Rationale:**
- **maxSurge=5**: Higher than typical (2-5% of pool size) because spot workloads tolerate restarts
- **maxUnavailable=2**: Allows some nodes to drain simultaneously since workloads handle interruption
- **Cost impact**: Brief surge of extra spot instances (typically 60-80% cheaper than on-demand)

**For on-demand pools (more conservative):**
```bash
gcloud container node-pools update on-demand-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

### 3. PDB Configuration

**Still use PDBs even for spot workloads** to ensure orderly drain:
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: spot-workload-pdb
spec:
  selector:
    matchLabels:
      app: your-spot-app
  maxUnavailable: 50%  # More permissive than on-demand workloads
```

This allows GKE to drain multiple spot pods simultaneously while maintaining some instances for service continuity.

## Pre-Upgrade Checklist

```markdown
Spot VM Upgrade Checklist
- [ ] Control plane upgraded to 1.32 first
- [ ] Spot workloads confirmed preemption-tolerant
- [ ] PDBs configured (more permissive than on-demand)
- [ ] Upgrade sequence planned: spot pools → on-demand pools
- [ ] Higher maxSurge/maxUnavailable configured for spot pools
- [ ] Node selectors/affinity rules reviewed (spot vs on-demand targeting)
```

## Upgrade Commands

```bash
# 1. Verify current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# 2. Configure spot pool for aggressive upgrade
gcloud container node-pools update SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5 \
  --max-unavailable-upgrade 2

# 3. Upgrade spot pool first
gcloud container node-pools upgrade SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxx

# 4. Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-preemptible'

# 5. After spot pool completes, upgrade on-demand pool
gcloud container node-pools update ON_DEMAND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade ON_DEMAND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxx
```

## Advantages of Spot-First Approach

1. **Risk validation**: Test your upgrade process on fault-tolerant workloads first
2. **Faster feedback**: Spot pools can use higher parallelism for quicker completion
3. **Cost efficiency**: Spot surge nodes cost 60-80% less during the brief upgrade window
4. **Workload validation**: Confirm applications handle the upgrade-induced restarts properly

## Monitoring During Upgrade

```bash
# Watch node status across both pools
kubectl get nodes -L cloud.google.com/gke-preemptible,cloud.google.com/gke-nodepool

# Check workload health
kubectl get pods -A | grep -E "(spot|on-demand)" | grep -v Running

# Verify no stuck PDBs
kubectl get pdb -A -o wide
```

The key insight is that spot instances' fault-tolerance makes them ideal candidates for more aggressive upgrade settings and should be upgraded first to validate your process before touching critical on-demand workloads.
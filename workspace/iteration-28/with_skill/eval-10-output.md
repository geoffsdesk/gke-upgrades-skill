# GKE Upgrade Plan: Mixed Spot/On-Demand Node Pools

## Spot VM Upgrade Considerations

Spot instances have unique characteristics that actually make them **lower risk** for upgrades compared to on-demand instances:

### Key Advantages for Upgrades
- **Workloads are preemption-tolerant by design** — your applications already handle interruption gracefully
- **Lower upgrade risk** — since pods can be evicted at any time anyway, the upgrade drain is just another expected interruption
- **Higher upgrade parallelism is safe** — you can be more aggressive with surge settings

### Recommended Upgrade Strategy

**For your mixed spot/on-demand environment:**

1. **Upgrade spot pools FIRST** before on-demand pools
   - Spot carries lower risk and validates your surge/drain settings
   - Use spot as a "canary" for the upgrade process

2. **Use higher maxSurge on spot pools:**
   ```bash
   # Spot pool - more aggressive settings
   gcloud container node-pools update SPOT_POOL_NAME \
     --cluster CLUSTER_NAME \
     --zone ZONE \
     --max-surge-upgrade 5% \
     --max-unavailable-upgrade 0
   
   # On-demand pool - conservative settings  
   gcloud container node-pools update ONDEMAND_POOL_NAME \
     --cluster CLUSTER_NAME \
     --zone ZONE \
     --max-surge-upgrade 1 \
     --max-unavailable-upgrade 0
   ```

3. **Still use PDBs** even for spot workloads to ensure orderly drain:
   ```yaml
   apiVersion: policy/v1
   kind: PodDisruptionBudget
   metadata:
     name: spot-workload-pdb
   spec:
     minAvailable: 75%  # Allows 25% disruption
     selector:
       matchLabels:
         app: your-spot-app
   ```

## Upgrade Sequence

### Phase 1: Control Plane
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.latest
```

### Phase 2: Spot Node Pool (First)
```bash
# Configure for higher parallelism
gcloud container node-pools update SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5 \
  --max-unavailable-upgrade 0

# Upgrade
gcloud container node-pools upgrade SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

### Phase 3: On-Demand Pool (After spot completes)
```bash
# Conservative settings
gcloud container node-pools update ONDEMAND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade
gcloud container node-pools upgrade ONDEMAND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.latest
```

## Pre-Upgrade Checklist

```
Spot VM Upgrade Checklist
- [ ] Verify workloads handle preemption gracefully (should already be true)
- [ ] PDBs configured for spot workloads (even though they're interruption-tolerant)
- [ ] Spot pricing acceptable during upgrade window (surge nodes = temporary cost increase)
- [ ] On-demand workloads can handle temporary capacity reduction during their upgrade
- [ ] Node selectors/taints properly configured to maintain workload placement preferences
- [ ] Cluster autoscaler will not interfere with upgrade (nodes may scale during upgrade)
```

## Monitoring During Upgrade

```bash
# Watch upgrade progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-preemptible'

# Monitor workload distribution
kubectl get pods -o wide --sort-by='.spec.nodeName'

# Check for any scheduling issues
kubectl get events -A --field-selector reason=FailedScheduling
```

## Cost Considerations

- **Temporary cost increase** during surge phase when extra nodes are provisioned
- **Spot nodes during upgrade** still qualify for spot pricing (60-91% discount)
- **Surge duration** typically 10-30 minutes per batch, depending on pool size

The key insight: **Spot VMs make upgrades easier, not harder** — leverage their interruption tolerance for faster, lower-risk upgrades!
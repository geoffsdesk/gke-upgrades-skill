# GKE Upgrade Plan: Mixed Spot/On-Demand Node Pool

## Spot VM Upgrade Strategy

Spot instances have unique characteristics that actually **reduce** upgrade risk compared to on-demand instances:

### Key Advantages for Upgrades
- **Workloads are preemption-tolerant by design** — they already handle interruption gracefully
- **Lower blast radius** — upgrade-related pod restarts are less disruptive than normal preemptions
- **Natural resilience** — applications running on spot are built to handle node loss

### Recommended Surge Settings

For your mixed spot/on-demand pool upgrading 1.31→1.32:

```bash
# More aggressive settings than typical on-demand pools
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5% \
  --max-unavailable-upgrade 1-2

# Then upgrade
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

**Rationale:**
- **maxSurge: 2-5% of pool size** (higher than the typical 1-2% for on-demand)
- **maxUnavailable: 1-2** (spot workloads tolerate the capacity gap)
- This speeds up the upgrade while leveraging spot workloads' inherent fault tolerance

### Upgrade Sequencing Strategy

**Upgrade spot pools FIRST, then on-demand pools:**

1. **Phase 1: Spot node pools**
   - Use aggressive surge settings (5% maxSurge)
   - Validate upgrade behavior and drain patterns
   - Spot workloads serve as a "canary" for the upgrade process

2. **Phase 2: On-demand/critical pools**  
   - Use conservative settings based on spot pool learnings
   - Apply lessons learned from spot pool upgrade

### Pre-Flight Checklist

```markdown
Spot VM Upgrade Checklist
- [ ] Verify workloads handle preemption gracefully (required for spot)
- [ ] PDBs configured even for spot workloads (ensures orderly drain)
- [ ] No bare pods on spot instances
- [ ] Spot pool upgraded before critical on-demand pools
- [ ] Monitor spot instance availability during upgrade window
```

### Monitoring During Upgrade

```bash
# Track spot vs on-demand node upgrade progress
kubectl get nodes -o wide -L cloud.google.com/gke-preemptible,cloud.google.com/gke-nodepool

# Watch for preemptions during upgrade (normal background noise)
kubectl get events -A --field-selector reason=NodeNotReady

# Verify workload rescheduling
kubectl get pods -A -o wide | grep spot-pool-name
```

### Important: Still Use PDBs

Even though spot workloads handle interruption, **still configure PDBs** for:
- **Orderly drain during upgrades** (different from random preemption)
- **Maintaining minimum replicas** during the controlled upgrade process
- **Preventing upgrade-related outages** distinct from spot preemptions

Example PDB for spot workloads:
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: spot-workload-pdb
spec:
  minAvailable: 50%  # Or whatever maintains service
  selector:
    matchLabels:
      app: your-spot-app
```

### Timeline Expectations

- **Spot pools**: Faster upgrade due to aggressive surge settings
- **Mixed pools**: Upgrade time similar to on-demand (limited by most restrictive workload)
- **Validation window**: 30-60 minutes between spot and on-demand pool upgrades

This approach leverages spot instances' fault tolerance to de-risk your overall upgrade while maintaining service availability for critical workloads.
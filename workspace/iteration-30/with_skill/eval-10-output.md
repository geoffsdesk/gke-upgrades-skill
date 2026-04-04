# GKE Spot VM Node Pool Upgrade Plan

## Special Considerations for Spot VMs

Spot instances have unique characteristics that make them **lower risk** for upgrades compared to on-demand instances:

### Key Differences for Spot Upgrades

**Workload tolerance:** Spot workloads are already designed to handle preemption, so upgrade-related restarts carry inherently lower risk than on-demand workloads.

**Recommended surge settings for spot pools:**
```bash
# More aggressive than on-demand - workloads already handle interruption
gcloud container node-pools update SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5% \
  --max-unavailable-upgrade 2
```

**Upgrade sequencing:** Upgrade spot pools **FIRST** before on-demand pools:
- Lower risk validation of your upgrade settings
- Spot workloads validate the new node image/version
- Any issues surface on fault-tolerant workloads first

## Pre-Upgrade Checklist

```
Spot VM Upgrade Considerations
- [ ] Spot workloads designed for preemption (checkpointing, stateless, etc.)
- [ ] PDBs configured even for spot workloads (ensures orderly drain)
- [ ] Spot pool upgraded BEFORE on-demand pools
- [ ] Higher maxSurge/maxUnavailable acceptable due to workload tolerance
- [ ] Batch job submission paused during upgrade window (if applicable)
```

## Upgrade Sequence

### 1. Pre-flight checks
```bash
# Verify current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Check spot pool specifically
gcloud container node-pools describe SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --format="value(config.preemptible)"
```

### 2. Control plane upgrade first
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32
```

### 3. Upgrade spot pools first
```bash
# Configure more aggressive settings for spot
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

# Monitor progress
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=SPOT_POOL_NAME -o wide'
```

### 4. Upgrade on-demand pools after validation
```bash
# More conservative settings for on-demand
gcloud container node-pools update ON_DEMAND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade on-demand pool
gcloud container node-pools upgrade ON_DEMAND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

## Workload-Specific Considerations

### Batch Jobs on Spot
- Pause new job submissions 30 minutes before upgrade
- Ensure jobs have checkpointing enabled
- Consider that spot preemption + upgrade restart is double disruption

### Mixed Workload Scheduling
- Verify workloads can reschedule between spot and on-demand nodes
- Check node affinity/anti-affinity rules don't prevent cross-pool scheduling
- Monitor that critical workloads don't get "stuck" on draining spot nodes

### PDBs Still Important
Even though spot workloads tolerate preemption, configure PDBs to ensure:
- Orderly drain during upgrades (not just random eviction)
- Multiple replicas don't drain simultaneously
- Database/stateful components maintain quorum

```bash
# Example PDB for spot-tolerant but still critical workload
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: spot-workload-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: my-spot-app
```

## Validation Steps

```bash
# Verify spot nodes upgraded
kubectl get nodes -l cloud.google.com/gke-nodepool=SPOT_POOL_NAME \
  -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,SPOT:.metadata.labels.cloud\.google\.com/gke-preemptible

# Check workload distribution
kubectl get pods -A -o wide | grep SPOT_POOL_NAME

# Verify no stuck pods
kubectl get pods -A | grep -v Running | grep -v Completed
```

**Key advantage:** Using spot pools as your "canary" for upgrades gives you early validation with workloads that are already designed to handle disruption, making it a natural testing ground for your upgrade strategy before applying to production on-demand workloads.
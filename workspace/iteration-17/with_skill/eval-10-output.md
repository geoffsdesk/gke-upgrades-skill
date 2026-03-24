# GKE Node Pool Upgrade Plan: Spot + On-Demand Mixed Workloads

## Spot VM Upgrade Considerations

Spot instances have unique characteristics that actually make them **lower risk** for upgrades:

### Key Advantages
- **Workloads are preemption-tolerant by design** — they already handle unexpected interruption
- **Higher surge tolerance** — can use more aggressive `maxSurge` settings since workloads expect restarts
- **Validation opportunity** — upgrade spot pools first to test surge/drain settings before touching on-demand

### Recommended Upgrade Strategy

**1. Upgrade sequencing: Spot pools FIRST**
```bash
# Upgrade spot pools before on-demand pools
# They carry lower risk and validate your surge settings
```

**2. Spot-optimized surge settings:**
```bash
gcloud container node-pools update SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5% \
  --max-unavailable-upgrade 1

# Higher maxSurge (5% vs typical 1-2%) because workloads tolerate restarts
# Calculate 5% of pool size, minimum 1: 40-node pool = maxSurge=2
```

**3. On-demand pools (after spot validation):**
```bash
gcloud container node-pools update ONDEMAND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# More conservative for on-demand workloads
```

## Step-by-Step Upgrade Plan

### Pre-flight Checks
```bash
# Current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Verify 1.32 available in your release channel
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels)"

# Check for deprecated APIs (common 1.31→1.32 issue)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
```

### Upgrade Sequence

**Step 1: Control Plane**
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.xxxx
```

**Step 2: Spot Node Pools (first)**
```bash
# Configure aggressive surge for spot pools
gcloud container node-pools update SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 1

# Upgrade spot pool
gcloud container node-pools upgrade SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxxx

# Monitor progress
watch 'kubectl get nodes -l cloud.google.com/gke-preemptible=true -o wide'
```

**Step 3: On-Demand Pools (after spot validation)**
```bash
# More conservative surge for on-demand
gcloud container node-pools update ONDEMAND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade on-demand pool
gcloud container node-pools upgrade ONDEMAND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.xxxx
```

## PDB Configuration for Mixed Workloads

Even though spot workloads tolerate interruption, **still configure PDBs** for orderly drain:

**Spot workloads:**
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: spot-workload-pdb
spec:
  minAvailable: 50%  # Allows aggressive drain
  selector:
    matchLabels:
      app: your-spot-app
```

**On-demand workloads:**
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: critical-workload-pdb
spec:
  minAvailable: 80%  # More conservative
  selector:
    matchLabels:
      app: your-critical-app
```

## Monitoring During Upgrade

```bash
# Watch both pool types
kubectl get nodes -L cloud.google.com/gke-preemptible,cloud.google.com/gke-nodepool -o wide

# Check for preemptions during upgrade (may coincide)
kubectl get events -A --field-selector reason=Preempted --sort-by='.lastTimestamp'

# Monitor workload distribution
kubectl get pods -o wide | grep -E "spot|ondemand"
```

## Key Differences from Standard Upgrades

| Aspect | Spot Pools | On-Demand Pools |
|--------|------------|------------------|
| **maxSurge** | 5% of pool size (higher) | 1-2 nodes (conservative) |
| **Risk tolerance** | Higher - workloads expect restarts | Lower - minimize disruption |
| **Upgrade order** | First (validation) | Second (after spot proves settings) |
| **PDB settings** | More permissive (50% minAvailable) | Restrictive (80%+ minAvailable) |

## Version-Specific Notes (1.31→1.32)

- **No breaking changes** for spot/preemptible behavior in 1.32
- **Deprecated APIs**: Check for any deprecated API usage that affects both workload types
- **Node image updates**: Both spot and on-demand get the same updated node image

This approach uses spot instances as your "canary" for the upgrade process while maintaining appropriate protection for your critical on-demand workloads.
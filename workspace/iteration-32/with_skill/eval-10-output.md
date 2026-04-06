# GKE Upgrade Plan: Standard Cluster with Spot VMs (1.31 → 1.32)

## Spot VM Upgrade Characteristics

Spot instances have unique advantages for upgrades since workloads are **preemption-tolerant by design**:

- **Lower upgrade risk**: Workloads already handle interruption gracefully
- **Higher parallelism tolerance**: Can use more aggressive surge settings
- **Validation opportunity**: Upgrade spot pools first to test settings before on-demand pools

## Recommended Upgrade Strategy

### 1. Upgrade Sequence
```bash
# Upgrade spot node pools FIRST, then on-demand pools
# Spot pools act as canaries with lower risk
```

**Why spot first?**
- Workloads are interruption-tolerant, so upgrade disruption is minimal
- Validates your surge/drain settings before applying to critical on-demand workloads
- Catches any issues early with lower business impact

### 2. Spot Pool Surge Settings

```bash
gcloud container node-pools update SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5% \  # Higher than typical (2-5% vs 1-2%)
  --max-unavailable-upgrade 2  # Allow some capacity dip
```

**Rationale:**
- **maxSurge 5%**: Higher parallelism since workloads tolerate disruption
- **maxUnavailable 2**: Safe to have some nodes drain simultaneously
- For 20-node spot pool: ~1 surge + 2 draining = 3 nodes upgrading concurrently

### 3. On-Demand Pool Settings (Conservative)

```bash
gcloud container node-pools update ONDEMAND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0  # Zero-downtime for critical workloads
```

## Complete Upgrade Runbook

### Pre-flight Checks
```bash
# Current versions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Identify spot vs on-demand pools
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE \
  --format="table(name, config.preemptible, config.spot, instanceGroupUrls[0])"

# Check PDBs (still important even for spot workloads)
kubectl get pdb -A -o wide
```

### Step 1: Control Plane Upgrade
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32

# Wait for completion (~10-15 minutes)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

### Step 2: Upgrade Spot Pools First
```bash
# Configure spot pool settings
gcloud container node-pools update SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5% \
  --max-unavailable-upgrade 2

# Upgrade spot pool
gcloud container node-pools upgrade SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

# Monitor progress
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=SPOT_POOL_NAME -o wide'
```

### Step 3: Validate Spot Pool Success
```bash
# Confirm all spot nodes upgraded
kubectl get nodes -l cloud.google.com/gke-nodepool=SPOT_POOL_NAME \
  -o custom-columns="NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,READY:.status.conditions[?(@.type=='Ready')].status"

# Check workload health on spot nodes
kubectl get pods -A -o wide | grep SPOT_NODE_NAME
```

### Step 4: Upgrade On-Demand Pools
```bash
# Conservative settings for critical workloads
gcloud container node-pools update ONDEMAND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade on-demand pool
gcloud container node-pools upgrade ONDEMAND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

## Spot-Specific Considerations

### PDBs Still Matter
Even though spot workloads are preemption-tolerant, configure PDBs to ensure orderly drain:
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: spot-workload-pdb
spec:
  minAvailable: 1  # Or 50% for larger deployments
  selector:
    matchLabels:
      app: your-spot-app
```

### Workload Scheduling During Upgrade
Spot workloads may reschedule to on-demand nodes during upgrade. This is normal and temporary. Use node affinity if you want to keep spot workloads on spot nodes:

```yaml
affinity:
  nodeAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
    - weight: 100
      preference:
        matchExpressions:
        - key: cloud.google.com/gke-spot
          operator: In
          values: ["true"]
```

### Cost Optimization
The higher parallelism on spot pools reduces upgrade duration, minimizing the time you're paying for both old and new (surge) nodes.

## Troubleshooting Spot Upgrades

If spot pool upgrade stalls:

1. **Check preemptions during upgrade**:
   ```bash
   kubectl get events -A --field-selector reason=Preempted
   ```

2. **Verify surge capacity available**:
   ```bash
   gcloud compute instances list --filter="labels.goog-gke-node=*" --format="table(name, zone, status, scheduling.preemptible)"
   ```

3. **Reduce parallelism if needed**:
   ```bash
   gcloud container node-pools update SPOT_POOL_NAME \
     --max-surge-upgrade 1 \
     --max-unavailable-upgrade 1
   ```

## Post-Upgrade Validation

```bash
# All nodes at 1.32
kubectl get nodes -o custom-columns="NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,SPOT:.metadata.labels.cloud\.google\.com/gke-spot"

# Workload distribution looks healthy
kubectl get pods -A -o wide | awk '{print $8}' | sort | uniq -c

# No stuck pods
kubectl get pods -A | grep -v Running | grep -v Completed
```

The key advantage of mixed spot/on-demand environments is using spot pools as **low-risk canaries** for your upgrade settings before applying them to critical on-demand workloads.
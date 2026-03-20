# GKE Node Pool Upgrade Plan: Spot VM Considerations

## Spot VM Upgrade Behavior

Spot VMs in GKE node pools have **identical upgrade behavior** to regular (on-demand) instances during planned maintenance operations like version upgrades. The key difference is that spot VMs can be preempted by Google at any time for capacity reclamation, independent of your upgrade schedule.

## Upgrade Strategy for Mixed Spot/On-Demand Pools

### Recommended approach: Surge upgrade with conservative settings

```bash
# Configure surge settings for mixed pool
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

**Why this works:** During surge upgrades, GKE creates new nodes (respecting your spot/on-demand ratio), drains old nodes gracefully, then deletes them. Spot preemption risk exists but doesn't interfere with the upgrade process itself.

### Alternative: Split into separate pools (recommended for production)

If you need different upgrade timing or reliability guarantees:

```bash
# Create dedicated spot pool
gcloud container node-pools create spot-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --spot \
  --num-nodes 3 \
  --machine-type n1-standard-4

# Create dedicated on-demand pool  
gcloud container node-pools create ondemand-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --num-nodes 2 \
  --machine-type n1-standard-4
```

## Spot-Specific Considerations

### 1. **Workload placement strategy**

Use node selectors and tolerations to control which workloads run on spot vs on-demand:

```yaml
# For fault-tolerant batch jobs → spot nodes
apiVersion: apps/v1
kind: Deployment
metadata:
  name: batch-processing
spec:
  template:
    spec:
      nodeSelector:
        cloud.google.com/gke-spot: "true"
      tolerations:
      - key: cloud.google.com/gke-spot
        operator: Equal
        value: "true"
        effect: NoSchedule
---
# For critical services → on-demand nodes
apiVersion: apps/v1  
kind: Deployment
metadata:
  name: critical-api
spec:
  template:
    spec:
      nodeSelector:
        cloud.google.com/gke-spot: "false"
```

### 2. **PDB configuration**

Spot VMs add additional disruption risk beyond upgrades. Configure PDBs appropriately:

```yaml
# More conservative PDB for mixed pools
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: critical-app-pdb
spec:
  minAvailable: 75%  # Higher than usual due to spot preemption risk
  selector:
    matchLabels:
      app: critical-app
```

### 3. **Upgrade timing considerations**

- **Spot VM availability fluctuates** based on Google Cloud capacity and demand
- During high-demand periods (US business hours, month-end compute spikes), spot capacity may be limited
- **Recommendation:** Schedule upgrades during off-peak hours when spot capacity is typically more available
- If surge nodes can't be provisioned due to spot unavailability, the upgrade will pause until capacity becomes available

## Pre-Upgrade Checklist for Spot Pools

```markdown
Spot VM Upgrade Checklist
- [ ] Current pool composition verified: `kubectl get nodes -o wide -l cloud.google.com/gke-nodepool=NODE_POOL_NAME`
- [ ] Spot VM ratio documented (for validation post-upgrade)
- [ ] Workload placement strategy confirmed (spot-tolerant vs critical workloads)
- [ ] PDBs configured with spot preemption risk in mind
- [ ] Upgrade window scheduled during off-peak hours for better spot availability
- [ ] Alternative plan if spot capacity unavailable (switch to on-demand temporarily)
- [ ] Monitoring alerts configured for spot preemption events during upgrade window
```

## Upgrade Commands

### Control plane (same as any cluster)
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.30
```

### Mixed spot/on-demand node pool
```bash
# Configure conservative surge for mixed pool
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# Upgrade the pool
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30
```

## Post-Upgrade Validation

```bash
# Verify spot/on-demand ratio maintained
kubectl get nodes -o custom-columns="NAME:.metadata.name,SPOT:.metadata.labels.cloud\.google\.com/gke-spot,VERSION:.status.nodeInfo.kubeletVersion"

# Check no workloads stuck on wrong node types
kubectl get pods -A -o wide | grep -E "spot-sensitive-app|critical-service"

# Confirm PDBs not blocking future maintenance
kubectl get pdb -A
```

## Fallback Strategy

If spot capacity becomes unavailable during upgrade:

1. **Pause the upgrade** (GKE will automatically pause if surge nodes can't be created)
2. **Temporarily switch to on-demand** for surge capacity:
   ```bash
   # Create temporary on-demand pool for upgrade
   gcloud container node-pools create upgrade-temp \
     --cluster CLUSTER_NAME \
     --zone ZONE \
     --num-nodes 2 \
     --machine-type MACHINE_TYPE
   ```
3. **Complete upgrade with mixed capacity**, then return to original configuration

## Key Takeaway

Spot VMs don't change the upgrade mechanics, but they add capacity availability risk. The main considerations are workload placement strategy, more conservative PDBs, and having a fallback plan if spot capacity is unavailable during your upgrade window.
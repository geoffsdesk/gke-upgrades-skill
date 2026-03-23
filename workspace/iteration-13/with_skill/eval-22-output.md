# GKE Node Pool Upgrade: Pod Shuffling Issue

This is a classic "musical chairs" problem during GKE node upgrades. Pods are being evicted from draining nodes but landing on other nodes that are also queued for upgrade, creating a cycle of unnecessary pod restarts.

## Root Cause Analysis

**What's happening:**
- GKE's surge upgrade process creates new nodes and drains old ones in batches
- The Kubernetes scheduler doesn't know which nodes are "safe" (already upgraded) vs "temporary" (about to be drained)
- Pods get scheduled to any available node with capacity, including nodes that are next in the upgrade queue
- This causes pods to be evicted multiple times during the upgrade

**Why it happens:**
1. **Insufficient surge capacity** - Not enough new nodes available to absorb all evicted pods
2. **Scheduler ignorance** - The scheduler can't distinguish between upgraded and to-be-upgraded nodes
3. **Batch timing** - Multiple batches of old nodes being drained simultaneously

## Immediate Fixes

### 1. Increase Surge Capacity (Recommended)
```bash
# Increase maxSurge to create more "safe" nodes upfront
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 5 \
  --max-unavailable-upgrade 0
```

**Sizing guidance:**
- For a 20-node pool: `maxSurge=3-5` (15-25%)
- For a 100-node pool: `maxSurge=10-15` (10-15%)
- For GPU pools with limited surge quota: `maxSurge=1, maxUnavailable=1`

### 2. Use Node Affinity to Prefer Upgraded Nodes
```yaml
# Add to your Deployment/StatefulSet spec
spec:
  template:
    spec:
      affinity:
        nodeAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            preference:
              matchExpressions:
              - key: node.kubernetes.io/instance-type
                operator: In
                values: ["n1-standard-4"]  # Your target node type
```

### 3. Use Pod Disruption Budgets Strategically
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: my-app-pdb
spec:
  minAvailable: 50%
  selector:
    matchLabels:
      app: my-app
```

This slows down the drain process, giving more time for new nodes to become available.

## Better Upgrade Strategies

### Option A: Auto-Scale Blue-Green (Recommended for Large Pools)
```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoscaling \
  --total-min-nodes 10 \
  --total-max-nodes 50 \
  --autoscaled-rollout-policy=blue-green-initial-node-percentage=0.3,blue-green-full-batch-timeout=3600s
```

**Benefits:**
- Creates a separate "green" pool that scales up as needed
- Pods migrate once from blue to green, not multiple times
- Old pool scales down as workloads move

### Option B: Manual Blue-Green (Maximum Control)
```bash
# 1. Create new pool at target version
gcloud container node-pools create NODE_POOL_NAME-v2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION \
  --num-nodes TARGET_NODE_COUNT

# 2. Cordon old pool (prevents new pods from landing there)
kubectl cordon -l cloud.google.com/gke-nodepool=NODE_POOL_NAME

# 3. Wait for pods to naturally reschedule to new pool
# Or drain gradually:
for node in $(kubectl get nodes -l cloud.google.com/gke-nodepool=NODE_POOL_NAME -o name); do
  kubectl drain $node --ignore-daemonsets --delete-emptydir-data --grace-period=300
  sleep 60  # Pause between nodes
done

# 4. Delete old pool
gcloud container node-pools delete NODE_POOL_NAME --cluster CLUSTER_NAME --zone ZONE
```

## Prevention for Next Time

### 1. Right-Size Surge Settings
```bash
# Configure before starting upgrade
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 15%  # Percentage of pool size
  --max-unavailable-upgrade 0
```

### 2. Use Topology Spread Constraints
```yaml
spec:
  template:
    spec:
      topologySpreadConstraints:
      - maxSkew: 1
        topologyKey: topology.kubernetes.io/zone
        whenUnsatisfiable: DoNotSchedule
        labelSelector:
          matchLabels:
            app: my-app
```

This spreads pods across zones and can help avoid concentration on nodes about to be upgraded.

### 3. Monitor Upgrade Progress
```bash
# Watch node versions during upgrade
watch 'kubectl get nodes -L cloud.google.com/gke-nodepool -o wide'

# Monitor pod movements
kubectl get events -A --field-selector reason=Scheduled,reason=NodeDraining -w
```

## Immediate Actions for Your Current Stuck Upgrade

1. **Check current surge settings:**
   ```bash
   gcloud container node-pools describe NODE_POOL_NAME \
     --cluster CLUSTER_NAME \
     --zone ZONE \
     --format="value(upgradeSettings)"
   ```

2. **Increase surge if too low:**
   ```bash
   gcloud container node-pools update NODE_POOL_NAME \
     --cluster CLUSTER_NAME \
     --zone ZONE \
     --max-surge-upgrade 3  # Adjust based on pool size
   ```

3. **Temporarily relax PDBs if they're too restrictive:**
   ```bash
   kubectl get pdb -A
   # If any show ALLOWED DISRUPTIONS = 0, temporarily increase maxUnavailable
   ```

The upgrade should stabilize once there are enough "safe" upgraded nodes to absorb the evicted pods. The musical chairs effect typically resolves itself once surge capacity catches up, but increasing `maxSurge` accelerates this process significantly.
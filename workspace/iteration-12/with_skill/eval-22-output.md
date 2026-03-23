# Node Pool Upgrade Musical Chairs Issue

You're experiencing a common GKE upgrade pattern where the **upgrade algorithm** and **scheduler** are working at cross-purposes. Here's what's happening and how to fix it:

## Root Cause Analysis

**The problem:** GKE's node upgrade algorithm doesn't coordinate with the Kubernetes scheduler about which nodes are "safe" destinations. The scheduler sees multiple available nodes and may place evicted pods on nodes that are queued for drain in the next upgrade batch.

**Why it happens:**
1. **Surge upgrade behavior**: GKE creates new nodes, then drains old ones in batches
2. **Scheduler ignorance**: The scheduler doesn't know which nodes are "doomed" - it just sees available capacity
3. **Batch overlap**: Your `maxSurge` and `maxUnavailable` settings create overlapping drain windows
4. **No upgrade-aware scheduling**: Kubernetes has no built-in "don't schedule on nodes about to upgrade" logic

## Immediate Fixes

### 1. Adjust surge settings to reduce overlap

**Current problem configuration (likely):**
```bash
maxSurge=1, maxUnavailable=1
# This creates overlapping drain windows
```

**Better configuration:**
```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0
```

**Why this helps:** With `maxUnavailable=0`, GKE won't drain any nodes until replacement nodes are fully ready and available. This gives evicted pods a guaranteed safe landing spot.

### 2. Use node selectors to pin workloads temporarily

**During the upgrade, add a node selector to critical workloads:**

```bash
# First, label the already-upgraded nodes
kubectl label nodes NODE_NAME upgrade-status=complete

# Then patch your deployment to prefer completed nodes
kubectl patch deployment MY_APP \
  -p '{"spec":{"template":{"spec":{"nodeSelector":{"upgrade-status":"complete"}}}}}'
```

Remove the selector after upgrade completes.

### 3. Switch to blue-green upgrade strategy

If the musical chairs continues, consider GKE's native blue-green upgrade:

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-blue-green-upgrade \
  --node-pool-soak-duration 300s
```

**Why this works:** Blue-green keeps old nodes cordoned but available while new nodes are provisioned. Workloads migrate once to the green pool and stay there.

## Long-term Solutions

### 4. Use pod topology spread constraints

Add this to workload specs to distribute pods across upgrade batches:

```yaml
spec:
  topologySpreadConstraints:
  - maxSkew: 1
    topologyKey: kubernetes.io/hostname
    whenUnsatisfiable: DoNotSchedule
    labelSelector:
      matchLabels:
        app: my-app
```

### 5. Implement upgrade-aware scheduling

**Add node taints during upgrade planning:**

```bash
# Before starting upgrade, taint nodes that will be upgraded
for node in $(kubectl get nodes --no-headers -o custom-columns=NAME:.metadata.name | grep old-nodepool); do
  kubectl taint node $node upgrade-pending=true:NoSchedule
done

# Untaint after each node completes
kubectl taint node NODE_NAME upgrade-pending-
```

## Monitoring the Fix

**Watch pod movements during upgrade:**
```bash
# Monitor which nodes pods are landing on
kubectl get pods -A -o wide --watch

# Check if pods are still getting shuffled
kubectl get events -A --field-selector reason=Killing --watch
```

**Verify upgrade progress:**
```bash
# Confirm new nodes are staying put
kubectl get nodes -o wide -L cloud.google.com/gke-nodepool --watch
```

## When to Use Each Approach

| Scenario | Best Solution |
|----------|---------------|
| **Small node pool (< 10 nodes)** | Increase `maxSurge`, set `maxUnavailable=0` |
| **Large node pool, plenty quota** | Blue-green upgrade strategy |
| **Limited quota/GPU nodes** | Node taints + careful surge settings |
| **Mission-critical workloads** | Blue-green + pod topology constraints |
| **Mixed workload cluster** | Node selectors + separate upgrade windows |

The `maxSurge` increase with `maxUnavailable=0` is usually the quickest fix - try that first and see if the musical chairs stops.
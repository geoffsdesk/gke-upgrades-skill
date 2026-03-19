# Node Pool Upgrade: "Musical Chairs" Pod Rescheduling Issue

This is a classic surge upgrade sequencing problem. GKE is creating new nodes and draining old ones simultaneously, but the scheduler doesn't prioritize already-upgraded nodes when rescheduling evicted pods.

## What's happening

1. **Surge upgrade creates new nodes** alongside old ones
2. **Scheduler sees all Ready nodes as equivalent** - doesn't distinguish "old" vs "new"
3. **Evicted pods land randomly** on any available node (including ones about to be drained)
4. **Pods get re-evicted** when their "temporary" node gets drained next
5. **Process repeats** until only new nodes remain

This causes unnecessary churn, extends upgrade time, and can trigger restart loops for sensitive workloads.

## Immediate fixes

### Option 1: Prefer already-upgraded nodes (recommended)

Force pods to prefer nodes at the target version:

```bash
# Add node affinity to critical workloads temporarily
kubectl patch deployment DEPLOYMENT_NAME -p '{
  "spec": {
    "template": {
      "spec": {
        "affinity": {
          "nodeAffinity": {
            "preferredDuringSchedulingIgnoredDuringExecution": [{
              "weight": 100,
              "preference": {
                "matchExpressions": [{
                  "key": "node.kubernetes.io/kubernetes-version",
                  "operator": "In",
                  "values": ["v1.XX.XX-gke.XXXX"]
                }]
              }
            }]
          }
        }
      }
    }
  }
}'
```

Replace `v1.XX.XX-gke.XXXX` with your target version.

### Option 2: Cordon old nodes proactively

```bash
# List nodes at old version
kubectl get nodes -l node.kubernetes.io/kubernetes-version!=v1.XX.XX-gke.XXXX

# Cordon them (prevents new scheduling, allows existing pods to run)
kubectl get nodes -l node.kubernetes.io/kubernetes-version!=v1.XX.XX-gke.XXXX -o name | \
  xargs kubectl cordon

# GKE will still drain them when it's their turn, but no new pods will land there
```

### Option 3: Reduce upgrade parallelism

```bash
# Lower maxSurge to create fewer nodes at once
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

This reduces the number of "about to be drained" nodes in the pool.

## Prevention strategies

### 1. Configure surge settings based on pool size

```bash
# Small pools (≤10 nodes): Conservative settings
--max-surge-upgrade 1 --max-unavailable-upgrade 0

# Medium pools (11-50 nodes): Moderate parallelism  
--max-surge-upgrade 2 --max-unavailable-upgrade 0

# Large pools (50+ nodes): Higher surge but still bounded
--max-surge-upgrade 5 --max-unavailable-upgrade 0
```

### 2. Use blue-green for critical stateful workloads

Blue-green eliminates the musical chairs problem entirely by creating a complete replacement pool:

```bash
# Create new pool at target version
gcloud container node-pools create POOL_NAME-v2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION \
  --num-nodes NUM_NODES \
  --machine-type MACHINE_TYPE

# Migrate workloads (cordon old, let workloads reschedule naturally or force)
kubectl cordon -l cloud.google.com/gke-nodepool=POOL_NAME

# Delete old pool when migration complete
gcloud container node-pools delete POOL_NAME --cluster CLUSTER_NAME --zone ZONE
```

### 3. Workload-specific anti-affinity

For workloads that can't tolerate multiple restarts:

```yaml
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              labelSelector:
                matchLabels:
                  app: my-app
              topologyKey: kubernetes.io/hostname
        nodeAffinity:
          # Prefer nodes at current target version
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            preference:
              matchExpressions:
              - key: node.kubernetes.io/kubernetes-version
                operator: In
                values: ["v1.XX.XX-gke.XXXX"]
```

## Monitoring the fix

```bash
# Watch pod distribution across node versions
kubectl get pods -A -o wide | \
  awk 'NR>1 {print $8}' | sort | uniq -c

# Check which nodes are being scheduled on
kubectl get events --field-selector reason=Scheduled -o custom-columns=NODE:.source.host --no-headers | \
  sort | uniq -c

# Monitor upgrade progress
watch 'kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion | sort -k2'
```

## Why this happens more in large clusters

- **More nodes = more opportunities for poor placement**
- **GKE's ~20 node upgrade parallelism** means many nodes in "transition" state simultaneously
- **Kubernetes scheduler is version-agnostic** - doesn't understand "this node will be drained soon"
- **Pod disruption budgets can force sub-optimal placement** if preferred nodes don't have capacity

The fundamental issue is that GKE's upgrade process is node-centric while pod scheduling is cluster-wide. The scheduler lacks awareness of the upgrade sequence, so manual intervention (affinity rules, cordoning) bridges this gap.
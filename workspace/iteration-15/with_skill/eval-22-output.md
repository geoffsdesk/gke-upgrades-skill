This is a classic node pool upgrade coordination issue! You're seeing pods bounce between nodes because GKE's drain process doesn't coordinate with the Kubernetes scheduler about which nodes are "safe" landing spots. Here's what's happening and how to fix it:

## Root Cause: Scheduler Blind Spots

The Kubernetes scheduler only sees nodes as "schedulable" or "unschedulable" (cordoned). During a surge upgrade:

1. **Node A** gets cordoned and starts draining → pods evicted
2. **Node B** is still schedulable (hasn't been cordoned yet) → scheduler places pods there  
3. **Node B** gets cordoned next → same pods evicted again
4. **Node C** becomes the new "available" target → pods move again

The scheduler has no visibility into GKE's upgrade plan, so it can't prefer already-upgraded nodes.

## Solutions (in order of preference)

### 1. **Increase maxSurge to create stable landing zones**

Create more upgraded nodes upfront so pods have safe places to land:

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 20% \
  --max-unavailable-upgrade 0
```

**Why this works:** With higher surge, GKE creates multiple new nodes before starting to drain old ones. Pods land on the new nodes and stay there.

**Sizing guidance:** 
- 20-node pool → `maxSurge=4` (20%) creates 4 upgraded nodes upfront
- 100-node pool → `maxSurge=10` (10%) creates 10 upgraded nodes upfront

### 2. **Use node affinity to prefer already-upgraded nodes**

Add a temporary node affinity rule to your workloads during upgrade:

```yaml
spec:
  affinity:
    nodeAffinity:
      preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        preference:
          matchExpressions:
          - key: node.kubernetes.io/instance-type
            operator: In
            values: [TARGET_NODE_IMAGE]  # e.g., "gke-1.32.1-gke.1000"
```

**Limitation:** Requires workload manifest changes and knowing the exact target node image.

### 3. **Switch to blue-green upgrade strategy**

Blue-green eliminates the musical chairs problem entirely:

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --strategy=BLUE_GREEN \
  --node-pool-soak-duration=1800s \
  --standard-rollout-policy=batch-node-count=5,batch-soak-duration=60s
```

**How it works:** Creates a completely new "green" node pool at target version, then drains the old "blue" pool. Pods move once to stable destinations.

**Trade-off:** Requires 2x capacity temporarily, higher cost during upgrade.

### 4. **Drain-first approach for resource-constrained environments**

If you can't afford surge nodes:

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

**How it works:** Drains one node completely before creating its replacement. Pods move once to other existing nodes, then the replacement comes online.

**Trade-off:** Temporary capacity reduction, but eliminates bouncing.

## Immediate Mitigation (if upgrade is already running)

You can't change surge settings mid-upgrade, but you can help the situation:

```bash
# Manually cordon nodes that will be upgraded soon
# This removes them from scheduler consideration
kubectl get nodes -l cloud.google.com/gke-nodepool=NODE_POOL_NAME \
  -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion

# Cordon nodes still on old version (they'll be upgraded next)
kubectl cordon NODE_NAME
```

## Prevention for Future Upgrades

1. **Default to 10-20% maxSurge** for stateless workloads
2. **Use blue-green** for stateful workloads or when pods are expensive to restart
3. **Monitor pod restart counts** during upgrades to detect bouncing early
4. **Stagger workload deployments** if possible - deploy some workloads with node affinity during upgrade windows

## Monitoring the Fix

Track whether pods are still bouncing:

```bash
# Watch pod restarts during upgrade
kubectl get pods -A -o custom-columns=NAME:.metadata.name,NAMESPACE:.metadata.namespace,RESTARTS:.status.containerStatuses[0].restartCount,NODE:.spec.nodeName

# Monitor node versions to see upgrade progress
watch 'kubectl get nodes -L cloud.google.com/gke-nodepool -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,POOL:.metadata.labels.cloud\.google\.com/gke-nodepool'
```

The root issue is that GKE's node upgrade orchestration and Kubernetes' pod scheduling happen independently. Higher surge creates better coordination by giving pods stable landing zones before the chaos starts.
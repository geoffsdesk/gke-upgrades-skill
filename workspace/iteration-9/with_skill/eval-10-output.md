# GKE Upgrade Plan: Standard Cluster with Spot VMs (1.31 → 1.32)

## Spot VM upgrade considerations

Spot VMs have unique behaviors during GKE upgrades that require specific planning:

### Key differences from on-demand upgrades

1. **Preemption during upgrade**: Spot VMs can be preempted by Google Cloud at any time during the upgrade process, independent of GKE's drain operations. This creates two potential disruption sources.

2. **No surge capacity guarantee**: When using `maxSurge > 0`, GKE requests new spot instances for the surge nodes. However, spot capacity availability varies by zone and machine type. If surge spot instances aren't available, the upgrade will stall.

3. **Replacement instance availability**: Even with `maxUnavailable` mode, replacement spot instances may not be immediately available after the old node is terminated.

## Recommended upgrade strategy for spot node pools

### Option 1: Conservative spot upgrade (recommended)
```bash
gcloud container node-pools update SPOT_NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1
```

**Why this works best for spot:**
- No dependency on surge spot capacity
- Drains one node at a time, terminates it, requests replacement
- If replacement spot capacity unavailable, only affects one node
- Slower but more reliable completion

### Option 2: Aggressive spot upgrade (if capacity is abundant)
```bash
gcloud container node-pools update SPOT_NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

**Use only if:**
- You've confirmed spot capacity availability in your zones/machine types
- You can tolerate upgrade failures requiring retry
- Your workloads can handle the extra disruption if surge nodes get preempted

## Workload resilience requirements

Since spot VMs add preemption risk on top of upgrade disruption:

### Critical workload protection
```yaml
# Ensure PDBs account for both upgrade and preemption
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: critical-app-pdb
spec:
  minAvailable: 2  # Always keep multiple replicas available
  selector:
    matchLabels:
      app: critical-app
```

### Node affinity strategy
```yaml
# Spread across spot and on-demand for critical workloads
spec:
  affinity:
    nodeAffinity:
      preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 50
        preference:
          matchExpressions:
          - key: cloud.google.com/gke-spot
            operator: DoesNotExist  # Prefer on-demand
      - weight: 30
        preference:
          matchExpressions:
          - key: cloud.google.com/gke-spot
            operator: Exists  # But allow spot for cost savings
```

## Pre-upgrade checklist additions for spot pools

```
Spot VM Specific Checks
- [ ] Current spot capacity availability confirmed in target zones
- [ ] Machine type spot availability verified (check quotas page)
- [ ] Critical workloads have replicas spread across spot + on-demand nodes
- [ ] PDBs configured to handle preemption + upgrade disruption simultaneously
- [ ] Workloads tested for rapid restart capability (spot best practice)
- [ ] Monitoring configured for spot preemption events
- [ ] Cluster autoscaler settings account for spot availability fluctuations
```

## Upgrade execution plan

### Step 1: Verify current spot distribution
```bash
# Check current node distribution
kubectl get nodes -l cloud.google.com/gke-spot=true -o wide
kubectl get nodes -l cloud.google.com/gke-spot!=true -o wide

# Check workload distribution
kubectl get pods -A -o wide | grep -E "spot|preemptible"
```

### Step 2: Configure conservative upgrade settings
```bash
# Set conservative settings for spot pool
gcloud container node-pools update SPOT_NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1

# Keep standard settings for on-demand pool
gcloud container node-pools update ON_DEMAND_NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

### Step 3: Upgrade control plane first
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32
```

### Step 4: Upgrade on-demand pool first
```bash
gcloud container node-pools upgrade ON_DEMAND_NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

### Step 5: Upgrade spot pool during low-traffic period
```bash
# Monitor spot capacity before starting
gcloud compute instances list --filter="scheduling.preemptible=true" --zones ZONE

gcloud container node-pools upgrade SPOT_NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

## Troubleshooting spot-specific issues

### Upgrade stalled due to no spot capacity
**Diagnose:**
```bash
gcloud container operations describe OPERATION_ID \
  --zone ZONE \
  --cluster CLUSTER_NAME

# Look for "no available zones" or "quota exceeded" in operation details
kubectl get events -A --field-selector reason=FailedCreatePodSandBox
```

**Fix:**
- Wait for spot capacity to become available (can take hours)
- Temporarily switch node pool to on-demand, upgrade, switch back
- Add additional zones to the node pool to increase capacity options

### Workloads stuck on terminating nodes
**Diagnose:**
```bash
# Check for pods on nodes being preempted AND upgraded
kubectl get pods -A -o wide | grep -E "Terminating|Pending"
kubectl get nodes -l cloud.google.com/gke-spot=true
```

**Fix:**
```bash
# Force delete stuck pods (they'll reschedule)
kubectl delete pod POD_NAME -n NAMESPACE --grace-period=0 --force
```

## Post-upgrade validation

```bash
# Verify spot nodes at target version
kubectl get nodes -l cloud.google.com/gke-spot=true \
  -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion

# Check workload distribution
kubectl get pods -A -o wide | grep -c spot
kubectl get pods -A -o wide | grep -c -v spot

# Confirm no stuck resources
kubectl get pods -A | grep -E "Pending|Terminating"
```

## Key recommendations summary

1. **Use `maxUnavailable` strategy for spot pools** - more reliable than surge
2. **Upgrade on-demand pools first** - provides stable capacity during spot pool upgrade
3. **Plan for longer upgrade time** - spot capacity constraints can cause delays
4. **Ensure workload resilience** - PDBs and multi-node distribution are critical
5. **Monitor spot capacity** - check availability before starting upgrade
6. **Schedule during low-traffic periods** - spot preemption + upgrade = double disruption risk

This approach balances cost savings from spot VMs with upgrade reliability and workload availability.
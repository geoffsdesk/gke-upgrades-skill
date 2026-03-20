Yes, you can proceed by switching from surge upgrade to an in-place upgrade strategy. This avoids needing extra quota but will cause temporary capacity loss. Here's how:

## Switch to maxUnavailable mode

```bash
# Change strategy to drain-first instead of surge-first
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1

# Resume the upgrade (if it's not automatically continuing)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

**What this does:**
- `maxSurge=0` = No extra nodes created (zero additional quota needed)
- `maxUnavailable=1` = Drains one node at a time, then creates its replacement
- Net effect: Always N-1 nodes during upgrade, but no quota overage

## Prepare for capacity reduction

Since you'll temporarily lose nodes during the upgrade:

```bash
# Scale down non-critical workloads first
kubectl scale deployment NON_CRITICAL_APP --replicas=0 -n NAMESPACE

# Check which pods can tolerate eviction
kubectl get pods -A -o wide | grep NODE_BEING_DRAINED

# Verify PDBs won't block drain with reduced capacity
kubectl get pdb -A -o wide
# Look for minAvailable that might be too restrictive
```

## Alternative: Blue-green with controlled timing

If you have quota in a different zone within the region:

```bash
# Create new pool in different zone (if quota available there)
gcloud container node-pools create NODE_POOL_NAME-v2 \
  --cluster CLUSTER_NAME \
  --zone ZONE_WITH_QUOTA \
  --node-version TARGET_VERSION \
  --num-nodes CURRENT_NODE_COUNT \
  --machine-type CURRENT_MACHINE_TYPE

# Wait for nodes ready, then migrate workloads
kubectl get nodes -l cloud.google.com/gke-nodepool=NODE_POOL_NAME-v2

# Cordon old pool
kubectl cordon -l cloud.google.com/gke-nodepool=NODE_POOL_NAME

# Delete old pool once workloads migrated
gcloud container node-pools delete NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE
```

## Monitor progress with reduced capacity

```bash
# Watch upgrade progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Monitor pod scheduling during capacity dip
kubectl get pods -A | grep Pending
kubectl get events -A --field-selector reason=FailedScheduling
```

The `maxUnavailable=1` approach is your safest bet - it guarantees the upgrade proceeds without quota issues, though you'll have temporary capacity reduction. Increase the number (e.g., `maxUnavailable=2`) only if you're confident your workloads can handle losing multiple nodes simultaneously.
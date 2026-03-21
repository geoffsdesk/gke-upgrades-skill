# GKE Node Pool Upgrade: Spot VM Considerations

## Spot VM upgrade behavior

Spot VMs in GKE behave **identically** to regular (on-demand) VMs during planned upgrades. The key insight: **surge upgrades create new VMs at the target version** — they don't modify existing VMs in-place. This means:

- Spot VMs are **not preempted** during GKE upgrades
- Both spot and on-demand nodes follow the same surge upgrade process: cordon → drain → terminate → replace
- Your `maxSurge`/`maxUnavailable` settings apply equally to both VM types

## Upgrade plan for mixed spot/on-demand pool

### Pre-upgrade configuration
```bash
# Check current surge settings
gcloud container node-pools describe NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --format="value(upgradeSettings)"

# Recommended settings for mixed pools
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

**Rationale:** `maxSurge=2, maxUnavailable=0` ensures continuous capacity during the upgrade. Since spot availability can be unpredictable, having surge capacity prevents service disruption if some replacement nodes can't be provisioned immediately.

### Workload placement strategy

**For spot-tolerant workloads:**
- Use node affinity/taints to prefer spot nodes
- Ensure PDBs allow some disruption (spot preemptions can happen independently of upgrades)
- Set appropriate `terminationGracePeriodSeconds` (spot gives 30 seconds notice)

**For spot-intolerant workloads:**
- Use node selectors to pin to on-demand nodes
- Consider separating into dedicated on-demand-only pools for cleaner upgrade control

### Capacity considerations

**Spot availability risks:**
- New spot VMs might not be available in your zone during upgrade
- GKE will retry spot creation but may fall back to on-demand if spot quota is exhausted
- **Mitigation:** Ensure adequate on-demand quota as backup, or temporarily increase `maxSurge` for faster completion

**Cost optimization:**
- Spot replacement VMs will honor your original spot configuration
- No cost impact during upgrade — you're not paying extra for surge capacity if using spot
- Consider upgrading during off-peak hours when spot availability is typically better

## Upgrade execution

### Control plane first (required order)
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32
```

### Node pool upgrade
```bash
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

### Monitor progress
```bash
# Watch node replacement
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-preemptible'

# Check for stuck pods
kubectl get pods -A | grep -v Running | grep -v Completed

# Monitor spot vs on-demand distribution
kubectl get nodes -l cloud.google.com/gke-preemptible=true --no-headers | wc -l
```

## Potential issues and fixes

### Issue: Spot surge nodes can't be provisioned
**Symptom:** Upgrade stalls, some nodes remain on old version
**Diagnosis:**
```bash
kubectl get events -A --field-selector reason=FailedScheduling
gcloud compute instances list --filter="name~NODE_POOL_NAME"
```

**Fix:** Temporarily switch to on-demand for surge nodes, or increase the surge window:
```bash
# Increase maxSurge to create more parallel replacement attempts
gcloud container node-pools update NODE_POOL_NAME \
  --max-surge-upgrade 3
```

### Issue: Workloads stuck on terminating spot nodes
**Symptom:** Pods remain on cordoned nodes despite drain
**Fix:** Check PDBs and ensure workloads aren't pinned to specific nodes:
```bash
kubectl get pdb -A -o wide
kubectl describe pod STUCK_POD -n NAMESPACE | grep -A 5 "Node-Selectors\|Tolerations"
```

## Post-upgrade validation

```bash
# Verify version consistency
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].version)"

# Confirm spot/on-demand ratio maintained
kubectl get nodes -L cloud.google.com/gke-preemptible -o wide

# Check workload distribution
kubectl get pods -A -o wide | grep NODE_NAME
```

## Key takeaway

**Spot VMs don't complicate GKE upgrades** — they follow the same surge upgrade process as on-demand VMs. The main consideration is ensuring adequate surge capacity given spot availability constraints. Your existing PDBs and workload resilience patterns for handling spot preemptions will work the same during upgrades.

Would you like me to create a specific runbook with your cluster details, or do you have questions about handling particular workloads during this upgrade?
# GKE Node Pool Upgrade Strategy

Provides workload-aware node pool upgrade planning for Standard GKE clusters. Not applicable to Autopilot (Google manages node upgrades).

## Strategy Selection

### Surge Upgrades (Default)

Best for most workloads. GKE creates extra nodes, migrates workloads, removes old nodes.

| Pool Type | maxSurge | maxUnavailable | Why |
|-----------|----------|----------------|-----|
| General-purpose / stateless | 2-3 | 0 | Faster upgrades, zero disruption |
| Stateful / database | 1 | 0 | Conservative, let PDBs protect data |
| GPU / accelerator | 1 | 0 | GPUs are expensive, minimize temporary overcapacity |
| Large pools (50+ nodes) | 10-20 | 0 | Reasonable speed without excessive surge cost |
| Cost-sensitive (disruption OK) | 0 | 1-3 | No extra nodes, but pods get evicted |

Configure per pool:
```bash
gcloud container node-pools update POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade MAX_SURGE \
  --max-unavailable-upgrade MAX_UNAVAILABLE
```

### Blue-Green Upgrades

Best when you need instant rollback capability or have fragile stateful workloads.

- Creates a complete new set of nodes alongside existing ones
- Temporarily doubles node count (need quota and IP space)
- Control batch size: `--batch-node-count` or `--batch-percent`
- Set soak time: `--batch-soak-duration` for validation between batches

```bash
gcloud container node-pools update POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-blue-green-upgrade \
  --node-pool-soak-duration "3600s" \
  --standard-rollout-policy batch-node-count=3,batch-soak-duration=300s
```

## Upgrade Ordering

When a cluster has multiple node pools, upgrade in this order:

1. **General-purpose / stateless pools** -- Fastest, validates the version works
2. **Stateful / database pools** -- After stateless succeeds, with PDB protection
3. **GPU / accelerator pools** -- Last, after confirming driver compatibility

Rationale: if the upgrade hits issues on stateless pools, you haven't disrupted your most sensitive workloads yet.

## Workload-Specific Guidance

### StatefulSets / Databases
- Verify PV reclaim policy is `Retain` (not `Delete`)
- Take backups before starting
- Check operator version compatibility with target K8s version
- Monitor replication lag during drain
- Use `maxSurge=1, maxUnavailable=0`

### GPU Workloads
- Verify CUDA toolkit compatibility with new NVIDIA driver version
- Check GKE's GPU driver management mode (Google-managed vs customer-managed)
- Schedule upgrades during model training gaps
- Test in staging with representative GPU workloads first

### Long-Running Batch Jobs
- Consider blue-green with extended soak time
- Or cordon nodes manually and wait for jobs to complete before draining
- GKE waits up to 1 hour per node during surge upgrades

## Monitoring Progress

```bash
# Watch node versions during upgrade
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Check for stuck pods
kubectl get pods -A | grep -E "Terminating|Pending|ContainerCreating"

# Check GKE operation status
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --limit=5
```

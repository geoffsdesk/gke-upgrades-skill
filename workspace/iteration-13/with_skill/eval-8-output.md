For your Cassandra ring with 9 nodes on local SSDs, I **strongly recommend the surge upgrade strategy** over blue-green. Here's why and how to configure it:

## Why Surge Over Blue-Green for Cassandra

**Surge is better because:**
- **Cost efficiency:** Blue-green would require 18 nodes (double your cluster) during upgrade
- **Local SSD handling:** Cassandra can handle single-node failures gracefully through replication
- **Controlled disruption:** With proper surge settings, only 1 node restarts at a time
- **Simpler rollback:** Less complex than managing two full rings

**Blue-green downsides for your use case:**
- **Expensive:** 2x compute cost during upgrade window
- **Data migration complexity:** Moving Cassandra data between node pools is non-trivial
- **Split-brain risk:** Two rings could cause consistency issues

## Recommended Configuration

```bash
# Configure conservative surge settings for Cassandra
gcloud container node-pools update cassandra-pool \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Verify current settings
gcloud container node-pools describe cassandra-pool \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --format="value(upgradeSettings.maxSurge,upgradeSettings.maxUnavailable)"
```

## Pre-Upgrade Checklist for Cassandra

```
Cassandra-Specific Pre-Upgrade Checklist
- [ ] Cluster health: `nodetool status` shows all nodes UP/NORMAL
- [ ] Replication factor ≥3 with proper placement strategy
- [ ] No pending repairs: `nodetool compactionstats`
- [ ] Recent backup completed (snapshots + incremental)
- [ ] PodDisruptionBudget configured:
      maxUnavailable: 1 (allows only 1 pod eviction at a time)
- [ ] Cassandra graceful shutdown configured:
      terminationGracePeriodSeconds: 300 (5 minutes minimum)
- [ ] Local SSD provisioner properly configured for data persistence
- [ ] Anti-affinity rules ensure no two Cassandra pods on same node
```

## PodDisruptionBudget Configuration

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: cassandra-pdb
  namespace: cassandra
spec:
  maxUnavailable: 1  # Only 1 Cassandra node down at a time
  selector:
    matchLabels:
      app: cassandra
```

## Complete Upgrade Runbook

### 1. Pre-flight Checks
```bash
# Verify Cassandra cluster health
kubectl exec -it cassandra-0 -n cassandra -- nodetool status

# Check current GKE versions
gcloud container clusters describe YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --format="table(name, currentMasterVersion, nodePools[].version)"

# Verify PDB is active
kubectl get pdb cassandra-pdb -n cassandra -o wide
```

### 2. Configure Surge Settings
```bash
# Set conservative surge for stateful workload
gcloud container node-pools update cassandra-pool \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### 3. Control Plane Upgrade (if needed)
```bash
gcloud container clusters upgrade YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --master \
  --cluster-version TARGET_VERSION
```

### 4. Node Pool Upgrade
```bash
# Start the upgrade
gcloud container node-pools upgrade cassandra-pool \
  --cluster YOUR_CLUSTER_NAME \
  --zone YOUR_ZONE \
  --cluster-version TARGET_VERSION

# Monitor progress (expect ~45-60 minutes for 9 nodes)
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool=cassandra-pool'
```

### 5. Monitor Cassandra Health During Upgrade
```bash
# Watch Cassandra ring status
watch 'kubectl exec cassandra-0 -n cassandra -- nodetool status'

# Monitor pod restart sequence
kubectl get pods -n cassandra -w

# Check no data loss
kubectl exec cassandra-0 -n cassandra -- nodetool repair --validate
```

## Expected Upgrade Timeline

With your configuration:
- **1 node at a time:** maxSurge=1, maxUnavailable=0
- **Per-node time:** ~5-7 minutes (drain + provision + startup)
- **Total duration:** ~45-60 minutes for 9 nodes
- **Cassandra availability:** 8/9 nodes always available

## Troubleshooting

If the upgrade gets stuck:

**1. Check if Cassandra pod won't drain:**
```bash
kubectl describe pod STUCK_POD -n cassandra
# Look for deletion timestamp vs. termination grace period
```

**2. PDB too restrictive:**
```bash
kubectl get pdb cassandra-pdb -n cassandra
# Should show ALLOWED DISRUPTIONS: 1
```

**3. Local SSD attachment issues:**
```bash
kubectl get events -n cassandra --field-selector reason=FailedAttachVolume
```

## Why This Works for Cassandra

1. **Replication tolerance:** Cassandra RF≥3 handles single node failure
2. **Local SSD preservation:** Surge creates new node, data rebuilds from replicas
3. **Minimal blast radius:** Only 1/9 nodes affected at any time
4. **Fast recovery:** Cassandra streaming rebuilds the node automatically

This approach balances upgrade safety with Cassandra's built-in resilience, avoiding the cost and complexity of blue-green while maintaining data availability.
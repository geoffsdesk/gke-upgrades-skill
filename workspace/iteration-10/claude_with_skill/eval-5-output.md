You've hit GKE's version skew limit - nodes can't be more than 2 minor versions behind the control plane. With CP at 1.31 and nodes at 1.28, you're exactly at the boundary (1.28 → 1.29 → 1.30 → 1.31 = 3 steps). This triggers warnings and will eventually force an upgrade.

## What you're dealing with

**Immediate risks:**
- **API compatibility issues** - Your 1.28 kubelets may not understand newer APIs served by the 1.31 control plane
- **Feature drift** - Missing CSI drivers, security patches, kubelet features
- **Forced upgrade incoming** - GKE will automatically upgrade the node pool to resolve skew, potentially at an inconvenient time
- **Support limitations** - Mixed version clusters have limited support paths

**How this happened:**
- Control plane auto-upgraded through maintenance windows
- Node pool had auto-upgrade disabled or maintenance exclusions blocking it
- Possibly on legacy "No channel" with per-nodepool upgrade controls

## Fix Strategy

You need to upgrade that node pool to at least 1.29, but I recommend going directly to 1.31 to match the control plane. Node pools support skip-level upgrades (N+2), so you can go 1.28 → 1.31 in one step.

### Immediate Action Plan

```bash
# 1. Check current state
gcloud container clusters describe CLUSTER_NAME --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# 2. Verify 1.31 is available for node pools
gcloud container get-server-config --zone ZONE \
  --format="yaml(validNodeVersions)" | grep "1.31"

# 3. Configure upgrade strategy (adjust for your workloads)
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# 4. Execute the upgrade (1.28 → 1.31 skip-level)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.xxxx  # Use specific patch available
```

### Pre-upgrade checklist for this specific scenario

```markdown
Emergency Node Pool Upgrade - Version Skew Fix
- [ ] Cluster: ___ | CP: 1.31 | Problem node pool: 1.28
- [ ] Workload inventory on the 1.28 pool (what's running there?)
- [ ] PDBs reviewed - not overly restrictive for pod eviction
- [ ] No bare pods on the problem node pool
- [ ] Backup/checkpoint any stateful workloads on 1.28 nodes
- [ ] Surge strategy chosen based on workload type:
      - Stateless: maxSurge=2+, maxUnavailable=0 (faster)
      - Stateful: maxSurge=1, maxUnavailable=0 (safer)
      - GPU: maxSurge=0, maxUnavailable=1 (quota constrained)
- [ ] Maintenance window scheduled if this is production
```

### Monitor the upgrade

```bash
# Watch node versions change
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Check for stuck pods during drain
kubectl get pods -A | grep -E "Terminating|Pending"

# Monitor the operation
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --limit=3
```

## Why skip-level (1.28 → 1.31) is recommended

- **Faster**: One upgrade cycle instead of three (1.28→1.29→1.30→1.31)
- **Less disruption**: Pods restart once, not three times  
- **GKE supported**: Node pools specifically support N+2 upgrades
- **Eliminates skew immediately**: Gets you back to a supported configuration

## Prevent this in the future

**If you're on "No channel"** (legacy static version):
```bash
# Migrate to Regular channel for automatic lifecycle management
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular
```

**If you're on a release channel** but have exclusions:
- Review your maintenance exclusion scope - you may have "no minor or node upgrades" when you only need "no minor upgrades"
- Consider using maintenance windows instead of blanket exclusions
- Set up monitoring for version skew warnings

**Ongoing monitoring:**
```bash
# Check for skew weekly
gcloud container clusters describe CLUSTER_NAME --zone ZONE \
  --format="table(nodePools[].name, nodePools[].version, currentMasterVersion)"
```

The upgrade should take 30-60 minutes depending on your node count and surge settings. The version skew warnings will disappear once all nodes reach 1.29+, and you'll be back to a fully supported configuration at 1.31.
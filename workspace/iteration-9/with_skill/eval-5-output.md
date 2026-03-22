You're dealing with **version skew violation** - your node pool is 3 minor versions behind the control plane (1.28 vs 1.31), which exceeds GKE's maximum supported skew of 2 minor versions.

## What you're facing

**Immediate risks:**
- API compatibility issues between kubelet (1.28) and kube-apiserver (1.31)
- Potential pod scheduling failures
- Degraded cluster functionality
- Security vulnerabilities (1.28 is likely approaching/past End of Support)

**Root cause:** This usually happens when:
- Node pool auto-upgrades were disabled or excluded
- Manual upgrades skipped the node pools
- PDB or resource constraints repeatedly blocked node pool upgrades

## Fix: Emergency node pool upgrade

You need to get that node pool to at least 1.29 immediately. Here's the recovery runbook:

### 1. Pre-flight assessment

```bash
# Check current state
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Identify the problematic node pool
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE

# Check available versions
gcloud container get-server-config --zone ZONE \
  --format="yaml(validNodeVersions)" | head -20
```

### 2. Clear any upgrade blockers

```bash
# Check for restrictive PDBs
kubectl get pdb -A -o wide | grep -E "0|0%"

# Look for bare pods that can't be rescheduled
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# Check cluster resource utilization
kubectl top nodes
```

### 3. Configure surge settings for fastest recovery

```bash
# Set aggressive surge for speed (adjust based on your quota)
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0
```

### 4. Upgrade in steps (recommended path)

**Option A: Skip-level upgrade (fastest)**
```bash
# Jump directly to 1.30 or 1.31 (if available for nodes)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30.x-gke.xxxx
```

**Option B: Sequential upgrades (safer)**
```bash
# Step 1: 1.28 → 1.29
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.29.x-gke.xxxx

# Wait for completion, then step 2: 1.29 → 1.30
# (Repeat until within skew limits)
```

### 5. Monitor progress

```bash
# Watch node versions during upgrade
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Check upgrade operation status
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --limit=3
```

### 6. Validate after upgrade

```bash
# Confirm version skew resolved
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(nodePools[].name, nodePools[].version, currentMasterVersion)"

# Check cluster health
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed
```

## Prevention for the future

**Immediate:**
- Enable auto-upgrades on this node pool (unless you have specific reasons not to)
- Set up maintenance windows aligned with your change windows
- Configure appropriate maintenance exclusions if you need control

```bash
# Re-enable auto-upgrade
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-autoupgrade

# Set maintenance window
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start 2024-01-01T02:00:00Z \
  --maintenance-window-end 2024-01-01T06:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"
```

**Longer term:**
- Monitor the GKE deprecation insights dashboard
- Set up Cloud Monitoring alerts for version skew
- Review your release channel strategy - consider Regular or Stable channel with maintenance exclusions rather than disabling auto-upgrades entirely

## If the upgrade gets stuck

Common issues during emergency upgrades:
1. **PDB blocking drain** - Temporarily relax with `kubectl patch pdb`
2. **Resource constraints** - Increase `maxSurge` or scale down non-critical workloads
3. **Long-running pods** - May need to manually drain nodes if termination takes too long

The key is getting that node pool to at least 1.29 ASAP to restore supported version skew. Then you can plan a more methodical upgrade to catch up fully.

How large is this node pool and what type of workloads are running on it? That'll help me give more specific surge/strategy recommendations.
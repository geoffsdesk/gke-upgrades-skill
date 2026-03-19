You're in a **version skew violation** — node pools can't be more than 2 minor versions behind the control plane. With control plane at 1.31 and nodes at 1.28, you're at the 3-version limit where things start breaking.

## What you're dealing with

**Immediate risks:**
- API compatibility issues (1.28 kubelet may not understand 1.31 API responses)
- Workload scheduling problems
- Security vulnerabilities in the old node version
- Potential cluster instability

**Why this happened:**
- Control plane auto-upgraded (or was manually upgraded) but node pools were left behind
- Node pool upgrades may have been paused/excluded or failed silently

## Fix: Emergency node pool upgrade

You need to upgrade that node pool immediately. Here's the runbook:

### 1. Pre-flight assessment

```bash
# Confirm the version skew
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Check which pools are affected
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE

# Verify cluster health before touching anything
kubectl get nodes -o wide
kubectl get pods -A | grep -v Running | grep -v Completed
```

### 2. Choose upgrade path

**Option A (Recommended): Direct upgrade 1.28→1.31**
- Faster, gets you compliant immediately  
- Higher risk since you're skipping versions

**Option B (Conservative): Sequential 1.28→1.29→1.30→1.31**
- Safer for catching compatibility issues
- Takes longer, multiple maintenance windows

Given the skew violation, I recommend **Option A** unless you have particularly sensitive workloads.

### 3. Configure surge settings

Set conservative surge for the emergency upgrade:

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### 4. Execute the upgrade

```bash
# Check available versions first
gcloud container get-server-config --zone ZONE \
  --format="yaml(validNodeVersions)"

# Upgrade to 1.31 (match control plane)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.X-gke.XXXX

# Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
```

### 5. Validation

```bash
# Confirm version alignment
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion,nodePools[].version)"

# Check cluster health
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed

# Verify workloads
kubectl get deployments -A
```

## Preventing this in the future

1. **Enable maintenance windows** to control when auto-upgrades happen:
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start 2024-01-01T02:00:00Z \
  --maintenance-window-end 2024-01-01T06:00:00Z \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"
```

2. **Monitor version skew** with alerting on the `container/cluster_version_skew` metric

3. **Coordinate upgrades** — when control plane upgrades, schedule node pool upgrades within days, not weeks

## If the upgrade fails

Common issues with large version jumps:
- **Deprecated APIs**: Check `kubectl get --raw /metrics | grep deprecated`
- **Admission webhooks**: May reject 1.31 pod specs
- **PDBs**: Might be too restrictive for drain

See the troubleshooting section if you hit issues, but start the upgrade now — the version skew is a bigger risk than upgrade complications.

**Timeline expectation**: Plan for 1-3 hours depending on node pool size and workload complexity.
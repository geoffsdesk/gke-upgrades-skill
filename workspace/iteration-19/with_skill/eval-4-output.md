# GKE Control Plane Upgrade Plan: 1.31 → 1.32

## What to Expect (Regional Cluster Advantage)

**Good news: You'll have ZERO API server downtime.** Here's why:

- **Regional clusters** have multiple control plane replicas across different zones
- During upgrade, GKE upgrades one replica at a time while others remain available
- Your cluster API remains fully accessible throughout the process
- Only brief (~30 seconds) leadership transitions as replicas restart
- Workloads continue running uninterrupted

**Contrast with zonal clusters:** Zonal clusters have a single control plane replica, causing 3-5 minutes of API unavailability during upgrade.

## Pre-Flight Checklist

```markdown
- [ ] Cluster: YOUR_CLUSTER | Mode: Standard | Channel: Regular
- [ ] Current version: 1.31 | Target version: 1.32
- [ ] Regional cluster confirmed (zero API downtime expected)

Compatibility Checks
- [ ] 1.32 available in Regular channel
- [ ] No deprecated API usage
- [ ] Release notes reviewed for breaking changes
- [ ] Node version skew acceptable (nodes can be up to 2 minor versions behind CP)
```

## Step-by-Step Runbook

### 1. Pre-flight Verification

```bash
# Verify current cluster state
gcloud container clusters describe YOUR_CLUSTER_NAME \
  --region us-central1 \
  --format="table(name, currentMasterVersion, nodePools[].version, location)"

# Check available versions in Regular channel
gcloud container get-server-config --region us-central1 \
  --format="yaml(channels)" | grep -A 10 "REGULAR"

# Check for deprecated API usage (most common upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Verify cluster health
kubectl get nodes
kubectl get pods -n kube-system | grep -v Running
```

### 2. Control Plane Upgrade

```bash
# Trigger control plane upgrade (this bypasses maintenance windows)
gcloud container clusters upgrade YOUR_CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version 1.32

# Expected output:
# "Master of cluster [YOUR_CLUSTER_NAME] will be upgraded from version [1.31.x] to version [1.32.x]. This operation is long-running and will block other operations on the cluster (including delete) until it has run to completion."
```

**Timeline:** Expect 15-20 minutes for the control plane upgrade to complete.

### 3. Monitor Progress

```bash
# Check upgrade progress
gcloud container operations list \
  --region us-central1 \
  --filter="targetLink ~ YOUR_CLUSTER_NAME AND operationType=UPGRADE_MASTER"

# Verify control plane version (wait until upgrade completes)
gcloud container clusters describe YOUR_CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion)"

# Check system component health
kubectl get pods -n kube-system
kubectl get nodes  # Node versions will still be 1.31 - that's expected
```

### 4. Validation Commands

After control plane upgrade completes:

```bash
# Confirm API server responsiveness
kubectl cluster-info
kubectl get ns

# Verify system pods restarted successfully
kubectl get pods -n kube-system | grep -v Running

# Check for any webhook or admission controller issues
kubectl get events -n kube-system --sort-by='.lastTimestamp' | tail -10
```

## What About Node Pools?

**Important:** This upgrade only affects the control plane. Your node pools will remain at 1.31, which is perfectly fine - GKE supports nodes up to 2 minor versions behind the control plane.

**Node pool upgrade options:**
1. **Let auto-upgrade handle it** (recommended): Nodes will automatically upgrade to 1.32 based on your maintenance window
2. **Manual upgrade later**: Upgrade node pools when convenient using the node pool upgrade process

## Two-Step Rollback Option (1.33+ Feature Preview)

Since you're upgrading to 1.32, you won't have access to the new two-step upgrade feature that allows rollback during a soak period. That feature requires upgrading from 1.33+. However, control plane patch downgrades within 1.32 are possible if needed.

## Potential Issues & Mitigations

**Most likely issue: Deprecated API usage**
- If GKE detects deprecated APIs, the upgrade may pause
- Check the GKE console for deprecation insights
- Fix deprecated API calls before retrying

**Admission webhooks compatibility:**
- Cert-manager, Istio, or other webhooks may need updates
- Test webhook functionality after upgrade
- Have webhook version compatibility confirmed beforehand

## Recovery Plan

If issues arise during or after upgrade:

1. **Control plane issues**: Check Cloud Logging for cluster events
2. **System pod failures**: Restart problematic pods in kube-system namespace
3. **Webhook failures**: Temporarily patch webhook configurations to `failurePolicy: Ignore`
4. **API compatibility**: Review application logs for 4xx errors indicating API changes

## Summary

Your regional cluster architecture gives you the best upgrade experience - zero API downtime with automatic high availability during the control plane upgrade. The process is safe and straightforward for control plane-only upgrades.

Ready to proceed? The commands above will safely upgrade your control plane from 1.31 to 1.32 with zero downtime.
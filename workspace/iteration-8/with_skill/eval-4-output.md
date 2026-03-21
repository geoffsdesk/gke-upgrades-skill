# Control Plane Upgrade Plan: 1.31 → 1.32

## What happens during control plane upgrade

**Good news: Zero API server downtime.** GKE control plane upgrades are designed for high availability:

- **Regional clusters** (like yours) maintain 3 control plane replicas across zones
- During upgrade, replicas are upgraded one at a time with health checks between each
- The API server remains available throughout - you may see brief (~seconds) increased latency but no connection failures
- Total upgrade time: typically 10-15 minutes for regional clusters
- Your workloads continue running normally - this only affects the Kubernetes API, not your applications

## Pre-flight checks

```bash
# Verify target version is available in Regular channel
gcloud container get-server-config --region us-central1 \
  --format="yaml(channels.regular.validVersions)" | grep "1.32"

# Check current cluster state
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="table(name, currentMasterVersion, status, location)"

# Verify cluster health
kubectl get nodes
kubectl get pods -n kube-system | grep -v Running

# Check for deprecated API usage (most common upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
```

## Upgrade commands

```bash
# Upgrade control plane to 1.32 (latest patch in Regular channel)
gcloud container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version 1.32

# Monitor progress
gcloud container operations list --region us-central1 --filter="name:operation-*"

# Verify completion
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion)"
```

## Post-upgrade validation

```bash
# Confirm API server responding
kubectl cluster-info
kubectl get nodes

# Check system pods
kubectl get pods -n kube-system | grep -v Running

# Verify no workload disruption
kubectl get pods -A | grep -v Running | grep -v Completed
```

## Important notes

1. **Node pools stay at 1.31** - Control plane upgrade doesn't touch your nodes. You'll upgrade node pools separately after validating the control plane.

2. **Version skew is fine** - Nodes can be up to 2 minor versions behind the control plane, so 1.31 nodes with 1.32 control plane is fully supported.

3. **No maintenance window needed** - Control plane upgrades can run anytime since there's no downtime. Manual upgrades also bypass maintenance windows.

4. **Auto-upgrade will catch up** - Since you're on Regular channel, auto-upgrade will eventually move you to 1.32 anyway. This just gets you there on your timeline.

## What if something goes wrong?

- **During upgrade**: The operation will automatically rollback if pre-flight checks fail
- **After upgrade**: Control plane patch downgrades are supported if needed (minor downgrades require GKE support)
- **API access issues**: Your regional cluster has 3 replicas, so connectivity should remain stable

This is a low-risk operation. The control plane upgrade is completely separate from your workload nodes and designed for zero downtime.
# GKE Control Plane Upgrade: 1.31 → 1.32

## Control Plane Availability During Upgrade

**Good news: Regional GKE clusters have NO control plane downtime during upgrades.** Here's what happens:

- **Regional clusters:** Multiple API server replicas across zones. During upgrade, GKE performs a rolling upgrade of API servers - some remain available while others upgrade. Your `kubectl` commands and workloads continue without interruption.
- **Upgrade duration:** Control plane upgrades typically take 10-15 minutes for the version change to complete.
- **API server load balancing:** The regional cluster's load balancer automatically routes requests to healthy API servers during the rolling upgrade.

Your workloads keep running normally - only the control plane version changes. Node pools stay at 1.31 until you upgrade them separately.

## Pre-flight Verification

First, let's confirm 1.32 is available in Regular channel and check your cluster state:

```bash
# Check available versions in Regular channel
gcloud container get-server-config --region us-central1 \
  --format="yaml(channels.regular)"

# Current cluster state
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="table(name, currentMasterVersion, nodePools[].version)"

# Verify cluster health
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed

# Check for deprecated API usage (common upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
```

## Control Plane Upgrade Commands

```bash
# Upgrade control plane to 1.32
gcloud container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version 1.32

# The command will prompt for confirmation. Type 'y' to proceed.
# Expected output: "Upgrading CLUSTER_NAME... This operation may take several minutes."
```

## Monitor Progress

```bash
# Check upgrade status (run periodically)
gcloud container operations list \
  --region us-central1 \
  --filter="targetLink:CLUSTER_NAME AND operationType:UPGRADE_MASTER"

# Verify completion
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion)"

# Confirm system pods are healthy after upgrade
kubectl get pods -n kube-system
```

## What to Expect

1. **Start:** Command initiates the rolling upgrade of API server replicas
2. **During (10-15 min):** 
   - API remains available throughout
   - You can continue using `kubectl` 
   - Workloads keep running normally
   - Some API requests may have slightly higher latency
3. **Complete:** Control plane shows version 1.32, nodes remain at 1.31

## Important Notes

- **Nodes stay at 1.31** - you'll need to upgrade node pools separately afterward
- **Version skew:** Nodes can be up to 2 minor versions behind the control plane, so 1.31 nodes with 1.32 control plane is fully supported
- **Breaking changes:** Review the [GKE 1.32 release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes) for any breaking changes between 1.31 → 1.32
- **Auto-upgrade:** Your Regular channel cluster will auto-upgrade to 1.32 soon anyway - doing it manually just gives you control over timing

## Next Steps After Control Plane Upgrade

Once the control plane is at 1.32, you can upgrade your node pools. Since you're on Standard GKE, you have full control over node pool upgrade strategy (surge settings, timing, etc.). Let me know when you're ready to plan the node pool upgrades!

Would you like me to also prepare a node pool upgrade plan, or do you want to handle the control plane upgrade first and then circle back?
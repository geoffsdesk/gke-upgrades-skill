# GKE Control Plane Upgrade: Regional Standard Cluster

## What Will Happen During Your Upgrade

**Good news: You'll have ZERO API server downtime.** Regional Standard clusters have multiple control plane replicas across zones, and GKE upgrades them one at a time. Here's the exact process:

1. **High availability maintained**: Your cluster has 3 control plane replicas (one per zone in us-central1-a, us-central1-b, us-central1-c)
2. **Rolling upgrade**: GKE upgrades one replica at a time, keeping 2/3 available
3. **Each replica downtime**: ~3-5 minutes per replica while it restarts
4. **Total upgrade time**: ~15-20 minutes end-to-end
5. **Workload impact**: None — your pods keep running normally

**During the upgrade you CAN:**
- Deploy new workloads
- Scale existing deployments
- Run kubectl commands
- Access the Kubernetes API normally

The remaining healthy replicas handle all API traffic seamlessly.

## Pre-Flight Commands

```bash
# Verify current version and channel
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="table(name, currentMasterVersion, releaseChannel.channel, status)"

# Check if 1.32 is available in Regular channel
gcloud container get-server-config --region us-central1 \
  --format="yaml(channels.REGULAR)"

# Check for deprecated API usage (common upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Verify cluster health before starting
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed
```

## Control Plane Upgrade Commands

```bash
# Upgrade control plane to 1.32 (replace CLUSTER_NAME with your actual cluster name)
gcloud container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version 1.32

# Monitor upgrade progress
gcloud container operations list \
  --region us-central1 \
  --filter="targetLink:CLUSTER_NAME AND operationType:UPGRADE_MASTER" \
  --limit=1

# Alternative: watch in the console
echo "Monitor at: https://console.cloud.google.com/kubernetes/clusters/details/us-central1/CLUSTER_NAME"
```

## Validation Commands (run after ~20 minutes)

```bash
# Confirm control plane upgraded successfully
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion)"

# Verify system pods are healthy
kubectl get pods -n kube-system

# Check cluster can still schedule pods
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "API server working"

# Verify nodes can still communicate with control plane
kubectl get nodes -o wide
```

## Two-Step Upgrade Option (Preview - Rollback Safety)

If your team wants maximum safety, consider the **two-step control plane upgrade** for 1.31→1.32:

```bash
# Step 1: Binary upgrade with rollback capability (6h-7d soak period)
gcloud beta container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version 1.32 \
  --control-plane-soak-duration 24h

# During soak period: test thoroughly, can still rollback to 1.31 if issues found

# Step 2: Complete the upgrade (enables 1.32 features, no rollback after this)
gcloud beta container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --complete-cluster-version-upgrade
```

## Next Steps: Node Pool Upgrades

**Important**: Your nodes will remain at 1.31 after the control plane upgrade. This is perfectly fine — GKE supports up to 2 minor version skew. Plan your node pool upgrades separately when ready:

```bash
# Later, when ready to upgrade node pools:
gcloud container node-pools list --cluster CLUSTER_NAME --region us-central1
# Then upgrade each pool individually
```

## What Could Go Wrong (and how to handle it)

1. **Deprecated API usage**: GKE automatically pauses upgrades if deprecated APIs are detected. Check the deprecation insights in your GKE console.

2. **Admission webhooks**: If you have cert-manager or other admission controllers, they might need updates for 1.32 compatibility.

3. **Custom operators**: Verify any Istio, Prometheus operators, etc. support Kubernetes 1.32.

**Your regional setup provides excellent safety** — even if something unexpected happens during the control plane upgrade, you maintain API availability throughout the process.

Ready to proceed? The upgrade is very low-risk for regional Standard clusters.
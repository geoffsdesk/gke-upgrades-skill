# GKE Control Plane Upgrade: Regional Standard Cluster

Good news! **Regional GKE clusters have zero API server downtime during control plane upgrades.** Your concerns about API server availability are resolved by your cluster architecture.

## What Happens During the Upgrade

**Regional cluster behavior:**
- Your cluster has **multiple control plane replicas** across 3 zones in us-central1
- GKE upgrades **one replica at a time** while the others remain available
- The API server **stays highly available** throughout the entire process
- **No service interruption** for existing workloads or API calls
- Upgrade typically takes 15-30 minutes total

**During the upgrade you CAN:**
- Deploy new workloads
- Modify existing workloads  
- Make kubectl calls
- Use the Kubernetes API normally

**What you CANNOT do (briefly, per replica):**
- Each replica is unavailable for ~3-5 minutes during its individual upgrade
- Load balancer routes around unavailable replicas automatically

## Pre-Flight Commands

```bash
# Verify current state and available versions
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="table(name, currentMasterVersion, location)"

# Check available versions in Regular channel
gcloud container get-server-config --region us-central1 \
  --format="yaml(channels.regular)"

# Verify no deprecated API usage
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Check cluster health
kubectl get nodes
kubectl get pods -n kube-system
```

## Control Plane Upgrade Commands

```bash
# Upgrade control plane to 1.32 (replace with latest 1.32.x patch)
gcloud container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version 1.32.x-gke.xxxx

# Monitor progress (optional - runs in background)
gcloud container operations list \
  --region us-central1 \
  --filter="operationType=UPGRADE_MASTER AND targetId=CLUSTER_NAME"
```

## Verification After Upgrade

```bash
# Confirm control plane version
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion)"

# Verify API server health
kubectl get pods -n kube-system
kubectl get nodes

# Check for any issues
kubectl get events -n kube-system --sort-by='.lastTimestamp' | tail -10
```

## Safety Recommendations

**Before upgrading:**
1. **Review GKE 1.32 release notes** for breaking changes between 1.31→1.32
2. **Test in staging first** if you have a staging cluster
3. **Verify third-party operators** (cert-manager, Istio, etc.) support 1.32
4. **Check admission webhooks** won't reject new API versions

**Timing:**
- Regional upgrades can run anytime - no API downtime
- Consider off-peak hours for extra caution
- Node pool upgrades (separate step) should use maintenance windows

## Next Steps: Node Pool Upgrades

After the control plane upgrade completes, you'll need to upgrade your node pools. **This is a separate operation** that does involve pod restarts. The control plane can be up to 2 minor versions ahead of nodes, so you have flexibility on timing.

Would you like me to provide the node pool upgrade plan once your control plane is at 1.32?

---

**Key takeaway:** Regional Standard GKE clusters are designed for zero-downtime control plane upgrades. Your API server will remain available throughout the process.
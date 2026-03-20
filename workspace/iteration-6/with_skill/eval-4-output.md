# GKE Control Plane Upgrade Plan: 1.29 → 1.30

## What to expect during the upgrade

**Good news: Zero API server downtime.** Regional GKE clusters have multiple control plane replicas across zones. During the upgrade, GKE performs a rolling update of these replicas, so the API server remains available throughout.

**Timeline:** Control plane upgrades typically take 10-15 minutes for regional clusters. You'll see brief API latency spikes during replica transitions, but no outages.

**What gets upgraded:** Only the control plane (API server, etcd, scheduler, controller-manager). Your nodes stay at 1.29 until you upgrade them separately.

## Pre-flight safety checks

Run these commands to verify your cluster is ready:

```bash
# Confirm current version and check 1.30 availability
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="table(name, currentMasterVersion, location, releaseChannel.channel)"

# Check available versions in Regular channel
gcloud container get-server-config --region us-central1 \
  --format="yaml(channels.REGULAR.validVersions)"

# Look for deprecated API usage (most common upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Verify cluster health
kubectl get nodes
kubectl get pods -n kube-system | grep -v Running
```

## The upgrade command

```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version 1.30
```

**Important:** The `--master` flag upgrades ONLY the control plane. Your nodes remain at 1.29.

## Monitor the upgrade

```bash
# Check upgrade progress
gcloud container operations list --region us-central1 --filter="operationType=UPGRADE_MASTER"

# Verify control plane version (wait ~10-15 min)
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion)"

# Confirm system pods are healthy
kubectl get pods -n kube-system
```

## What happens next

After the control plane upgrade completes:
1. **Your workloads continue running normally** — no pod restarts
2. **Node pools remain at 1.29** — this is expected and supported (nodes can be up to 2 minor versions behind)
3. **You can upgrade node pools later** when convenient using a separate command

## Version compatibility

✅ **Supported configuration:** Control plane 1.30 + Node pools 1.29  
✅ **API compatibility:** All 1.29 workloads work with 1.30 control plane  
⚠️ **Plan node upgrades:** Upgrade node pools to 1.30 within a reasonable timeframe

## Rollback consideration

Control plane downgrades are not supported. If you discover issues post-upgrade, the fix is to resolve the specific problem rather than downgrade. This is why we're only upgrading the control plane first — it's the safest approach.

---

**Ready to proceed?** The control plane upgrade is very low risk for regional clusters. Your API server stays available, and your workloads are unaffected. Run the pre-flight checks, then execute the upgrade command when ready.

Would you like me to create a runbook for upgrading your node pools to 1.30 afterwards?
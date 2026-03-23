# GKE Control Plane Upgrade Plan - Regional Cluster

Good news: **Regional GKE clusters have NO API server downtime** during control plane upgrades. This is a key benefit of regional clusters over zonal ones.

## What happens during a regional control plane upgrade

**Zero downtime:** Regional clusters run 3 control plane replicas across 3 zones with a load balancer. During upgrade, replicas are upgraded one at a time while the others continue serving traffic.

**Upgrade flow:**
1. First replica upgraded (others serve traffic)
2. Second replica upgraded (first + third serve traffic)  
3. Third replica upgraded (first + second serve traffic)
4. All replicas now on target version

**Duration:** Typically 10-15 minutes total. You'll see brief API latency spikes as replicas restart, but no connection failures.

## Pre-flight checks

First, verify 1.32 is available in Regular channel and check cluster health:

```bash
# Check available versions in Regular channel
gcloud container get-server-config --region us-central1 \
  --format="yaml(channels.REGULAR.validVersions)"

# Current cluster state
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="table(name, currentMasterVersion, releaseChannel.channel)"

# Cluster health
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed

# Check for deprecated API usage (most common upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
```

## Control plane upgrade command

```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version 1.32
```

**Important flags:**
- `--master`: Upgrades only the control plane, not nodes
- `--cluster-version 1.32`: Specify target version explicitly
- No `--async` needed - the command returns when upgrade completes

## During the upgrade

**Monitor progress:**
```bash
# Check upgrade status
gcloud container operations list \
  --region us-central1 \
  --filter="targetLink:CLUSTER_NAME AND operationType=UPGRADE_MASTER"

# Verify control plane version (will show 1.32 when complete)
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion)"

# System pod health
kubectl get pods -n kube-system
```

**Expected behavior:**
- `kubectl` commands continue working throughout
- Brief latency increases (~100-500ms) as replicas restart
- No connection failures or timeouts
- Upgrade completes in 10-15 minutes

## Post-upgrade validation

```bash
# Confirm control plane at 1.32
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion)"

# Verify API server responding normally
kubectl get pods -n kube-system
kubectl get nodes

# Check system component health
kubectl get componentstatuses  # May show warnings during upgrade
```

## Node pools (separate step)

After control plane upgrade completes, your nodes remain on 1.31. This is normal and supported - nodes can be up to 2 minor versions behind the control plane.

**Node upgrade is optional and separate.** If you want to upgrade nodes later:
```bash
# List node pools and their versions
gcloud container node-pools list --cluster CLUSTER_NAME --region us-central1

# Upgrade specific node pool (when ready)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region us-central1 \
  --cluster-version 1.32
```

## Troubleshooting

**If upgrade fails to start:**
1. Check for deprecated API usage (blocks auto-upgrades)
2. Verify no "no upgrades" maintenance exclusions are active
3. Ensure cluster is healthy (all nodes Ready)

**If stuck mid-upgrade:**
- Regional control plane upgrades rarely get stuck
- Wait 30 minutes before escalating to GKE support
- Provide cluster name, region, and operation ID

## Key takeaways

✅ **Zero downtime** for regional clusters  
✅ **Safe operation** - can run during business hours  
✅ **Control plane only** - nodes stay on 1.31 until you choose to upgrade them  
✅ **Quick process** - 10-15 minutes typical duration  
✅ **Continue kubectl access** throughout the upgrade

The upgrade is safe to run anytime. Your team's concerns about API server downtime don't apply to regional clusters - that's exactly why you chose regional over zonal!
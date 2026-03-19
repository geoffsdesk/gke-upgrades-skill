# GKE Control Plane Upgrade Guide: 1.29 → 1.30

Your team can breathe easy — **there is no API server downtime during GKE control plane upgrades**. Here's what actually happens and how to do it safely.

## What happens during control plane upgrade

### Zero downtime design
- **Regional clusters** (like yours) run 3 control plane replicas across zones
- GKE upgrades them one at a time (rolling upgrade)
- API server traffic is load-balanced across healthy replicas
- Your `kubectl` commands and workloads continue working normally

### Timeline expectations
- **Duration**: 10-15 minutes typically for 1.29 → 1.30
- **User impact**: None — API remains available throughout
- **Workload impact**: None — only the control plane upgrades, nodes stay on 1.29

## Pre-flight checks

Run these commands to verify readiness:

```bash
# Confirm current versions
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="table(name, currentMasterVersion, nodePools[].version)"

# Verify 1.30 is available in Regular channel
gcloud container get-server-config --region us-central1 \
  --format="yaml(channels.REGULAR)"

# Check for deprecated APIs (common upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Verify cluster health
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed
```

## Safe upgrade commands

### Step 1: Control plane upgrade
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version 1.30
```

**This command:**
- Upgrades only the control plane (API server, etcd, scheduler)
- Leaves all node pools on 1.29 (nodes can run up to 2 minor versions behind)
- Completes with zero API downtime

### Step 2: Monitor progress
```bash
# Check upgrade operation status
gcloud container operations list \
  --region us-central1 \
  --filter="targetId:CLUSTER_NAME AND operationType:UPGRADE_MASTER"

# Verify control plane version (wait ~10-15 minutes)
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion)"

# Confirm API server health
kubectl get pods -n kube-system
kubectl cluster-info
```

## What your team will observe

### During the upgrade (10-15 minutes)
- ✅ `kubectl` commands work normally
- ✅ Applications continue serving traffic
- ✅ New pods can be created/scheduled
- ✅ No service disruption

### After the upgrade
- Control plane: 1.30.x
- Node pools: still 1.29.x (unchanged)
- New Kubernetes 1.30 features available via API
- Full compatibility maintained

## Version compatibility

Your setup will be:
- **Control plane**: 1.30.x ← upgraded
- **Node pools**: 1.29.x ← unchanged
- **Version skew**: 1 minor version (fully supported)

This is perfectly normal. You can upgrade node pools later when convenient, or leave them on 1.29 until Regular channel auto-upgrades them.

## Node pool upgrade (optional, later)

If you want to upgrade node pools immediately after:

```bash
# Upgrade specific node pool
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --region us-central1 \
  --cluster-version 1.30

# Or upgrade all node pools
gcloud container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --node-pool-upgrade-strategy NODE_POOL
```

**Node pool upgrades DO cause pod restarts** as nodes are recreated with surge strategy.

## Key points for your team

1. **No API downtime** — this is GKE's core strength vs self-managed Kubernetes
2. **Control plane first** — always upgrade CP before nodes (required order)  
3. **Version skew is fine** — nodes can lag behind control plane safely
4. **Regular channel timing** — you control when this happens (no forced auto-upgrade for minor versions)
5. **Rollback is rare** — control plane downgrades require GKE support involvement

The control plane upgrade is the safest part of the GKE upgrade process. The complexity comes later with node pool upgrades (pod eviction, resource constraints, etc.), but you can tackle those separately when ready.
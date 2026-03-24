# Regional GKE Control Plane Upgrade: 1.31 → 1.32

## Zero-Downtime Guarantee for Regional Clusters

**Good news:** Your regional GKE cluster will have **zero API server downtime** during the control plane upgrade. Here's why:

- **Multiple control plane replicas:** Regional clusters run 3 control plane replicas across different zones
- **Rolling upgrade:** GKE upgrades one replica at a time while the others continue serving
- **High availability maintained:** The cluster API remains available throughout the entire upgrade process
- **Workloads unaffected:** Your pods continue running normally during the control plane upgrade

This is the key advantage of regional over zonal clusters for production workloads.

## What Happens During the Upgrade

1. **Pre-upgrade validation:** GKE checks for deprecated APIs and compatibility issues
2. **Rolling control plane upgrade:** Each replica is upgraded sequentially:
   - Replica 1 upgraded (Replicas 2 & 3 serve traffic)
   - Replica 2 upgraded (Replicas 1 & 3 serve traffic) 
   - Replica 3 upgraded (All replicas now at 1.32)
3. **System component updates:** kube-system pods restart with new versions
4. **Upgrade completion:** Cluster reports 1.32 as currentMasterVersion

**Duration:** Typically 10-15 minutes total

## Pre-Flight Checklist

```bash
# 1. Verify target version availability in Regular channel
gcloud container get-server-config --region us-central1 \
  --format="yaml(channels.REGULAR.validVersions)" | grep "1.32"

# 2. Check for deprecated API usage (most common upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# 3. Current cluster status
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="table(name, currentMasterVersion, status, location)"

# 4. System pod health baseline
kubectl get pods -n kube-system

# 5. Check for any active maintenance exclusions
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="value(maintenancePolicy)"
```

## Safe Upgrade Commands

```bash
# Upgrade control plane to 1.32
gcloud container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version 1.32 \
  --quiet

# Monitor progress (in separate terminal)
watch 'gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion,status)"'
```

## Validation Steps

**During upgrade (~10-15 minutes):**
```bash
# API server remains responsive
kubectl get nodes
kubectl get pods -n kube-system

# Cluster operations continue working
kubectl run test-pod --image=nginx --rm -it --restart=Never -- echo "API available"
```

**Post-upgrade validation:**
```bash
# 1. Confirm control plane version
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion)"
# Should show: 1.32.x-gke.xxxx

# 2. System pods healthy
kubectl get pods -n kube-system

# 3. Node versions (should still be 1.31 - that's normal)
kubectl get nodes -o wide

# 4. No stuck resources
kubectl get pods -A | grep -v Running | grep -v Completed

# 5. API functionality test
kubectl create deployment test-upgrade --image=nginx --replicas=1
kubectl delete deployment test-upgrade
```

## Next Steps: Node Pool Upgrades

**Important:** Control plane at 1.32, nodes at 1.31 is a **valid configuration**. Kubernetes supports up to 2 minor version skew (nodes can be up to 2 versions behind control plane).

You can:
- **Wait for auto-upgrade:** Regular channel will auto-upgrade your node pools to 1.32 within a few weeks
- **Manual node upgrade:** Upgrade node pools yourself when ready (separate operation, requires planning for pod disruption)
- **Stay at 1.31 nodes:** Keep nodes at 1.31 until you're ready (within the 2-version skew limit)

## Rollback Information

- **Control plane minor rollback:** Not supported without GKE support involvement
- **Patch rollback:** Possible within the same minor version (1.32.x → 1.32.y)
- **If issues arise:** Contact GKE support immediately with cluster name and symptoms

## Why This is Safe

1. **No API downtime:** Regional architecture ensures continuous availability
2. **Workload isolation:** Control plane upgrade doesn't restart your application pods
3. **Gradual rollout:** GKE has already validated 1.32 in Rapid channel before it reached Regular
4. **Automatic validation:** GKE blocks upgrades if deprecated APIs are detected

**Recommendation:** Proceed with confidence. Regional GKE control plane upgrades are designed to be zero-downtime operations.
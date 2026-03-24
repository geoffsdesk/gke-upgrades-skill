# GKE Control Plane Upgrade Guide: Regional Standard Cluster

## What happens during a regional control plane upgrade

**Good news: No API server downtime expected.** Regional clusters have multiple control plane replicas across zones, and GKE upgrades them one at a time while maintaining high availability.

**Upgrade sequence:**
1. One control plane replica is taken down and upgraded to 1.32
2. The remaining replicas continue serving API requests  
3. Process repeats for each replica
4. Each replica is briefly unavailable (~2-3 minutes), but the cluster API remains accessible
5. Total upgrade time: ~10-15 minutes

**During the upgrade:**
- ✅ Existing workloads continue running normally
- ✅ API server remains available (kubectl/gcloud commands work)
- ✅ You can still deploy new workloads
- ⚠️ Brief increased API latency possible during replica switches

This is the key advantage of regional over zonal clusters for production workloads.

## Pre-upgrade checklist

```bash
# 1. Verify target version is available in Regular channel
gcloud container get-server-config --region us-central1 \
  --format="yaml(channels.REGULAR.validVersions)"

# 2. Check current cluster state
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="table(name, currentMasterVersion, status)"

# 3. Check for deprecated API usage (most common upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# 4. Verify cluster health
kubectl get nodes
kubectl get pods -n kube-system | grep -v Running
```

## Safe upgrade commands

### Option 1: Immediate upgrade (recommended)
```bash
# Upgrade control plane to 1.32
gcloud container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version 1.32 \
  --quiet

# Monitor progress (upgrade takes ~10-15 minutes)
watch 'gcloud container clusters describe CLUSTER_NAME --region us-central1 --format="value(currentMasterVersion,status)"'
```

### Option 2: Schedule during maintenance window
```bash
# Set maintenance window first (optional - for predictable timing)
gcloud container clusters update CLUSTER_NAME \
  --region us-central1 \
  --maintenance-window-start "2024-01-27T02:00:00Z" \
  --maintenance-window-duration 4h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Then let auto-upgrade handle it, or manually trigger during the window
```

## Post-upgrade validation

```bash
# 1. Verify control plane version
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion)"

# 2. Check system pods are healthy
kubectl get pods -n kube-system

# 3. Test API server responsiveness
kubectl get nodes
kubectl create deployment test-nginx --image=nginx --replicas=2
kubectl delete deployment test-nginx

# 4. Verify no deprecated API warnings
kubectl get events -A --field-selector type=Warning | grep -i deprecated
```

## Important notes about node pools

After the control plane upgrade to 1.32:
- Your **node pools will remain at 1.31** (this is normal and supported)
- Nodes can be up to 2 minor versions behind the control plane
- You can upgrade node pools separately when convenient
- Consider skip-level node upgrades (1.31→1.32 in one step) to minimize disruption

## If something goes wrong

**Control plane upgrade failures are rare**, but if you see issues:

1. **Stuck upgrade operation:**
   ```bash
   # Check operation status
   gcloud container operations list --region us-central1 --filter="name~CLUSTER_NAME"
   ```

2. **API server 503 errors after upgrade:**
   - Usually resolves within 5-10 minutes as components stabilize
   - Check system pod health: `kubectl get pods -n kube-system`

3. **Admission webhook failures:**
   ```bash
   # Check webhook configurations
   kubectl get validatingwebhookconfigurations
   # May need to update cert-manager or other operators
   ```

**Emergency contact:** GKE support if the control plane upgrade fails or API server is unavailable >30 minutes.

Would you like me to also prepare a node pool upgrade plan for after your control plane is successfully upgraded to 1.32?
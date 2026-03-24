## Regional Cluster Control Plane Upgrade - Zero Downtime

**Good news:** Your **regional** cluster will have **zero API server downtime** during the control plane upgrade. Regional clusters have multiple control plane replicas across different zones, and GKE upgrades them one at a time while keeping the others serving traffic.

### What happens during a regional control plane upgrade:

1. **High availability maintained:** Multiple control plane replicas remain available throughout
2. **Rolling upgrade:** Each replica is upgraded individually while others handle requests
3. **Brief individual replica downtime:** Each replica is unavailable for ~2-3 minutes during its upgrade
4. **Total upgrade time:** ~10-15 minutes for the entire control plane
5. **Workloads unaffected:** Your pods keep running normally during the upgrade

This is fundamentally different from zonal clusters, which have a single control plane replica and experience a few minutes of API unavailability.

## Pre-flight Checks

```bash
# Verify current version and channel
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="table(name, currentMasterVersion, releaseChannel.channel, location)"

# Check if 1.32 is available in Regular channel
gcloud container get-server-config --region us-central1 \
  --format="yaml(channels.REGULAR)"

# Check for deprecated API usage (common upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Verify cluster health
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed
kubectl get pods -n kube-system
```

## Control Plane Upgrade Commands

```bash
# Upgrade control plane to 1.32
gcloud container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version 1.32

# Monitor progress (should complete in 10-15 minutes)
watch 'gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion,status)"'
```

## Verification

```bash
# Confirm control plane version
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion)"

# Verify system components are healthy
kubectl get pods -n kube-system
kubectl get componentstatuses  # Deprecated but still useful

# Test API server responsiveness
kubectl get namespaces
kubectl create deployment test-deployment --image=nginx --dry-run=client -o yaml
```

## Safety Considerations

**API server availability:** ✅ Zero downtime expected with regional clusters

**Workload impact:** ✅ Minimal - pods continue running, no restarts required

**Timing:** The upgrade can be done during business hours since there's no API downtime

**Node pools:** Your node pools will remain at 1.31 until you upgrade them separately (which IS disruptive and should be planned accordingly)

## Next Steps After Control Plane Upgrade

1. **Monitor for 24-48 hours** to ensure stability
2. **Plan node pool upgrades** - these WILL cause pod restarts and need careful planning with surge settings
3. **Review any deprecated APIs** before the next minor version upgrade

The control plane upgrade itself is the low-risk part of your 1.32 migration. The node pool upgrades (when you're ready) will require more planning around PDBs, surge capacity, and workload tolerance.

Would you like me to help you plan the node pool upgrade strategy once your control plane is successfully at 1.32?
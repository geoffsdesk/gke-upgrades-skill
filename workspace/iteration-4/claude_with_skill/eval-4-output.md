# GKE Control Plane Upgrade: 1.29 → 1.30

Good news: **Regional GKE clusters have zero API server downtime during control plane upgrades.** Your cluster has multiple control plane replicas across zones, and GKE upgrades them one at a time while maintaining API availability.

## What happens during the upgrade

1. **Rolling upgrade**: GKE upgrades control plane replicas sequentially across the 3 zones in us-central1
2. **API server remains available**: At least 2 replicas stay online throughout the process
3. **Automatic failover**: `kubectl` requests automatically route to healthy replicas
4. **Duration**: Typically 10-15 minutes total
5. **No node impact**: Your workloads keep running on existing nodes

The only brief interruption you might notice is individual `kubectl` commands occasionally retrying (usually transparent to users).

## Pre-flight checks

```bash
# Verify current version and available upgrades
gcloud container clusters describe YOUR_CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion)"

# Check what 1.30 versions are available in Regular channel
gcloud container get-server-config --region us-central1 \
  --format="yaml(channels.regular.validVersions)" | grep "1.30"

# Verify cluster health
kubectl get nodes
kubectl get pods -n kube-system | grep -v Running
```

## Upgrade commands

```bash
# Upgrade control plane to 1.30 (replace with specific patch version)
gcloud container clusters upgrade YOUR_CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version 1.30.x-gke.xxxx

# Monitor progress (optional - the command blocks until complete)
gcloud container operations list \
  --region us-central1 \
  --filter="targetLink:YOUR_CLUSTER_NAME AND operationType=UPGRADE_MASTER"
```

## Validation

```bash
# Confirm control plane upgraded
gcloud container clusters describe YOUR_CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion)"

# Verify API server responding
kubectl get pods -n kube-system

# Check system components healthy
kubectl get componentstatuses
```

## Safety considerations

✅ **Regional cluster** = No API downtime  
✅ **Control plane only** = No workload disruption  
✅ **Regular channel** = Version 1.30 is well-tested  

The main risk is if you have:
- **Deprecated API usage** → Check deprecation insights dashboard first
- **Admission webhooks** → May reject system pods briefly during upgrade
- **Custom operators** → Verify 1.30 compatibility

## Next steps

After the control plane upgrade succeeds:
1. **Node pools remain on 1.29** → Plan node pool upgrades separately
2. **Version skew limit** → Nodes can be up to 2 minor versions behind (1.29 nodes + 1.30 control plane = OK)
3. **Node upgrades** → These will cause pod rescheduling and need more planning

Would you like me to create a node pool upgrade plan once your control plane upgrade is complete?
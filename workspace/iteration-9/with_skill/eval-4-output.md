# GKE Control Plane Upgrade Plan: 1.31 → 1.32

## Control Plane Availability During Upgrade

**Good news: No API server downtime expected.** GKE regional clusters run multiple control plane replicas across zones. During control plane upgrades:

- **Regional clusters**: Zero downtime - upgrade happens with rolling replacement of control plane replicas
- **Zonal clusters**: Brief unavailability (few minutes) during single control plane upgrade

Since you're running a **regional cluster**, your API server will remain available throughout the upgrade process. Your `kubectl` commands, CI/CD pipelines, and applications making Kubernetes API calls should continue working normally.

## Pre-Flight Checklist

```bash
# Verify current versions and available targets
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="table(name, currentMasterVersion, releaseChannel.channel)"

# Check what 1.32 versions are available in Regular channel
gcloud container get-server-config --region us-central1 \
  --format="yaml(channels.regular)"

# Check for deprecated API usage (most common upgrade failure cause)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Verify cluster health
kubectl get nodes
kubectl get pods -A | grep -v Running | grep -v Completed
```

## Upgrade Commands

```bash
# 1. Upgrade control plane to 1.32
gcloud container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version 1.32.x-gke.xxxx

# The upgrade typically takes 10-15 minutes for regional clusters
# You'll see output like: "Upgrading master to 1.32.x-gke.xxxx..."
```

## Validation Steps

```bash
# 2. Verify control plane upgrade completed
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion)"

# 3. Check system pods are healthy
kubectl get pods -n kube-system

# 4. Verify API server responsiveness
kubectl get namespaces
kubectl version --short
```

## What Happens During the Upgrade

1. **Pre-upgrade validation**: GKE checks cluster health and compatibility
2. **Rolling upgrade**: Control plane replicas upgraded one zone at a time
3. **Load balancer management**: Traffic automatically shifts to available replicas
4. **System component updates**: Core add-ons (DNS, metrics-server) restart with new versions
5. **Final validation**: GKE confirms all replicas are healthy

**Timeline**: 10-15 minutes total, with API available throughout.

## Important Notes

- **Node pools stay on 1.31** until you explicitly upgrade them (separate step)
- **Version skew**: Nodes can run up to 2 minor versions behind control plane (1.31 nodes + 1.32 control plane = supported)
- **Automatic vs manual**: Since you're on Regular channel, this upgrade would happen automatically during your next maintenance window anyway
- **No rollback needed**: Control plane patch downgrades are supported if issues arise

## Next Steps After Control Plane Upgrade

Your cluster will be in a mixed state (1.32 control plane, 1.31 nodes) which is fully supported. When ready to upgrade node pools:

```bash
# Check node pool versions
gcloud container node-pools list --cluster CLUSTER_NAME --region us-central1

# Node pool upgrades are a separate operation (more disruptive, requires pod restarts)
# Plan those during your normal maintenance window
```

## Safety Considerations

✅ **Regional cluster** = No API downtime expected  
✅ **Regular channel** = Well-tested upgrade path  
✅ **Control plane only** = No workload pod restarts  
✅ **Version skew supported** = Can upgrade nodes later  

The control plane upgrade is the lowest-risk part of the GKE upgrade process. Your applications will continue running normally on the 1.31 nodes while gaining access to any new 1.32 Kubernetes features through the API server.
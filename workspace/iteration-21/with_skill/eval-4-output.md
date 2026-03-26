# GKE Control Plane Upgrade: Regional Standard Cluster (1.31 → 1.32)

## What Will Happen During Your Upgrade

**Good news: You'll have zero API server downtime.** Here's why:

### Regional Control Plane Upgrade Behavior
- **Regional clusters** have multiple control plane replicas across zones
- GKE upgrades one replica at a time while others remain available
- Your cluster API remains highly available throughout the upgrade
- Each replica is briefly unavailable during its individual upgrade (~2-3 minutes per replica)
- **Total upgrade time:** ~10-15 minutes for the full control plane

### What You CAN Do During Upgrade
- Deploy new workloads
- Modify existing workloads  
- Change cluster configuration
- All `kubectl` and `gcloud` commands work normally

**This is the key advantage of regional over zonal clusters** - no API server downtime during upgrades.

## Version Availability Check

First, let's confirm 1.32 is available in the Regular channel:

```bash
# Check available versions in Regular channel
gcloud container get-server-config --zone us-central1-a \
  --format="yaml(channels)" | grep -A 20 "REGULAR"

# Check your current cluster details
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="table(name, currentMasterVersion, releaseChannel.channel)"
```

## Safe Upgrade Commands

### Pre-flight Checks
```bash
# Verify cluster health
kubectl get nodes
kubectl get pods -n kube-system

# Check for deprecated API usage (most common upgrade blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# If you see deprecated APIs, check GKE insights for details:
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=us-central1 \
    --project=PROJECT_ID
```

### Control Plane Upgrade
```bash
# Upgrade control plane to 1.32
gcloud container clusters upgrade CLUSTER_NAME \
  --region us-central1 \
  --master \
  --cluster-version 1.32

# Monitor progress (upgrade typically takes 10-15 minutes)
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="value(currentMasterVersion)"
```

### Post-Upgrade Validation
```bash
# Verify control plane version
gcloud container clusters describe CLUSTER_NAME \
  --region us-central1 \
  --format="table(name, currentMasterVersion, status)"

# Check system component health
kubectl get pods -n kube-system
kubectl get componentstatuses

# Verify API functionality
kubectl get nodes
kubectl get namespaces
```

## Node Pool Planning (Separate Step)

**Important:** This upgrade only covers the control plane. Your nodes remain at 1.31, which is perfectly valid (nodes can be up to 2 minor versions behind the control plane).

When you're ready to upgrade node pools later:
- Nodes must be upgraded after the control plane
- You can upgrade directly from 1.31 → 1.32 (skip-level within supported skew)
- Plan node pool upgrades separately with appropriate surge settings

## Timeline and Expectations

- **Initiation:** Command returns immediately
- **Duration:** 10-15 minutes typical
- **Downtime:** Zero API server downtime
- **Workload impact:** None (nodes unchanged)
- **Rollback:** Control plane minor version rollback requires GKE support involvement

## What Could Go Wrong?

**Most likely issues (in order):**
1. **Deprecated API usage** - GKE automatically pauses auto-upgrades when deprecated APIs are detected. Manual upgrades may proceed but could cause issues post-upgrade.
2. **Admission webhook compatibility** - Webhooks (cert-manager, policy controllers) may need updates for Kubernetes 1.32 API changes.

**Preparation recommendation:**
- Review [GKE 1.32 release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes) for breaking changes
- Test critical workloads against 1.32 in a staging cluster if possible

This is a low-risk upgrade for the control plane on a regional cluster. The zero-downtime nature of regional control plane upgrades makes this operation safe for production environments.
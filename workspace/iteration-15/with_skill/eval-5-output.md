## Version Skew Analysis

You have a **critical version skew issue**. Your node pool at 1.28 is **3 minor versions behind** the 1.31 control plane, which **exceeds GKE's supported 2-minor-version skew limit**.

**What this means:**
- ⚠️ **Unsupported configuration** - GKE only supports nodes within 2 minor versions of the control plane
- 🔴 **Version 1.28 is approaching End of Support** (EoS enforcement likely happening soon)
- ⚡ **GKE will force-upgrade this node pool** when 1.28 reaches EoS, regardless of maintenance exclusions
- 🚨 **Risk of API compatibility issues** between very old nodes and newer control plane

## Immediate Action Required

You need to upgrade the 1.28 node pool to at least **1.29** to get back within supported skew, but I recommend going directly to **1.31** (same as control plane) for consistency.

## Upgrade Strategy

Since you're dealing with a 3-version gap, you have two options:

### Option A: Skip-Level Upgrades (Recommended)
Upgrade in two steps to stay within supported skew:
1. **1.28 → 1.30** (2-version skip, maximum allowed)
2. **1.30 → 1.31** (1-version skip)

### Option B: New Node Pool Migration (Safer for critical workloads)
Create a new node pool at 1.31 and migrate workloads:

```bash
# Create new node pool at target version
gcloud container node-pools create POOL_NAME-v131 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.xxxx \
  --machine-type MACHINE_TYPE \
  --num-nodes NUM_NODES

# Cordon old pool to prevent new pod scheduling
kubectl cordon -l cloud.google.com/gke-nodepool=OLD_POOL_NAME

# Drain workloads (this will take time)
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data

# Delete old pool once migration complete
gcloud container node-pools delete OLD_POOL_NAME --cluster CLUSTER_NAME --zone ZONE
```

## Upgrade Runbook (Option A - Skip-Level)

### Pre-flight Checks
```bash
# Verify current versions
gcloud container clusters describe CLUSTER_NAME --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Check for deprecated API usage (critical for 1.28→1.31)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Check workload readiness
kubectl get pdb -A
kubectl get pods -A | grep -v Running | grep -v Completed
```

### Step 1: Configure Conservative Upgrade Settings
```bash
# Set conservative surge settings for the problematic pool
gcloud container node-pools update OLD_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### Step 2: First Skip-Level Upgrade (1.28 → 1.30)
```bash
# Upgrade to intermediate version
gcloud container node-pools upgrade OLD_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30.x-gke.xxxx

# Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
```

### Step 3: Second Skip-Level Upgrade (1.30 → 1.31)
```bash
# Upgrade to match control plane
gcloud container node-pools upgrade OLD_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.xxxx
```

## Key Considerations

**API Compatibility Risk:** The 1.28→1.31 gap spans significant Kubernetes API changes. Before upgrading, verify:
- No deprecated APIs in use that were removed in 1.29, 1.30, or 1.31
- Third-party operators/controllers support the target versions
- Admission webhooks are compatible with newer API versions

**Timing Pressure:** You're likely close to automatic EoS enforcement. Check your cluster's EoS timeline:
```bash
gcloud container clusters get-upgrade-info CLUSTER_NAME --region REGION
```

**Prevention:** After fixing this, implement:
- Regular upgrade cadence to prevent version drift
- Monitoring for version skew warnings
- Maintenance exclusions only when needed (not indefinite freezing)

## Validation Checklist

After each upgrade step:
```bash
# ✅ Version alignment
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE

# ✅ All nodes healthy
kubectl get nodes

# ✅ Workloads running
kubectl get pods -A | grep -E "CrashLoop|Pending|Error"

# ✅ System pods stable
kubectl get pods -n kube-system
```

This is a recoverable situation, but you need to act quickly before EoS enforcement kicks in. The skip-level approach will get you back to a supported state efficiently.
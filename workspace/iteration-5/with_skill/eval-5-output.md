# GKE Version Skew Emergency Fix

You have a **critical version skew issue**. Your node pool at 1.28 is **3 minor versions** behind your 1.31 control plane, which exceeds GKE's supported skew limit of 2 minor versions. This can cause instability and must be fixed immediately.

## What you're dealing with

**Severity:** Critical - unsupported configuration
**Risk:** API compatibility issues, pod scheduling failures, unpredictable behavior
**Root cause:** Node pool upgrades were skipped or failed while control plane auto-upgraded

## Immediate action plan

### 1. Verify the situation
```bash
# Confirm versions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version)"

# Check if any upgrades are currently running
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="status=RUNNING"
```

### 2. Upgrade the 1.28 node pool immediately

You'll need to do this in stages since you can't jump 3 versions safely:

```bash
# Stage 1: 1.28 → 1.29
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.29

# Wait for completion, then Stage 2: 1.29 → 1.30
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30

# Wait for completion, then Stage 3: 1.30 → 1.31
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31
```

**Important:** You must upgrade sequentially (1.28→1.29→1.30→1.31). Don't attempt to jump directly to 1.31.

### 3. Configure surge settings for faster upgrades

Before starting the upgrades, optimize for speed:

```bash
# Set aggressive surge for faster completion
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0
```

### 4. Monitor progress between stages

```bash
# Watch node versions during each upgrade
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Check for any stuck pods between upgrades
kubectl get pods -A | grep -v Running | grep -v Completed
```

## Why this happened

Common causes:
- **Maintenance exclusions** blocking node pool upgrades while CP auto-upgraded
- **Failed node pool upgrades** due to PDB/resource constraints, but CP continued
- **Manual CP upgrades** without corresponding node pool upgrades
- **"No channel" legacy cluster** with inconsistent upgrade behavior

## Prevent recurrence

After fixing the immediate issue:

### 1. Review your maintenance exclusions
```bash
# Check current exclusions
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="yaml(maintenancePolicy)"
```

If you have "no minor or node upgrades" exclusions, they block node pool upgrades but allow CP patches. Consider using "no upgrades" (blocks everything) or "no minor upgrades" (allows node pool patches) instead.

### 2. Migrate off legacy "No channel" if applicable
```bash
# Check if you're on legacy "No channel"
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(releaseChannel.channel)"

# If empty/null, migrate to Regular channel
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular
```

### 3. Set up monitoring
```bash
# Enable GKE deprecation insights in Console
# Set up alerts for version skew in Cloud Monitoring
```

## Troubleshooting during fix

If any upgrade stage gets stuck:

1. **Check PDBs:** `kubectl get pdb -A` - relax if blocking
2. **Check resources:** `kubectl get pods -A | grep Pending` - increase surge
3. **Check bare pods:** Delete any pods without owner references

## Timeline expectation

- Each stage (1.28→1.29, 1.29→1.30, 1.30→1.31) takes 15-45 minutes depending on pool size
- Total time: 1-3 hours for the full upgrade sequence
- **Don't wait** - start this immediately to get back into supported configuration

The version skew warnings will disappear once all node pools reach 1.31. This is your top priority fix.
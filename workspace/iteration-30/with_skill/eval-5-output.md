You're dealing with **version skew violation** - your node pool is 3 minor versions behind the control plane (1.28 vs 1.31), which exceeds GKE's maximum supported skew of 2 minor versions. This is a serious issue that needs immediate attention.

## What You're Dealing With

**Current state:** Control plane 1.31, node pool 1.28 (N+3 skew - **unsupported**)
**Risk:** Version 1.28 is likely at or approaching End of Support, meaning forced upgrades are imminent
**Impact:** Potential cluster instability, unsupported configuration, security vulnerabilities

## Recovery Plan

You need to upgrade the node pool, but you **cannot jump directly from 1.28 to 1.31** in a single upgrade. Here are your options:

### Option 1: Skip-level upgrades (Recommended)
Perform two skip-level (N+2) upgrades to catch up:

```bash
# Step 1: Upgrade 1.28 → 1.30 (N+2 skip-level)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --node-version 1.30.X-gke.XXXX

# Wait for completion, then Step 2: Upgrade 1.30 → 1.31 (regular)
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --node-version 1.31.X-gke.XXXX
```

### Option 2: New node pool migration (Faster recovery)
Create a new pool at 1.31 and migrate workloads:

```bash
# Create new node pool at current CP version
gcloud container node-pools create NEW_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --node-version 1.31.X-gke.XXXX \
  --num-nodes NUM_NODES \
  --machine-type MACHINE_TYPE

# Cordon old pool
kubectl cordon -l cloud.google.com/gke-nodepool=OLD_POOL_NAME

# Drain old pool (this will migrate workloads)
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data

# Delete old pool once workloads are migrated
gcloud container node-pools delete OLD_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE
```

## Pre-flight Checks (Critical)

Before starting either approach:

```bash
# Check available versions
gcloud container get-server-config --zone ZONE \
  --format="yaml(channels)"

# Check for deprecated API usage (major blocker)
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Verify workload readiness
kubectl get pdb -A -o wide
kubectl get pods -A | grep -v Running
```

## Immediate Actions

1. **Apply maintenance exclusion** to prevent auto-upgrades during recovery:
```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "recovery-exclusion" \
  --add-maintenance-exclusion-scope no_upgrades \
  --add-maintenance-exclusion-start-time $(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --add-maintenance-exclusion-end-time $(date -u -d '+7 days' +"%Y-%m-%dT%H:%M:%SZ")
```

2. **Check EoS timeline** for version 1.28:
```bash
gcloud container clusters get-upgrade-info CLUSTER_NAME --zone ZONE
```

## Recommended Strategy

**Go with Option 2 (new node pool)** if:
- You need fastest recovery
- You have sufficient quota for temporary double capacity
- Workloads can tolerate brief rescheduling

**Go with Option 1 (skip-level)** if:
- Quota is constrained
- You want to preserve node pool configuration
- You can tolerate longer maintenance window

## Prevention for the Future

After recovery, set up proper upgrade controls:

```bash
# Configure maintenance window
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-01-13T02:00:00Z" \
  --maintenance-window-end "2024-01-13T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"

# Consider "no minor or node upgrades" exclusion for maximum control
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**Time sensitivity:** If version 1.28 is approaching EoS (check the [GKE release schedule](https://cloud.google.com/kubernetes-engine/docs/release-schedule)), GKE will force-upgrade your node pool. Start recovery immediately.

Would you like me to create a detailed runbook for either recovery option, or do you need help diagnosing any specific blockers first?
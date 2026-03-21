# GKE Version Skew Issue - Urgent Fix Required

## What you're dealing with

Your cluster is in **violation of GKE's version skew policy**:
- Control plane: 1.31
- Node pool: 1.28 
- **Gap: 3 minor versions** (exceeds the 2-minor-version maximum)

This creates several problems:
- **API incompatibilities** - nodes may not understand newer control plane APIs
- **Networking issues** - kube-proxy/CNI version mismatches
- **Security gaps** - nodes missing 3 versions of security patches
- **Support issues** - configuration is outside supported boundaries
- **Potential workload failures** - especially for system components

## Immediate Action Required

You need to upgrade the 1.28 node pool to at least 1.29 to get back within the supported skew range. Here's your upgrade path:

### Step 1: Pre-flight Assessment

```bash
# Check exact versions and node pool details
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].name, nodePools[].version, nodePools[].status)"

# Check workload health before changes
kubectl get pods -A | grep -v Running | grep -v Completed
kubectl get nodes | grep -v Ready
```

### Step 2: Plan Your Node Pool Upgrade Strategy

Since you're dealing with a 3-version gap, you have options:

**Option A: Skip-level upgrade (1.28 → 1.30 or 1.31)**
- Faster, single operation
- Node pools support N+2 upgrades
- Less total disruption

**Option B: Sequential upgrades (1.28 → 1.29 → 1.30 → 1.31)**
- More conservative
- Multiple disruption windows
- Easier to troubleshoot issues

**I recommend Option A** - skip-level to 1.30 or directly to 1.31 to match your control plane.

### Step 3: Configure Upgrade Settings

```bash
# For stateless workloads - faster upgrade
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 3 \
  --max-unavailable-upgrade 0

# For stateful workloads - conservative upgrade
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

### Step 4: Execute the Upgrade

```bash
# Skip-level upgrade to match control plane
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31

# Monitor progress
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
```

### Step 5: Validate

```bash
# Confirm all nodes are at compatible versions
gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE

# Check workload health
kubectl get pods -A | grep -E "Error|CrashLoop|Pending"
kubectl get nodes | grep NotReady
```

## How did this happen?

This situation typically occurs when:
1. **Manual version pinning** - node pool auto-upgrade was disabled
2. **Maintenance exclusions** - long-running exclusions blocked node upgrades while control plane continued
3. **Failed upgrades** - previous node pool upgrades failed and were never retried
4. **Legacy "No channel"** - clusters without release channels have different upgrade behavior

## Prevention for the future

After fixing the immediate issue:

```bash
# Check if you're on a release channel
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(releaseChannel.channel)"

# If "No channel" (legacy), migrate to Regular channel
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --release-channel regular

# Set up maintenance windows for predictable upgrades
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-12-14T02:00:00Z" \
  --maintenance-window-end "2024-12-14T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
```

## If you have multiple node pools in this state

Upgrade them **sequentially** to avoid overwhelming the cluster:
1. Start with least critical workloads
2. Validate each pool before moving to the next
3. Leave GPU/stateful pools for last

## Emergency considerations

If workloads are failing due to version skew right now:
1. **Prioritize the upgrade** - this is outside supported configuration
2. **Scale down non-critical workloads** temporarily if needed for faster upgrade
3. **Check for deprecated API usage** that might fail with newer kubelet versions

The version skew warnings will disappear once your node pools are within 2 minor versions of the control plane (1.29 or newer).
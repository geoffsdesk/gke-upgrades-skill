You are currently facing a **Kubernetes version skew violation**, which is a critical state. 

GKE (and upstream Kubernetes) strictly requires that node pools be no more than **two minor versions behind the control plane**. With your control plane at 1.31 and nodes at 1.28, you have a skew of three versions. 

**The Risks:**
* **API Incompatibility:** The 1.31 control plane has completely removed certain APIs that your 1.28 nodes (and the workloads running on them) might still be trying to use.
* **Communication Failures:** The `kubelet` on 1.28 nodes may struggle to communicate properly with the 1.31 API server, leading to workloads failing to schedule or nodes going `NotReady`.

Here is the step-by-step plan to safely fix this and prevent it from happening again.

---

### Step 1: The Upgrade Path (Skip-Level Upgrade)

Because you cannot upgrade a node pool more than two minor versions at a time (N+2), **you cannot upgrade directly from 1.28 to 1.31.**

Fortunately, GKE supports skip-level (N+2) upgrades for node pools. The fastest and least disruptive path to compliance is to upgrade the 1.28 node pool directly to **1.30** in a single operation. Once at 1.30, you will be back within the supported 2-version skew limit, and you can later upgrade to 1.31 if desired.

### Step 2: Remediation Runbook

Run these commands to execute the skip-level upgrade. Replace `CLUSTER_NAME`, `ZONE`, and `NODE_POOL_NAME` with your actual values.

#### 1. Pre-flight Checks
First, find an available 1.30 version in your cluster's zone/region:
```bash
# List available 1.30 versions for node pools
gcloud container get-server-config --zone ZONE \
  --format="yaml(validNodeVersions)" | grep "1.30"
```
*(Select a valid 1.30 patch version from the output, e.g., `1.30.5-gke.1000000`, and use it as your `TARGET_VERSION` below).*

#### 2. Configure Surge Settings (Optional but recommended)
To ensure the upgrade moves quickly but safely, configure your surge settings. (If this is a GPU node pool, use `--max-surge-upgrade 0 --max-unavailable-upgrade 1` instead).
```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

#### 3. Execute the Skip-Level Upgrade
Initiate the N+2 upgrade to version 1.30:
```bash
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --node-version TARGET_VERSION
```

#### 4. Monitor Progress
Open a separate terminal to watch the nodes cycle. You should see new 1.30 nodes joining the cluster and 1.28 nodes being cordoned, drained, and removed:
```bash
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
```

---

### Step 3: Root Cause & Long-Term Fix

You need to address *why* this happened. GKE's default auto-upgrade lifecycle is designed to specifically prevent this exact skew. This state almost always occurs for one of two reasons:

1. **Legacy "No Channel" Configuration:** The cluster might not be enrolled in a release channel, and manual node upgrades were forgotten while the control plane was force-upgraded due to End of Support (EoS) policies.
2. **Improper Maintenance Exclusions:** You might have applied a maintenance exclusion that specifically blocked *node* upgrades but allowed the control plane to continue upgrading automatically. 

**How to prevent this moving forward:**

Instead of turning off auto-upgrades or un-enrolling from release channels, you should use GKE's native release channels combined with a **Cluster-Level Maintenance Exclusion**.

If your goal is to strictly control when disruptive minor and node upgrades happen, apply the `no_minor_or_node_upgrades` exclusion:

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "freeze-minor-and-nodes" \
  --add-maintenance-exclusion-start-time "2023-10-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2024-10-01T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

**Why this is the best practice:**
The `no_minor_or_node_upgrades` scope prevents the control plane from moving to a new minor version (e.g., 1.31 to 1.32) AND prevents node pools from upgrading. However, it *allows* the control plane to receive invisible, non-disruptive security patches. Because it locks the control plane minor version, **it mathematically guarantees you will never suffer from version skew again**, while keeping you securely patched.
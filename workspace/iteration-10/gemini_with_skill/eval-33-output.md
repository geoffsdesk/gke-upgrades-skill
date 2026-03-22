Upgrading a large-scale AI/ML cluster from GKE 1.31 to 1.32 requires careful orchestration. Because GPU VMs do not support live migration, every node upgrade requires a pod restart. Furthermore, your two workload profiles (latency-sensitive inference and long-running fine-tuning) require completely different upgrade strategies.

Here is your tailored upgrade plan, focusing on GPU quota constraints, driver compatibility, and protecting your 4-8 hour fine-tuning jobs.

### ⚠️ Critical Pre-Flight: GPU Driver & CUDA Version
When you upgrade the GKE node version to 1.32, **GKE will automatically install the NVIDIA driver associated with that new GKE version**. This may silently change the underlying CUDA version, which can break PyTorch/TensorFlow framework compatibility. 
* **Action:** Before touching production, spin up a single L4 and A100 node on GKE 1.32 in a dev environment and verify your inference server and fine-tuning containers initialize successfully.

---

## Node Pool Upgrade Strategies

### 1. L4 Node Pool (Inference - 200 nodes)
**Goal:** Maintain serving capacity and keep inference latency stable.
**Strategy:** Customized Surge Upgrade.

Because you are auto-scaling based on traffic, you need to ensure GKE doesn't take down too many serving nodes at once. GPU instances typically lack available surge quota in GCP.
* **If you DO NOT have extra L4 quota:** Set `maxSurge=0, maxUnavailable=5`. This drains and upgrades 5 nodes at a time without requiring new VMs. It briefly reduces your cluster capacity by 2.5%, which your auto-scaler can handle by routing traffic to the remaining 195 nodes.
* **If you DO have extra L4 quota:** Set `maxSurge=5, maxUnavailable=0`. GKE will provision 5 new nodes before draining the old ones, resulting in zero capacity dip.

Ensure you have **PodDisruptionBudgets (PDBs)** applied to your inference deployments so GKE respects your minimum available replica counts during the rolling drain.

### 2. A100 Node Pool (Fine-Tuning - 100 nodes)
**Goal:** Prevent GKE from killing 4-8 hour jobs mid-flight.
**Strategy:** Cordon & Wait OR Autoscaled Blue-Green.

**The Danger:** GKE's default PDB timeout during a standard surge upgrade is **1 hour**. If a node is draining and your fine-tuning job refuses to evict because it's running, GKE will forcefully terminate the pod after 60 minutes.

You have two paths depending on your A100 quota availability:

* **Path A: Autoscaled Blue-Green Upgrade (If you have buffer A100 quota)**
  This strategy cordons the old nodes (blue) and scales up replacement nodes (green). It supports significantly longer wait-for-drain and graceful termination periods, allowing your 8-hour jobs to finish naturally before the underlying node is deleted.
* **Path B: Cordon and Wait (If your 100 A100s represent your absolute quota limit)**
  Since A100s are highly constrained, you likely cannot provision "green" nodes temporarily. You must manage this manually:
  1. Halt the scheduling of *new* fine-tuning jobs.
  2. Cordon the A100 node pool.
  3. Wait 4-8 hours for active jobs to complete successfully.
  4. Once the nodes are idle, upgrade the pool.

---

## Upgrade Runbook

### Step 0: Apply Maintenance Exclusions (Immediate Action)
To ensure GKE's auto-upgrader doesn't trigger unexpectedly while you are mid-training or planning, apply a "No minor or node upgrades" exclusion immediately. This blocks disruptions but allows control plane security patches.

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "ml-upgrade-freeze" \
  --add-maintenance-exclusion-start-time "2023-10-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2023-10-15T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

### Step 1: Upgrade the Control Plane
The control plane must be upgraded to 1.32 before the node pools. This takes ~15 minutes and does not disrupt running workloads.

```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32
```

### Step 2: Upgrade the L4 Inference Pool
Assuming you do not have extra L4 quota, configure the surge settings to use `maxUnavailable`:

```bash
# Configure rolling upgrade parameters for L4 pool
gcloud container node-pools update l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 5

# Initiate L4 pool upgrade
gcloud container node-pools upgrade l4-inference-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

### Step 3: Upgrade the A100 Fine-Tuning Pool (Strict Quota Method)
If you are strictly bound to 100 A100s, follow the Cordon & Wait pattern:

```bash
# 1. Cordon the entire A100 pool so no new jobs are scheduled
kubectl cordon -l cloud.google.com/gke-nodepool=a100-tuning-pool

# 2. Monitor your workloads and wait for active jobs to complete
# Ensure your training platform/orchestrator queues new jobs elsewhere or holds them

# 3. Once jobs are finished and nodes are idle, maximize speed
gcloud container node-pools update a100-tuning-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 20  # Drain 20 at a time since they are empty

# 4. Initiate the upgrade
gcloud container node-pools upgrade a100-tuning-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

---

## Pre/Post-Upgrade Checklist

### Pre-Upgrade
- [ ] **Driver Test**: Test framework (PyTorch/TF) against the 1.32 GKE node image in a sandbox.
- [ ] **Checkpointing**: Verify all active fine-tuning jobs are regularly saving checkpoints to Cloud Storage/Filestore in case of unexpected node eviction.
- [ ] **Quota Check**: Confirm your exact A100 and L4 quota limits in GCP console (IAM & Admin > Quotas) to validate your `maxSurge` strategy.
- [ ] **PDB Check**: Verify inference PDBs are active: `kubectl get pdb -A`. Ensure none require 100% availability (which would block the L4 upgrade).
- [ ] **API Deprecations**: Check the GKE Deprecation Insights dashboard for APIs removed in 1.32.

### Post-Upgrade
- [ ] **Control plane and Nodes matching**: `kubectl get nodes -o wide` to confirm all pools show v1.32.x.
- [ ] **GPU Plugin Health**: Verify NVIDIA device plugins are running: `kubectl get pods -n kube-system -l k8s-app=nvidia-gpu-device-plugin`.
- [ ] **Workload Verification**: Launch a test inference request and schedule a short 5-minute dummy fine-tuning job to ensure GPU allocators and networking (e.g., NCCL/RDMA if using multi-node) survived the update.
- [ ] **Cleanup**: Remove the temporary maintenance exclusion to allow future automated patch upgrades.
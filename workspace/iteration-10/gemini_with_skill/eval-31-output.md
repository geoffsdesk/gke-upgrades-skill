Upgrading a 512-node H100 (A3 Mega) cluster with GPUDirect-TCPXO requires strict orchestration. Because your training runs last 2–3 weeks, **you cannot upgrade while a run is active.** GKE only respects PodDisruptionBudgets (PDBs) for up to 1 hour during surge upgrades before force-draining nodes, which would fatally interrupt your training. Furthermore, 512 extra H100s for a blue-green upgrade are almost certainly unavailable, meaning we must use an in-place surge strategy tailored for GPU scarcity.

Here is the comprehensive plan, runbook, and checklist to upgrade your cluster from 1.31 to 1.32 safely.

### The Strategy: Isolate, Checkpoint, and Upgrade
1. **Protect the current run:** Apply a `"no minor or node upgrades"` maintenance exclusion immediately. This blocks the 1.32 upgrade from triggering automatically while your 3-week job runs, but still allows Google to apply critical control plane security patches if necessary.
2. **Validate the networking stack:** GKE tightly couples the NVIDIA driver version to the GKE node version. Upgrading to 1.32 will likely increment your NVIDIA driver and CUDA version. You must validate your NCCL/TCPXO performance in a staging cluster first.
3. **Execute between runs:** Schedule a 24-hour maintenance window *between* training runs. With GKE’s maximum upgrade parallelism of ~20 nodes concurrently, a 512-node pool will take 12–24 hours to upgrade completely.
4. **Surge configuration:** Because H100 surge capacity is likely unavailable, we will use `maxSurge=0` and `maxUnavailable=20` to upgrade nodes in chunks without requiring extra GPU quota.

---

### Phase 1: Pre-Upgrade Protection & Validation

Apply the maintenance exclusion immediately to protect your active workloads.

```bash
# Set variables
CLUSTER_NAME="your-llm-cluster"
ZONE="your-cluster-zone"
POOL_NAME="your-a3-mega-pool"
EXCLUSION_START=$(date -Iseconds)
# Set end time to comfortably after your current run finishes (e.g., 3 weeks from now)
EXCLUSION_END="2024-05-01T00:00:00Z" 

# 1. Apply the exclusion to block minor and node upgrades
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --add-maintenance-exclusion-name "protect-training-run" \
  --add-maintenance-exclusion-start-time $EXCLUSION_START \
  --add-maintenance-exclusion-end-time $EXCLUSION_END \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

**Staging Validation:** Spin up a small 2-node A3 Mega cluster on GKE 1.32. Run your standard NCCL all-reduce benchmark to verify that the GPUDirect-TCPXO DaemonSet, network topology, and your framework's CUDA dependencies are compatible with the 1.32 GPU driver image.

---

### Phase 2: Maintenance Window Runbook

Execute this *only* after your model has checkpointed and the 3-week training run has successfully concluded.

#### 1. Prepare the Cluster
```bash
# Remove the maintenance exclusion to allow upgrades
gcloud container clusters update $CLUSTER_NAME \
  --zone $ZONE \
  --remove-maintenance-exclusion "protect-training-run"

# Cordon the training node pool so no accidental jobs schedule during the upgrade
kubectl cordon -l cloud.google.com/gke-nodepool=$POOL_NAME
```

#### 2. Upgrade the Control Plane
The control plane must be upgraded to 1.32 before the nodes.
```bash
# Upgrade the control plane to 1.32 (will take 15-30 minutes)
gcloud container clusters upgrade $CLUSTER_NAME \
  --zone $ZONE \
  --master \
  --cluster-version "1.32"

# Verify control plane is at 1.32
gcloud container clusters describe $CLUSTER_NAME \
  --zone $ZONE \
  --format="value(currentMasterVersion)"
```

#### 3. Upgrade the A3 Mega Node Pool
We configure the node pool to drain and replace up to 20 nodes at a time (GKE's internal maximum for concurrent node upgrades). This avoids needing 20 extra H100 nodes in reserve.

```bash
# Configure surge settings for zero extra capacity requirements
gcloud container node-pools update $POOL_NAME \
  --cluster $CLUSTER_NAME \
  --zone $ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 20

# Initiate the node pool upgrade
gcloud container node-pools upgrade $POOL_NAME \
  --cluster $CLUSTER_NAME \
  --zone $ZONE \
  --cluster-version "1.32"
```

#### 4. Monitor the Upgrade
Because of the sheer size of the cluster (512 nodes), this will take several hours.
```bash
# Monitor the rolling upgrade progress
watch 'kubectl get nodes -l cloud.google.com/gke-nodepool='$POOL_NAME' -o wide | grep -E "NAME|VERSION"'

# Monitor for stuck draining operations
kubectl get pods -A | grep -v Running | grep -v Completed
```

#### 5. Verify Interconnect and Resume
Once the nodes are upgraded, they will automatically be uncordoned by the GKE upgrade process. Before resuming your 3-week run, validate the network.

```bash
# 1. Verify TCPXO DaemonSets are running on all 512 nodes
kubectl get pods -n kube-system -l k8s-app=nccl-fast-socket -o wide

# 2. Run a quick NCCL sanity test job to confirm bandwidth across the newly upgraded nodes
# (Deploy your standard nccl-tests yaml here)

# 3. Resume your LLM training job from the last checkpoint
```

---

### Large-Scale GPU Upgrade Checklist

```markdown
Pre-Upgrade Checklist
- [ ] Maintenance exclusion ("no minor or node upgrades") applied to protect active 3-week run.
- [ ] GKE 1.32 GPU driver compatibility tested with your ML framework (PyTorch/JAX) in staging.
- [ ] GPUDirect-TCPXO networking validated on a 1.32 staging cluster.
- [ ] Target version 1.32 is available in your cluster's current Release Channel.
- [ ] Upgrade window of 12–24 hours scheduled between training runs.
- [ ] All active jobs finished or checkpointed safely to persistent storage.

Upgrade Execution
- [ ] Maintenance exclusion removed.
- [ ] Control plane successfully upgraded to 1.32.
- [ ] Node pool surge settings confirmed: `maxSurge=0`, `maxUnavailable=20`.
- [ ] Node pool upgrade initiated.
- [ ] Upgrade monitored; no pods stuck in termination (bare pods deleted if blocking).

Post-Upgrade Validation
- [ ] All 512 nodes show as Ready and running 1.32.
- [ ] TCPXO/NCCL fast-socket DaemonSets are healthy on all nodes.
- [ ] NCCL all-reduce benchmark passes with expected bandwidth (e.g., matching 1.31 baselines).
- [ ] Maintenance exclusion ("no minor or node upgrades") RE-APPLIED for the duration of the next 3-week training run.
```

### Important Warning for Next Run
Do not forget to **re-apply the "no minor or node upgrades" exclusion** before you kick off your next 3-week training run. If a 1.32 patch or 1.33 minor upgrade becomes the auto-upgrade target while your job is running, GKE will wait 1 hour and then terminate your H100 pods, destroying weeks of progress. Using persistent exclusions tied to your training schedule is the safest way to operate frontier AI clusters on GKE.
Upgrading a 5,000-node mixed AI/ML cluster from GKE 1.31 to 1.32 requires careful orchestration. Because GPU VMs do not support live migration and surge capacity for H100/A100 machines is typically scarce or non-existent, you cannot rely on standard rolling upgrade defaults. 

Furthermore, GKE processes node upgrades with a maximum parallelism of ~20 nodes at a time. For a 2,000-node pool, this means the upgrade will take **days to complete**.

Here is a comprehensive, phased upgrade plan designed to protect your long-running training jobs and maintain your inference serving capacity.

---

### Critical Considerations for your AI/ML Fleet

1. **GPU Driver & CUDA Coupling:** GKE automatically installs the Nvidia GPU driver associated with the target version (1.32). This may introduce a new CUDA version. You **must** validate your training and inference framework compatibility on the Dev (T4) nodes first.
2. **Surge Capacity Scarcity:** Standard upgrades require temporary extra nodes (`maxSurge`). Because H100 and A100 capacity is tightly constrained (usually via reservations), assume you have **zero surge capacity**. We will use `maxUnavailable` to upgrade in place by intentionally dipping capacity.
3. **Training Job Protection:** Standard GKE upgrades wait only 1 hour for a PodDisruptionBudget (PDB) to release before force-draining. Multi-day H100 training runs will be killed if caught in an upgrade. You must use **maintenance exclusions** to freeze the training pools until a natural checkpoint occurs.
4. **Networking (GPUDirect-TCPX):** Your H100 instances likely use high-performance networking topologies. Ensure replacement nodes land in the proper compact placement groups so RDMA topologies aren't broken post-upgrade.

---

### Phased Upgrade Strategy

#### Phase 1: Control Plane & Initial Validation
The control plane must be upgraded first. This takes about 15–20 minutes and does not disrupt running workloads.
* **Action:** Upgrade control plane to 1.32.
* **Validation:** Ensure all system pods (`kube-system`) and third-party controllers/operators (like Ray or Kueue) are healthy.

#### Phase 2: Services (CPU) & Development (T4)
This phase validates the new version and GPU drivers without risking production ML workloads.
* **CPU Nodes (1,000 nodes):** Use high-surge rolling upgrades (`maxSurge=20, maxUnavailable=0`) to complete quickly. 
* **T4 Dev Nodes (500 nodes):** Upgrade using `maxSurge=0, maxUnavailable=5`. Have your ML engineers deploy test training and inference jobs to verify driver and framework compatibility on 1.32.

#### Phase 3: Inference (A100) - Rolling Upgrade
Inference requires continuous serving. Because A100 surge capacity is likely zero, we will perform a rolling upgrade by removing a small batch of nodes at a time.
* **Strategy:** Set `maxSurge=0, maxUnavailable=10` (or whatever capacity dip your inference SLAs can tolerate). 
* **Behavior:** GKE will cordon and drain 10 nodes, upgrade them, wait for them to become ready, and then move to the next 10. With 1,500 nodes, this will require ~150 batches.

#### Phase 4: Training (H100) - Parallel / Maintenance Gap
You cannot rolling-upgrade a tightly-coupled distributed training job (like LLM pre-training). If one node goes down, the entire job halts.
* **Strategy:** Use a **Maintenance Exclusion** of type `"no minor or node upgrades"` to block GKE from touching the H100 pool.
* **Execution:** 
  1. Wait for training jobs to hit a scheduled checkpoint or completion.
  2. Pause the job orchestrator (scale to zero).
  3. Remove the exclusion and upgrade the entire H100 pool while it is empty/idle. 
  4. Once all 2,000 nodes are on 1.32, resume training from the checkpoint.

---

### Step-by-Step Runbook

#### 1. Pre-flight Setup & Protection
First, protect the H100 training pool from auto-upgrades until you are ready:
```bash
# Add an exclusion to prevent disruptive upgrades on the cluster while planning
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "protect-h100-training" \
  --add-maintenance-exclusion-start-time 2023-10-01T00:00:00Z \
  --add-maintenance-exclusion-end-time 2023-10-30T00:00:00Z \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

#### 2. Upgrade Control Plane
```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.x

# Verify control plane version
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

#### 3. Upgrade CPU Services & T4 Dev Pools
```bash
# CPU Services: Fast surge upgrade
gcloud container node-pools update cpu-services-pool \
  --cluster CLUSTER_NAME --zone ZONE \
  --max-surge-upgrade 20 \
  --max-unavailable-upgrade 0

gcloud container node-pools upgrade cpu-services-pool \
  --cluster CLUSTER_NAME --zone ZONE \
  --cluster-version 1.32.x-gke.x

# T4 Dev nodes: Upgrade in place
gcloud container node-pools update t4-dev-pool \
  --cluster CLUSTER_NAME --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 5

gcloud container node-pools upgrade t4-dev-pool \
  --cluster CLUSTER_NAME --zone ZONE \
  --cluster-version 1.32.x-gke.x
```
*Wait for Dev users to validate CUDA/driver compatibility before proceeding.*

#### 4. Upgrade A100 Inference Pool
```bash
# Configure for safe rolling upgrade with zero extra capacity
gcloud container node-pools update a100-inference-pool \
  --cluster CLUSTER_NAME --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 10  # Adjust based on your serving headroom

gcloud container node-pools upgrade a100-inference-pool \
  --cluster CLUSTER_NAME --zone ZONE \
  --cluster-version 1.32.x-gke.x
```

#### 5. Upgrade H100 Training Pool (During scheduled gap)
When training hits a checkpoint, drain workloads, clear the exclusion, and upgrade:
```bash
# Cordon the training pool so no new jobs schedule
kubectl cordon -l cloud.google.com/gke-nodepool=h100-training-pool

# (Wait for active jobs to finish or checkpoint, then scale them down)

# Remove the maintenance exclusion
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "protect-h100-training"

# Increase upgrade speed (since it's empty, we can push maxUnavailable high)
gcloud container node-pools update h100-training-pool \
  --cluster CLUSTER_NAME --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 20  # GKE maxes out at ~20 concurrently

gcloud container node-pools upgrade h100-training-pool \
  --cluster CLUSTER_NAME --zone ZONE \
  --cluster-version 1.32.x-gke.x

# Uncordon once complete
kubectl uncordon -l cloud.google.com/gke-nodepool=h100-training-pool
```

---

### Checklists

#### Pre-Upgrade Checklist
```markdown
Pre-Upgrade Checklist
- [ ] Cluster: ___ | Mode: Standard | Channel: ___
- [ ] Current version: 1.31.x | Target version: 1.32.x

Compatibility & Infrastructure
- [ ] Target version available in release channel (`gcloud container get-server-config`)
- [ ] GKE 1.31 -> 1.32 release notes reviewed for breaking changes
- [ ] "No minor or node upgrades" maintenance exclusion applied to protect H100 runs
- [ ] Machine Learning frameworks tested locally against GKE 1.32's packaged Nvidia drivers
- [ ] Compact placement and GPUDirect-TCPX configuration verified for compatibility with 1.32

Workload Readiness
- [ ] Inference A100s: PDBs configured, ensuring serving capacity won't dip below SLAs
- [ ] Inference A100s: HPA/autoscaling policies verified to handle temporary capacity drops
- [ ] Training H100s: Checkpointing verified and tested
- [ ] Stateful workloads on CPU pools: PV backups completed
```

#### Post-Upgrade Checklist
```markdown
Post-Upgrade Checklist

Cluster Health
- [ ] Control plane at 1.32: `gcloud container clusters describe CLUSTER_NAME --format="value(currentMasterVersion)"`
- [ ] All node pools at 1.32: `gcloud container node-pools list --cluster CLUSTER_NAME`
- [ ] No nodes in NotReady state: `kubectl get nodes | grep NotReady`
- [ ] System pods healthy: `kubectl get pods -n kube-system`
- [ ] NVIDIA device plugins fully operational: `kubectl logs -n kube-system -l k8s-app=nvidia-gpu-device-plugin`

Workload Health
- [ ] Inference Latency (p95/p99) within pre-upgrade baselines
- [ ] GPUs successfully allocated to pods: `kubectl describe nodes | grep -A 5 "Allocated resources"`
- [ ] Training jobs successfully resumed from checkpoints
- [ ] GPUDirect/RDMA network interfaces verified on H100 pods
```
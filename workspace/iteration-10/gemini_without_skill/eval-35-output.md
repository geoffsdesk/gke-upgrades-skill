Designing a GKE cluster for multi-week Foundation Model (FM) training on H100s (A3 mega/high VMs) requires a fundamental shift from standard microservice architecture. 

For web services, we design for continuous, rolling upgrades. For multi-week FM training, **we design for absolute stasis**, treating the cluster as an immutable, dedicated supercomputer during the run.

Here is the blueprint for configuring a GKE cluster to protect multi-week H100 workloads while maintaining security.

---

### 1. Cluster Configuration & Release Channel
You must use **GKE Standard** (not Autopilot). Autopilot manages nodes for you and will inevitably evict pods for security patching, which is fatal to a tightly coupled MPI/NCCL training ring.

*   **Release Channel:** Use the **Stable Channel** with **Extended Support**. 
    *   *Why:* Extended Support allows you to stay on a minor version for up to 24 months. This dramatically reduces the frequency of mandatory cluster upgrades.
*   **Dataplane V2:** Enable it. It is required for advanced networking and GPUDirect-TCPX, which you will need to saturate the network between H100 nodes.
*   **Zonal vs. Regional:** Use a **Regional Cluster**, but deploy the H100 node pools in a **single specific zone**.
    *   *Why:* The control plane is highly available across the region (protecting against zonal control plane outages), but the GPUs must be in a single zone to utilize Compact Placement Policies for ultra-low latency NCCL communication.

### 2. Maintenance Settings (The "When")
GKE’s default behavior will kill your multi-week run. You must take explicit control of the upgrade schedule.

*   **Disable Node Auto-Upgrades (Crucial):** For your H100 node pools, completely disable auto-upgrades. You will manage node upgrades manually between training runs.
*   **Strict Maintenance Windows:** Configure a maintenance window for the *Control Plane* (e.g., Sunday 02:00 - 06:00). Control plane upgrades do not restart your GPU pods, but they do briefly pause API server availability.
*   **Maintenance Exclusions (The Iron Shield):** When you kick off a 4-week training run, create a **Maintenance Exclusion** for the duration of the run (up to 90 days). 
    *   *Scope:* Apply it to `NO_UPGRADES`. 
    *   *Note:* Google reserves the right to override this for critical zero-day vulnerabilities, which is why checkpointing (Section 5) remains necessary.

### 3. Node Pool Strategy (The "How")
H100 availability is scarce, and quota is strict. You cannot rely on "Surge Upgrades" because you likely do not have the spare quota in your GCP project to spin up a surge H100 node. 

*   **Node Pool Segregation:**
    *   **System Pool:** Create a basic `e2-standard` node pool for `kube-system` pods, operators (like Ray or Kueue), and ingress.
    *   **GPU Pool:** Dedicated A3 node pools. Apply Taints (`nvidia.com/gpu=present:NoSchedule`) to ensure no rogue daemonsets or system pods steal resources or block evictions.
*   **The "Blue/Green" Node Pool Upgrade Strategy:**
    Because you disabled node auto-upgrades, how do you securely patch the OS/NVIDIA drivers?
    1. Wait for the multi-week training run to finish.
    2. Create a *new* node pool (`h100-pool-v2`) with the latest GKE node version.
    3. Run a quick validation job on the new pool to ensure NCCL/GPUDirect TCPX is functioning.
    4. Cordon and delete the old node pool (`h100-pool-v1`).
    5. Start your next multi-week run on the new pool.

### 4. Workload Protection (Kubernetes Native)
Even with cluster-level protections, you must tell Kubernetes how to treat your pods if a node becomes unhealthy or a manual drain is accidentally triggered.

*   **PodDisruptionBudget (PDB):** Set `maxUnavailable: 0` for your training job. This prevents the cluster autoscaler or manual drains from taking down a pod voluntarily. *(Note: GKE will bypass a PDB after 1 hour if a forced upgrade is required, but it protects against human error).*
*   **High Termination Grace Period:** Set `terminationGracePeriodSeconds` to something very high (e.g., `3600` - 1 hour). If a preemption or forced eviction *does* happen, this gives your pod a massive window to intercept the `SIGTERM` signal, synchronize the distributed training ring, and write a final emergency checkpoint to Cloud Storage before the `SIGKILL` is sent.

### 5. Day-One Job Orchestration & Fault Tolerance
No matter how perfectly you configure GKE, **H100 hardware fails**. Running GPUs at 100% utilization for weeks causes hardware degradation, uncorrectable ECC memory errors, and Xid errors. You *will* lose a node during a multi-week run. 

To protect the run, your architecture must include:
*   **Frequent Checkpointing to GCS:** Use Cloud Storage FUSE (baked into GKE) to write model weights to a bucket every few hours.
*   **Use an ML Orchestrator (Kueue or Ray):** Do not use raw Kubernetes `Job` or `StatefulSet` resources. 
    *   If you use **Google Cloud Kueue** (Job queuing) or **Ray**, they are designed to detect a node failure, gracefully tear down the broken distributed ring, wait for GKE to provision a replacement H100 node, and automatically resume the job from the last GCS checkpoint.

### Summary Checklist for Terraform/EKSCTL
* [x] GKE Standard (Regional)
* [x] Stable Release Channel + Extended Support
* [x] Maintenance Window: Strict (e.g., weekends only)
* [x] Maintenance Exclusion: Active during the multi-week run
* [x] Node Auto-Upgrades: `false` (for GPU pools)
* [x] Node Auto-Repair: `true` (Replace dead hardware automatically)
* [x] System Node Pool: `e2-standard`
* [x] GPU Node Pool: `a3-highgpu-8g` (with Compact Placement Policy)
* [x] PDB: `maxUnavailable: 0`
* [x] Pod spec: `terminationGracePeriodSeconds: 3600`
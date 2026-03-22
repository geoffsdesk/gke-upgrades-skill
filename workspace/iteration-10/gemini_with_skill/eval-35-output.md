Designing a GKE environment for multi-week foundation model training on H100 GPUs requires balancing the scarcity of hardware, the strict need for uninterrupted uptime, and the necessity of security patching. 

Because GPU VMs do not support live migration, any node upgrade results in a pod restart. Furthermore, GKE's default pod eviction timeout during upgrades is 1 hour—which is insufficient to protect multi-week training runs using only PodDisruptionBudgets (PDBs). 

To achieve your goals, you must rely on **Release Channels combined with scoped Maintenance Exclusions**. Here is the recommended day-one architecture and configuration strategy.

---

### 1. Cluster Version & Channel Strategy
*   **Cluster Mode:** **GKE Standard**. Standard is required for this level of hardware control, GPUDirect-TCPX configuration, and specific node-pool upgrade strategies.
*   **Release Channel:** **Stable**. The Stable channel ensures you are only receiving the most thoroughly vetted GKE versions, minimizing churn and unexpected deprecations. 
*   *Avoid "No Channel":* Do not use the legacy "No channel" option. It strips you of the advanced granular exclusion controls you need to protect your training runs.

### 2. Maintenance Exclusions (Your Primary Shield)
This is the most critical setting for your cluster. You need to block disruptive node upgrades while allowing the control plane to receive security patches.
*   **The Scope:** Use the **`no_minor_or_node_upgrades`** exclusion scope. 
*   **Why:** This explicitly freezes your H100 node pools and prevents minor version bumps, completely protecting your multi-week runs from eviction. Crucially, it *still allows* automatic control plane security patches to apply in the background, fulfilling your security requirement.
*   **Duration:** Use the persistent `--add-maintenance-exclusion-until-end-of-support` flag so you don't have to manually chain 30-day exclusions.

### 3. Node Pool Upgrade Strategy
When you *do* decide to upgrade between training runs, you need a strategy tailored for H100s. H100 capacity is highly constrained, meaning you likely will not have the quota to provision "surge" replacement nodes.
*   **Surge Configuration:** Set `maxSurge=0` and `maxUnavailable=1` (or higher depending on your batch size tolerance). This drains and updates existing nodes without requiring additional H100 quota, causing a slight temporary dip in capacity rather than an upgrade-blocking quota error.
*   **AI Host Maintenance (Parallel Strategy):** For large training clusters, use GKE's AI Host Maintenance feature. Between training runs, cordon the cluster, apply the `cloud.google.com/perform-maintenance=true` label to all nodes simultaneously, wait ~4 hours for the fleet to update, and then resume training. This minimizes total wall-clock downtime.

### 4. Workload Architecture Best Practices
*   **Mandatory Checkpointing:** Even with exclusions, hardware failures happen. Ensure your LLM training framework frequently saves checkpoints to Cloud Storage. 
*   **PDBs are a buffer, not a guarantee:** Configure PDBs (`maxUnavailable: 0`), but remember GKE will force-drain nodes after 1 hour if an upgrade is triggered. Exclusions are your real protection.
*   **Network / GPU Driver Coupling:** GKE auto-installs GPU drivers matching the GKE version, which can change CUDA versions. High-performance networking like GPUDirect-TCPX (essential for H100s) is tightly coupled to these versions. Always validate the target GKE version on a small staging node pool before lifting your production maintenance exclusion.

---

### Day-One Implementation Runbook

Run these commands when setting up your new cluster to establish this protective baseline.

**1. Enroll in Stable Channel and Set an Off-Peak Window**
*(Even with exclusions, patches will only happen during this window)*
```bash
gcloud container clusters update CLUSTER_NAME \
    --region REGION \
    --release-channel stable \
    --maintenance-window-start 2024-01-01T02:00:00Z \
    --maintenance-window-duration 8h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA,SU"
```

**2. Apply the Persistent "No Minor or Node" Exclusion**
*(This protects your training jobs continuously until the GKE version reaches End of Support)*
```bash
gcloud container clusters update CLUSTER_NAME \
    --region REGION \
    --add-maintenance-exclusion-name "protect-training-runs" \
    --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
    --add-maintenance-exclusion-until-end-of-support
```

**3. Configure Zero-Surge Upgrade Strategy on the H100 Node Pool**
*(Prevents quota errors when you eventually perform manual upgrades)*
```bash
gcloud container node-pools update h100-training-pool \
    --cluster CLUSTER_NAME \
    --region REGION \
    --max-surge-upgrade 0 \
    --max-unavailable-upgrade 1
```

### How to execute an upgrade safely
When a multi-week run finishes and you are ready to adopt a new GKE version:
1. Ensure the training job has successfully checkpointed and stopped.
2. Remove the maintenance exclusion temporarily:
   `gcloud container clusters update CLUSTER_NAME --region REGION --remove-maintenance-exclusion "protect-training-runs"`
3. Manually trigger the minor/node upgrade to the new version.
4. Once the upgrade completes and you verify RDMA/GPUDirect connectivity, recreate the persistent exclusion using step 2 before starting your next multi-week run.
At a scale of 3,000 nodes, an 8-hour maintenance window is mathematically insufficient for a full cluster upgrade. 

Here is the root cause: **GKE currently enforces a maximum upgrade parallelism of ~20 nodes simultaneously**, regardless of your `maxSurge` settings. For 3,000 nodes, GKE must process at least 150 sequential batches. Even if a batch takes only 10 minutes (cordon, drain, detach volumes, boot new node, pull images), that translates to **25+ hours of pure upgrade time**. When your 8-hour window closes, GKE pauses the upgrade and waits until the next Saturday, leading to multi-week fragmented upgrades.

To successfully manage upgrades at this scale—especially with scarce A100/H100 GPU capacity—you need to shift from a single auto-upgrade window to a **staggered, optimized upgrade strategy**.

Here is the blueprint for handling massive AI/ML cluster upgrades.

---

### 1. Optimize Node Pool Upgrade Strategies

Different hardware requires different upgrade mechanics. The default surge settings are likely stalling your GPU pools because GKE is waiting for surge quota that doesn't exist for high-end accelerators.

**For the GPU Pools (A100, H100, L4, T4):**
Because A100 and H100 VMs are in high demand, GKE often cannot provision temporary surge nodes. If your pools are configured with `maxSurge > 0`, the upgrade will stall waiting for capacity. 
*   **Strategy:** Switch to a high `maxUnavailable` and zero surge. This forces GKE to delete nodes *before* recreating them, avoiding quota limits but causing a temporary capacity dip.
*   **Action:** Increase `maxUnavailable` up to the ~20 node GKE parallelism cap (e.g., `10` or `15`) to ensure GKE moves as fast as the system allows.

**For the CPU Pools:**
CPU quota is usually abundant. You can maximize speed here using surge upgrades.
*   **Strategy:** Maximize parallelism by setting `maxSurge` high.
*   **Action:** Set `maxSurge=20` and `maxUnavailable=0`. 

### 2. Redesign Your Maintenance Windows

You have two options for dealing with the 25+ hour required duration:

**Option A: The 48-Hour Weekend Window (Recommended)**
Extend the maintenance window to span the entire weekend. This gives GKE the unbroken time it needs to churn through 3,000 nodes.
*   Change the window to start Friday at 10 PM and run for 48 hours.

**Option B: Manual Staggering via Exclusions**
If you cannot tolerate a 48-hour window, you must stop relying on the single auto-upgrade window and instead sequence the pools manually during gaps in your training schedules.
1. Apply a **"no minor or node upgrades"** maintenance exclusion to the cluster to prevent auto-upgrades from interrupting long-running jobs.
2. Manually trigger node pool upgrades one by one (or in small batches) using `gcloud container node-pools upgrade`. Manual upgrades *bypass* maintenance windows and exclusions, giving you control over exactly what upgrades and when.

### 3. Protect Long-Running AI Training Jobs

For your A100 and H100 pools, node upgrades require pod restarts (GPUs do not support live migration). GKE's default behavior will force-evict pods after 1 hour if they don't drain naturally. 
*   Ensure all large training jobs (LLMs, etc.) have **checkpointing enabled** before any upgrade weekend.
*   If a training run spans multiple weeks, use the **"no minor or node upgrades" exclusion** to freeze the cluster version entirely until the campaign finishes. This allows the control plane to receive security patches but completely freezes node disruptions.

### 4. Upcoming Feature to Watch: Nodepool Upgrade Concurrency

*Note: GKE is releasing Nodepool Upgrade Concurrency for auto-upgrades (Preview, April 2026).* Once available to your cluster, GKE will process multiple node pools simultaneously rather than sequentially. This will dramatically reduce your 25-hour baseline, but until then, you must optimize per-pool settings.

---

### Actionable Runbook

Run these commands to reconfigure your cluster for large-scale success.

#### Step 1: Fix GPU Pool Settings (Do this for A100, H100, L4, T4)
*Replaces surge with aggressive unavailability to bypass quota exhaustion.*
```bash
# Repeat for each GPU node pool
gcloud container node-pools update GPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 15
```

#### Step 2: Fix CPU Pool Settings
*Maximizes parallel replacement for standard compute.*
```bash
# Repeat for each CPU node pool
gcloud container node-pools update CPU_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 20 \
  --max-unavailable-upgrade 0
```

#### Step 3: Expand the Maintenance Window
*Expands the window to 48 hours starting Friday night (adjust times to UTC as needed).*
```bash
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --maintenance-window-start 2023-10-20T22:00:00Z \
    --maintenance-window-duration 48h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=FR"
```
*(Note: Using the modern `--maintenance-window-duration` syntax)*

#### Alternative Step 3: Manual Execution (If you prefer manual sequencing)
If you decide to manually orchestrate the upgrade instead of widening the window, freeze the cluster first, then upgrade manually:

```bash
# 1. Add exclusion to block automatic node upgrades (up to the version's End of Support)
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "freeze-for-manual-orchestration" \
  --add-maintenance-exclusion-start-time 2023-10-01T00:00:00Z \
  --add-maintenance-exclusion-end-time 2024-04-01T00:00:00Z \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# 2. Upgrade the control plane manually
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION

# 3. Upgrade node pools manually (this overrides the exclusion)
gcloud container node-pools upgrade CPU_POOL_1 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```
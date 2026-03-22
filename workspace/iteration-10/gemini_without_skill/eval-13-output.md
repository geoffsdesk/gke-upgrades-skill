To safely upgrade your GKE cluster without killing your 8-16 hour batch jobs, you must **avoid GKE's default Surge Upgrade strategy**. 

By default, Surge Upgrades will cordon a node, attempt to drain it, and if the pods are not gone after **1 hour**, GKE will forcefully terminate them. 

To bypass this and protect your 16-hour workloads, you have two excellent options: **Blue-Green Node Pool Upgrades** (native to GKE) or a **Manual Node Pool Migration**.

Here is how to handle both approaches.

---

### Option 1: Blue-Green Upgrades with an Extended Soak Time (Recommended)

GKE supports Blue-Green upgrades for node pools. In this strategy, GKE provisions a completely duplicate set of nodes running the new version (1.31). It then cordons the old nodes so no *new* jobs schedule there, but allows existing jobs to finish. 

By default, GKE only waits 1 hour before deleting the old nodes, but **you can configure this soak time for up to 7 days**.

**Steps:**
1. **Upgrade your Control Plane first:** The control plane upgrade takes a few minutes and does *not* disrupt running workloads on worker nodes.
   ```bash
   gcloud container clusters upgrade CLUSTER_NAME --master --cluster-version 1.31
   ```
2. **Trigger the Blue-Green Node Pool upgrade:** Set the soak time to `24h` to give your 16-hour jobs plenty of buffer.
   ```bash
   gcloud container node-pools update NODE_POOL_NAME \
       --cluster CLUSTER_NAME \
       --strategy=BLUE_GREEN \
       --blue-green-node-pool-soak-time=24h \
       --blue-green-batch-node-count=1 # Or adjust based on your cluster size
   ```

*Note: Because Blue-Green provisions a duplicate set of nodes, you must have enough Compute Engine quota (CPU, IP addresses, etc.) in your GCP project to temporarily double your cluster size.*

---

### Option 2: Manual Node Pool Migration (Maximum Control)

If you don't have the quota to double your node pool size all at once, or if you simply want ultimate manual control over the process, you can migrate pools manually.

**Steps:**
1. **Upgrade your Control Plane to 1.31** (same as step 1 above).
2. **Create a new Node Pool running 1.31:**
   ```bash
   gcloud container node-pools create new-pool-1-31 \
       --cluster CLUSTER_NAME \
       --node-version 1.31 \
       # ... add your standard node pool flags (machine type, etc.)
   ```
3. **Cordon the old Node Pool (1.30):** This prevents any new jobs from scheduling on the old nodes. New jobs will automatically spin up on the new 1.31 nodes.
   ```bash
   kubectl get nodes -l cloud.google.com/gke-nodepool=OLD_NODE_POOL_NAME -o name | xargs kubectl cordon
   ```
4. **Wait for jobs to finish:** Monitor your existing batch jobs. Once your monitoring tools show that the 1.30 nodes are empty (or only running DaemonSets/kube-system pods), you can safely delete the old pool.
5. **Delete the old pool:**
   ```bash
   gcloud container node-pools delete OLD_NODE_POOL_NAME --cluster CLUSTER_NAME
   ```

---

### Crucial Best Practices for your Setup

*   **Set Maintenance Windows / Exclusions:** Because you are on the Regular release channel, Google will eventually force an automatic node upgrade. If this happens while a job is running, it will use the default Surge strategy (which has the 1-hour kill limit). You should configure a **Maintenance Exclusion** to block automated upgrades until you execute one of the controlled methods above.
*   **Do not rely on `terminationGracePeriodSeconds`:** Setting this to 16 hours on your Pod spec will *not* save you during a default GKE node upgrade. The node upgrade timeout (1 hour) will override the pod's grace period and forcefully kill it.
*   **Job Resiliency:** Even with these protections, underlying VMs can fail (hardware issues, live migrations). Ensure your batch processing architecture supports resuming from checkpoints or idempotency whenever possible.
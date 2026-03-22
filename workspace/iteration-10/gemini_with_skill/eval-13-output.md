To safely upgrade your GKE Standard cluster without killing your 8–16 hour batch jobs, you need to bypass GKE's default upgrade behavior. 

By default, GKE uses a **Surge upgrade** strategy. During a surge upgrade, GKE respects PodDisruptionBudgets (PDBs) and graceful termination periods for a **maximum of 1 hour**. If your job is still running after 1 hour, GKE will forcefully terminate it to proceed with the upgrade. 

To solve this, you should combine **Maintenance Exclusions** (to control exactly *when* the upgrade happens) with GKE's **Autoscaled Blue-Green upgrade strategy** (which is specifically designed for workloads that take 8+ hours to drain).

Here is your comprehensive plan and runbook to execute this safely.

---

### Phase 1: Pause Auto-Upgrades (Immediate Action)
Since you are on the **Regular** release channel, GKE will eventually auto-upgrade your cluster to 1.31. To prevent this from happening while you plan, immediately apply a `no_minor_or_node_upgrades` maintenance exclusion. This blocks the disruptive 1.31 upgrade while still allowing non-disruptive control plane security patches.

```bash
# Set an exclusion to buy you time for planning (e.g., for the next 30 days)
# Replace CLUSTER_NAME, ZONE, and timestamps with your specific details
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "hold-1-31-upgrade" \
  --add-maintenance-exclusion-start-time "2023-10-01T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2023-11-01T00:00:00Z" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

### Phase 2: Choose Your Upgrade Strategy

For 8–16 hour batch jobs, you have two native paths:

**Option A: Autoscaled Blue-Green Upgrade (Recommended)**
This strategy creates a new "green" node pool and cordons the old "blue" pool. As your batch jobs naturally complete on the blue pool over your 8–16 hour window, those old nodes are scaled down. New jobs are scheduled on the updated 1.31 green nodes. This natively supports extended eviction periods without force-killing your jobs.

**Option B: Dedicated Batch Node Pool + Wait-for-drain**
If your batch jobs are mixed with web workloads, it is highly recommended to isolate the batch jobs onto their own node pool. You can quickly surge-upgrade the web node pools, and then use Blue-Green (or schedule a specific maintenance window) exclusively for the batch node pool.

---

### Phase 3: Upgrade Execution Runbook

Once you are ready to perform the upgrade, follow these steps.

#### 1. Upgrade the Control Plane First
The control plane must be upgraded to 1.31 before the nodes. This step is safe and will not evict your batch jobs (API server will have seconds of downtime, but running pods are unaffected).

```bash
# Start the control plane upgrade
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.31

# Verify completion (takes ~15 minutes)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

#### 2. Prepare Your Workloads
Ensure your batch jobs are properly configured to leverage the extended drain times:
* Ensure they are running as K8s `Job` or `CronJob` resources, not bare Pods.
* Set the `terminationGracePeriodSeconds` on the Pod spec to a high enough value to cover the longest possible remaining execution time (e.g., `57600` for 16 hours), though autoscaled blue-green primarily relies on waiting for the pod to naturally complete.
* Ensure you have adequate compute quota in your GCP project, as Blue-Green requires temporarily provisioning additional nodes to run the "Green" pool.

#### 3. Execute Node Pool Upgrade 
Apply the autoscaled blue-green strategy to your node pool. *Note: Autoscaled Blue-Green is currently in preview. If you are using standard Blue-Green, ensure your `node-pool-soak-duration` is set longer than 16 hours.*

```bash
# Configure the node pool to use the blue-green strategy
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --enable-blue-green-upgrade \
  --standard-rollout-policy=batch-node-count=1,batch-soak-duration=10s \
  --node-pool-soak-duration=60000s # ~16.6 hours to allow jobs to finish

# Initiate the node pool upgrade
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31
```

#### 4. Monitor the Drain
During the upgrade, you can monitor the old nodes being cordoned and waiting for jobs to finish.

```bash
# Watch node status (old nodes will show as SchedulingDisabled)
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Check for any stuck pods
kubectl get pods -A | grep -v Running | grep -v Completed
```

#### 5. Post-Upgrade Cleanup
Once the upgrade is complete and all old nodes have drained and been deleted, you can remove the maintenance exclusion so your cluster resumes its normal patch lifecycle on the Regular channel.

```bash
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --remove-maintenance-exclusion-name "hold-1-31-upgrade"
```

### Future Optimization: Checkpointing
For jobs extending up to 16 hours, the safest long-term architecture is to implement **checkpointing** within your batch application. If your jobs can save state every 30-60 minutes and resume upon restart, you can use standard GKE surge auto-upgrades without worrying about custom soak times, as the jobs will simply be evicted, rescheduled, and resume from their last checkpoint.
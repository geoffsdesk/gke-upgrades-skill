Upgrading node pools that utilize Spot VMs introduces a unique set of dynamics, primarily around **capacity availability**. 

*(Note: In GKE Standard, individual node pools are either entirely Spot or entirely On-Demand. I will assume you have separate node pools for your Spot and On-Demand workloads, or are evaluating the Spot-specific pools within your cluster).*

Here are the special considerations and a tailored upgrade plan for moving your Spot node pools from 1.31 to 1.32.

### 1. Spot Capacity and Upgrade Stalls (The Primary Risk)
GKE's default **Surge Upgrade** strategy provisions new "surge" nodes before draining old ones. Because Spot capacity fluctuates based on GCP region/zone demand, GKE might not be able to provision the required surge Spot VMs. 
* **If Spot capacity is unavailable:** The upgrade will stall waiting for those surge nodes to be created.
* **Blue-Green Strategy Warning:** GKE's Blue-Green upgrade strategy temporarily *doubles* the size of your node pool. It is **highly recommended to avoid Blue-Green for Spot node pools**, as acquiring 2x your current Spot capacity at once is a gamble and frequently leads to stalled upgrades.

### 2. Tuning the Surge Strategy for Spot
Because workloads running on Spot VMs are inherently designed to tolerate sudden disruptions, you can leverage the `maxUnavailable` setting to keep the upgrade moving even if Spot capacity is tight.

* **Standard On-Demand Pool:** Typically uses `maxSurge=1 (or more), maxUnavailable=0` to ensure zero capacity loss.
* **Spot Pool Recommendation:** Use `maxSurge=1, maxUnavailable=1` (or higher). By allowing some nodes to be unavailable, GKE can drain and delete an old node *first*, freeing up quota and keeping the upgrade progressing without being strictly blocked by the immediate availability of new Spot capacity.

### 3. Eviction Timeouts vs. Spot Preemption
When GCP preempts a Spot VM natively, your workload gets a maximum of 25 seconds to shut down. However, **during a GKE upgrade**, GKE uses a standard Kubernetes cordon-and-drain process. 
* GKE will respect your Pod Disruption Budgets (PDBs) and `terminationGracePeriodSeconds` for **up to 1 hour** before force-deleting pods.
* Even though they are Spot VMs, overly strict PDBs (e.g., `maxUnavailable: 0`) will still block the upgrade drain process until that 1-hour timeout is reached.

---

## Upgrade Plan: 1.31 to 1.32

Below is the step-by-step runbook and checklist for safely upgrading your control plane and mixed node pools.

### Pre-Upgrade Checklist

```markdown
Pre-Upgrade Checklist
- [ ] Cluster: ___ | Mode: Standard | Channel: ___
- [ ] Current version: 1.31.x | Target version: 1.32.x

Compatibility
- [ ] Target 1.32 version available in release channel (`gcloud container get-server-config --zone ZONE --format="yaml(channels)"`)
- [ ] No deprecated 1.31 APIs in use (Check GKE Deprecation Insights dashboard in the GCP Console)
- [ ] GKE release notes reviewed for 1.32 breaking changes
- [ ] Third-party operators/controllers (e.g., ingress controllers, monitoring) are 1.32 compatible

Workload Readiness
- [ ] PDBs verified: Ensure Spot workloads do not have overly restrictive PDBs that block draining.
- [ ] No bare pods (pods not managed by a Deployment/StatefulSet/Job).

Infrastructure & Strategy
- [ ] Control Plane scheduled to upgrade FIRST (mandatory before node pools).
- [ ] On-Demand Node Pools: Surge settings confirmed (e.g., `maxSurge=2, maxUnavailable=0`).
- [ ] Spot Node Pools: Surge settings confirmed (e.g., `maxSurge=1, maxUnavailable=1` or higher to prevent stalls).
```

### Maintenance Runbook

Replace `CLUSTER_NAME`, `ZONE`, `TARGET_VERSION`, and `NODE_POOL_NAME` with your specific values.

#### 1. Upgrade the Control Plane First
The control plane must be updated to 1.32 before the node pools.
```bash
# Initiate control plane upgrade to 1.32
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION

# Verify the new version (this takes 15-20 minutes)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"
```

#### 2. Configure Upgrade Strategies per Node Pool
Apply different surge settings based on the node pool capacity type.

```bash
# For your ON-DEMAND node pools (Prioritize capacity preservation)
gcloud container node-pools update ON_DEMAND_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0

# For your SPOT node pools (Prioritize upgrade progression over capacity)
gcloud container node-pools update SPOT_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 1
```

#### 3. Upgrade Node Pools
You can upgrade node pools sequentially. It is often best practice to upgrade your On-Demand (stable) pools first, followed by your Spot pools.

```bash
# Upgrade the node pool
gcloud container node-pools upgrade POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

#### 4. Monitor & Troubleshoot Spot Stalls
While the Spot node pool is upgrading, monitor the nodes:

```bash
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool,cloud.google.com/gke-provisioning'
```

**If the Spot upgrade gets stuck:**
1. Check if GKE is waiting for new Spot VMs due to regional stockouts:
   ```bash
   gcloud container operations list --cluster CLUSTER_NAME --zone ZONE --filter="operationType=UPGRADE_NODES"
   ```
2. Check for strict PDBs blocking the drain:
   ```bash
   kubectl get pdb -A
   ```
3. **The Fix:** If it's a capacity issue, you can safely increase the `max-unavailable-upgrade` setting mid-upgrade to allow GKE to terminate old nodes and continue the cycle, or simply wait for Spot capacity to free up in the zone.
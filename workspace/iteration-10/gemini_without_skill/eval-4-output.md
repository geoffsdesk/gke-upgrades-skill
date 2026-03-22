You have good news here: because you are running a **Regional** GKE cluster, **you will not experience API server downtime during the control plane upgrade.**

Here is a detailed breakdown of exactly what happens during the upgrade, followed by the step-by-step commands to perform it safely.

### What Happens During a Regional Control Plane Upgrade?

Unlike Zonal clusters (which have only one control plane VM and experience downtime during upgrades), Regional clusters have **three highly available (HA) control plane replicas** spread out across three different zones within `us-central1`. 

When you trigger a control plane upgrade:
1. **Rolling Update:** GKE upgrades the control plane replicas one at a time.
2. **Continuous API Availability:** While one replica is taken offline, upgraded, and rebooted, the other two replicas continue to serve Kubernetes API requests. The cluster's API endpoint remains fully available.
3. **Workload Impact:** Zero. Your running Pods, Services, and workloads are not interrupted. The Kubernetes scheduler, controller manager, and etcd maintain quorum and function normally.
4. **Minor Client Nuance:** If you have CI/CD pipelines or operators actively communicating with the API server, a connection might drop if the specific replica it was talking to goes down for its upgrade. However, any standard Kubernetes client (like `kubectl` or client-go) is designed to automatically retry and will immediately reconnect to one of the remaining healthy replicas.

### Pre-Flight Safety Checks

Before running the upgrade, you must check for deprecated APIs. Kubernetes 1.32 removes several beta APIs. If your workloads or Helm charts are still calling 1.31 beta APIs, they will break in 1.32.

1. Go to the Google Cloud Console.
2. Navigate to **Kubernetes Engine > Clusters**.
3. Click on your cluster and look at the **Deprecation Insights** tab. Ensure there are no active calls to deprecated APIs before proceeding.

### Step-by-Step Upgrade Commands

*Note: Replace `<CLUSTER_NAME>` with the actual name of your cluster.*

**1. Find the available 1.32 versions in the Regular channel**
Because you are tied to the Regular channel, you need to find the exact 1.32 version available in `us-central1`.
```bash
gcloud container get-server-config \
    --region=us-central1 \
    --channel=regular \
    --format="yaml(channels)"
```
*Look under the `regular` channel output and copy the exact 1.32 version number (e.g., `1.32.1-gke.1000`).*

**2. Trigger the Control Plane (Master) Upgrade**
By passing the `--master` flag, you ensure that **only** the control plane is upgraded, leaving your node pools untouched at 1.31 for now.

```bash
gcloud container clusters upgrade <CLUSTER_NAME> \
    --region=us-central1 \
    --master \
    --cluster-version=<THE_1.32_VERSION_YOU_FOUND>
```
*Gcloud will prompt you to confirm the upgrade. Type `Y` and press Enter. This process typically takes 15 to 30 minutes.*

**3. Verify the Upgrade**
Once the command completes, verify that the control plane is running 1.32:
```bash
gcloud container clusters describe <CLUSTER_NAME> \
    --region=us-central1 \
    --format="value(currentMasterVersion)"
```
You can also run `kubectl version` to verify the server version is now 1.32.

### Next Steps: Node Pools
Once your control plane is successfully upgraded to 1.32, your worker nodes will still be on 1.31. Standard Kubernetes version skew policy allows worker nodes to be up to two minor versions behind the control plane (so a 1.32 control plane and 1.31 nodes are perfectly safe and supported). 

However, because you are on the Regular release channel, GKE will automatically schedule an upgrade for your node pools to match the control plane version shortly after, based on your configured Maintenance Windows.
**Recommendation: You must choose Surge Upgrades.**

For a stateful workload like a Cassandra ring—and specifically because you are using **Local SSDs**—a **Blue-Green upgrade is highly dangerous and should be avoided.** 

Here is the detailed explanation of why, along with the exact configuration and safety measures you need to implement for a safe Surge Upgrade.

---

### Why Blue-Green is the Wrong Choice
1. **Local SSD Data Loss:** Local SSDs are physically attached to the underlying VM. When GKE upgrades a node, the VM is recreated, and **all data on the Local SSD is permanently wiped**. 
2. **Quorum Destruction:** In a Blue-Green upgrade, GKE creates a parallel "green" pool of nodes and migrates workloads over in large batches (or all at once). For Cassandra, moving multiple pods to the "green" pool simultaneously means multiple nodes will wake up with empty Local SSDs. You will lose quorum, resulting in massive data loss or a completely broken database ring.

### Why Surge Upgrades are the Right Choice
Surge upgrades allow you to control the exact velocity of the upgrade. By configuring the surge settings to upgrade **strictly one node at a time**, you allow Cassandra's replication mechanisms to handle the node replacement safely.

When Node A is upgraded:
1. GKE creates a new node (with a blank Local SSD).
2. GKE drains Node A, and the Cassandra pod schedules onto the new node.
3. The Cassandra pod boots up, realizes it has an empty disk, and initiates a node bootstrap/rebuild process to stream data from the other 8 healthy nodes.
4. GKE waits for the new pod to become "Ready" before moving on to upgrade Node B.

---

### Prerequisites for a Safe Surge Upgrade
Because the new node must stream data from the Cassandra ring before it is truly "healthy," you **must** configure Kubernetes to prevent GKE from upgrading the next node too early. 

**1. Pod Disruption Budget (PDB)**
You must apply a PDB to your Cassandra StatefulSet to ensure only one node can be taken down at a time. GKE node upgrades respect PDBs.
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: cassandra-pdb
spec:
  maxUnavailable: 1
  selector:
    matchLabels:
      app: cassandra # replace with your actual label
```

**2. Strict Readiness Probes**
GKE relies on the Pod's Readiness Probe to know when a Surge upgrade step is complete. Your Cassandra container's Readiness Probe **must not return success until the node has finished streaming/bootstrapping data and has fully joined the ring.** If the pod reports as "Ready" while it is still rebuilding data, GKE will tear down the next node, causing overlapping failures.
*(If you are using a standard Cassandra Operator like K8ssandra, this is usually handled for you).*

---

### How to Configure the Surge Upgrade

You need to configure your node pool with **Max Surge = 1** and **Max Unavailable = 0**. 

This tells GKE: *"Create exactly 1 new node, move a pod to it, wait for the pod to be fully ready, delete the old node, and repeat."*

**Using gcloud CLI:**
Run the following command to update your node pool settings:

```bash
gcloud container node-pools update [NODE_POOL_NAME] \
    --cluster=[CLUSTER_NAME] \
    --zone=[COMPUTE_ZONE] \
    --max-surge-upgrade=1 \
    --max-unavailable-upgrade=0
```
*(Note: If your cluster is regional, use `--region` instead of `--zone`)*

**Using the Google Cloud Console:**
1. Go to the **Google Kubernetes Engine** page.
2. Click your cluster name, then go to the **Nodes** tab.
3. Click on your Cassandra node pool.
4. Under the **Upgrade settings** section, click the pencil icon to edit.
5. Select **Surge upgrade**.
6. Set **Maximum surge** to `1`.
7. Set **Maximum unavailable** to `0`.
8. Click **Save Changes**.

### Summary Warning
Upgrading a stateful node pool with Local SSDs is effectively a rolling disaster-recovery exercise for Cassandra. Because the data on the local disk is destroyed during the upgrade, the cluster *must* rebuild the data over the network 9 separate times. Ensure your cluster has sufficient network bandwidth and CPU overhead to handle the replication traffic during the upgrade window.
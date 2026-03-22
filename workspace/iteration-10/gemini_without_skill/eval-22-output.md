This is a classic Kubernetes behavior and a very common frustration during cluster maintenance. You have accurately diagnosed it as a "musical chairs" scenario. 

Here is a breakdown of exactly why this is happening and the various ways you can fix it, ranging from manual workarounds to fully automated best practices.

---

### **What is happening (The Root Cause)**

The Kubernetes Scheduler is completely blind to your *intent* to upgrade the whole node pool. It only looks at the current state of the cluster. 

If you have a 10-node pool and your upgrade strategy is updating them one at a time (a standard rolling upgrade), the process looks like this to Kubernetes:
1. Node 1 is **cordoned** (marked unschedulable) and **drained**.
2. The Pods on Node 1 are evicted.
3. The Scheduler looks for a place to put them. Nodes 2 through 10 are still perfectly healthy, un-cordoned, and likely have available resources. Furthermore, the scheduler might actually *prefer* them because the container images are already cached there.
4. The Pods land on Node 2.
5. Node 1 finishes upgrading. 
6. Node 2 is cordoned and drained. The Pods are evicted *again*, and land on Node 3... and so on.

---

### **How to Fix It**

There are three primary ways to solve this, depending on whether you are managing the nodes yourself or using a managed cloud service (EKS, GKE, AKS).

#### **Solution 1: The Blue/Green Node Pool Strategy (Best Practice)**
Instead of doing an "in-place" rolling upgrade of an existing node pool, you replace the entire pool. This guarantees zero "musical chairs" and is the safest way to upgrade.

1. **Create a new node pool** (the "Green" pool) with the upgraded Kubernetes version/AMI. Wait for all new nodes to join the cluster and become `Ready`.
2. **Cordon the entire old node pool** (the "Blue" pool). Run: 
   `kubectl cordon -l your-node-pool-label=old-pool`
   *(Now, NO pods can be scheduled on ANY old node).*
3. **Drain the old node pool.** Because the old nodes are cordoned, the evicted pods have absolutely nowhere to go except your shiny, newly created Green pool.
4. **Delete the old node pool.**

#### **Solution 2: Pre-Cordoning (The Manual/On-Prem Fix)**
If you must do an in-place upgrade and cannot create a parallel node pool, you need to change the order of operations so that the scheduler knows the old nodes are doomed.

1. Provision your new, upgraded nodes (or let your autoscaler spin them up via surge).
2. **Cordon ALL old nodes at the same time.**
3. **Drain the old nodes one by one** (or in batches). 
Because all old nodes are cordoned from the start, an evicted pod from Node A cannot land on Node B. It is forced to wait for a new, upgraded node.

#### **Solution 3: Tweak your Managed Cloud Surge Settings**
If you are using a managed Kubernetes service (like EKS Managed Node Groups, GKE, or AKS) that handles the rolling update for you, the default "batch size" or "surge" settings are likely causing this. 

You need to tell your cloud provider to provision new nodes *before* killing old ones, and to do it in larger batches.

*   **In AWS EKS:** Check your Managed Node Group **Update Config**. Change `maxUnavailable` to a lower number (or percentage) and ensure you have enough extra capacity in your Auto Scaling Group to spin up new nodes *before* the old ones are terminated.
*   **In GCP GKE:** Edit your node pool's upgrade strategy. Use **Surge Upgrades**. Set `maxSurge` to a high number (e.g., 3 or 5) and `maxUnavailable` to 0. This forces GKE to spin up 3 brand new nodes, cordon 3 old nodes, and drain them. The pods will naturally flow to the new surge nodes.
*   **In Azure AKS:** AKS also supports **Max Surge** for node pools. Upgrading your node pool with a `--max-surge` value (e.g., 33%) will ensure new nodes are pre-provisioned to catch the pods.

### **Summary Checklist for your next upgrade:**
1. Do I have **new nodes** ready and waiting *before* the first old node is drained?
2. Are the **remaining old nodes cordoned** so they can't accept evicted pods? 

If the answer to both is yes, your pods will migrate smoothly to the upgraded nodes on the first try.
Your concern is highly justified. Misconfigured PodDisruptionBudgets (PDBs) are the **number one cause of stalled Kubernetes cluster upgrades** and blocked node drains. 

When you drain a node during an upgrade, Kubernetes uses the Eviction API. The Eviction API strictly respects PDBs. If a PDB does not allow a pod to be removed, the node drain will hang indefinitely until it times out.

Here is the audit of your configurations, categorized by risk:

---

### 🚨 HIGH RISK / GUARANTEED TO BLOCK UPGRADES

**Service A (`minAvailable: 100%`)**
*   **Verdict:** **Will block upgrades.**
*   **Why:** You are telling Kubernetes that 100% of your pods must be healthy and running at all times. When the upgrade process tries to drain a node hosting one of these pods, Kubernetes will refuse to evict it because doing so would drop availability to 99% or lower.
*   **The Fix:** Change this to a percentage less than 100% (e.g., `minAvailable: 80%`) or use `maxUnavailable: 1`. If the service *requires* a specific number of pods to function, you must over-provision. For example, if you absolutely need 5 pods running, scale your Deployment to 6 replicas and set `minAvailable: 5`.

**Service B (`maxUnavailable: 0`)**
*   **Verdict:** **Will block upgrades.**
*   **Why:** This is mathematically identical to `minAvailable: 100%`. You are telling the cluster that zero pods are allowed to be taken down voluntarily. The node drain process will completely halt when it encounters a node hosting this pod.
*   **The Fix:** Change this to `maxUnavailable: 1` (or higher, depending on your replica count). 

---

### ✅ SAFE / OPTIMAL FOR UPGRADES

**Service C (`minAvailable: 2` with 3 replicas)**
*   **Verdict:** **Safe.**
*   **Why:** You have 3 pods, but only require 2 to be available. This leaves a "budget" of 1 disruption. Kubernetes will safely evict one pod, wait for it to be rescheduled on a new, upgraded node, wait for its readiness probe to pass, and *only then* move on to evict the next pod. 

**Service D (`maxUnavailable: 1` with 5 replicas)**
*   **Verdict:** **Safe.**
*   **Why:** You are explicitly telling Kubernetes it is allowed to take down exactly 1 pod at a time. The upgrade process will smoothly roll through your nodes, moving one pod at a time. You will always have 4 healthy pods serving traffic. 

*(Note: `maxUnavailable` is generally preferred over `minAvailable` because it safely adapts if you dynamically scale your replicas up or down).*

---

### ⚠️ Hidden "Safe PDB" Traps to Watch Out For

Even though Services C and D have safe PDBs, they can *still* block your upgrade if the following conditions are not met:

1.  **Readiness Probes are failing:** When Kubernetes evicts a pod, it reschedules it. It will not evict the *next* pod until the newly rescheduled pod passes its Readiness Probe. If your new pod crashes or fails its probe, the PDB disruption budget drops to 0, and the upgrade stalls.
2.  **Not enough cluster capacity:** If you drain a node, the pods need somewhere to go. If your cluster is completely full and the evicted pod gets stuck in a `Pending` state, the budget drops to 0, and the upgrade stalls. Ensure you have enough slack capacity (or Cluster Autoscaler configured) before starting the upgrade.
3.  **Single-node bottlenecks:** If you use strict `podAntiAffinity` rules and don't have enough nodes to satisfy them during the upgrade, pods will get stuck in `Pending`.

### Summary Recommendation
Immediately patch **Service A** and **Service B** before attempting your upgrade. Change them both to `maxUnavailable: 1`. This provides the highest level of safety while still allowing the Kubernetes scheduler to cycle the pods across nodes during the upgrade process.
Upgrading a Kubernetes cluster underneath a stateful, distributed system like Elasticsearch requires careful coordination between Kubernetes orchestrations (Node Draining) and Elasticsearch's internal clustering mechanics (Shard Allocation and Quorum).

Because your data nodes use Regional `pd-ssd` Persistent Volumes, your data is replicated across two zones. However, detaching a PV from a dying node and attaching it to a new node takes time. If Elasticsearch isn't prepared for this delay, it will attempt to rebalance shards, causing massive I/O bottlenecks, network saturation, and potential availability loss.

Here is the comprehensive, step-by-step guide to upgrading your GKE cluster from 1.31 to 1.32 with zero downtime and zero data loss.

---

### Phase 1: Preparation & Safeguards (Do Not Skip)

Before clicking "Upgrade" in GKE, you must ensure Kubernetes respects Elasticsearch's availability requirements.

**1. Verify Pod Disruption Budgets (PDBs)**
GKE respects PDBs during node upgrades. You must have PDBs configured to prevent GKE from draining too many nodes simultaneously.
*   **Master Nodes:** `maxUnavailable: 1` (Ensures 2 out of 3 masters are always up to maintain quorum).
*   **Data Nodes:** `maxUnavailable: 1` (Ensures only one data node restarts at a time).
*   **Coordinating Nodes:** `maxUnavailable: 1` or `minAvailable: 1` (Ensures traffic can always be routed).

**2. Verify Readiness Probes**
Ensure your Elasticsearch pods have a strict `readinessProbe`. GKE will wait for the newly upgraded pod to become "Ready" before moving to the next node. For data nodes, the probe should ideally check `_cluster/health` and wait for status `yellow` or `green`.

**3. Check Termination Grace Period**
Elasticsearch needs time to flush memory to disk before shutting down. Check your StatefulSets and ensure `terminationGracePeriodSeconds` is set to at least `120` (preferably `300`).

**4. Take an Elasticsearch Snapshot**
Take a manual snapshot of your cluster to your snapshot repository (e.g., GCS bucket) just in case.
```bash
curl -X PUT "localhost:9200/_snapshot/my_gcs_repository/pre-k8s-1-32-upgrade?wait_for_completion=true"
```

**5. Set GKE Node Pool Upgrade Strategy**
Ensure all your node pools are configured to use **Surge Upgrades** with:
*   `maxSurge: 1`
*   `maxUnavailable: 0`
This forces GKE to provision a *new* node before draining the old one, vastly reducing the time your pod is offline waiting for compute resources.

---

### Phase 2: Upgrade the GKE Control Plane

Upgrade the GKE Control plane from 1.31 to 1.32.
*   **Impact:** Zero downtime for workloads. The Kubernetes API will experience minor blips, but Elasticsearch pods communicate directly with each other, so they will be completely unaffected.

---

### Phase 3: Upgrade Coordinating Node Pool

Because coordinating nodes are stateless (they don't hold PVs or cluster state), they are the safest place to start.

1.  Trigger the GKE Node Pool upgrade for the **Coordinating Node Pool**.
2.  Because of your PDB, GKE will surge one node, drain one pod, wait for the new pod to become ready (handling traffic), and then proceed to the second node.
3.  **Monitor:** Watch your ingress controllers / load balancers to ensure API requests are flowing successfully.

---

### Phase 4: Upgrade Master Node Pool

Master nodes hold cluster state but not massive amounts of data. They restart very quickly.

1.  Trigger the GKE Node Pool upgrade for the **Master Node Pool**.
2.  GKE will take down Master A. Masters B and C will maintain quorum.
3.  The PV will detach, reattach to the new node, and Master A will start.
4.  GKE waits for Master A to become Ready (meaning it rejoined the cluster).
5.  GKE proceeds to Master B, then C.
6.  **Monitor:** Tail the logs of the active master node or watch `_cluster/health` to ensure the cluster state remains stable and nodes successfully drop and rejoin.

---

### Phase 5: Upgrade Data Node Pool (The Critical Path)

This is the phase where you must alter Elasticsearch's behavior manually before letting GKE do its job.

By default, if a data node goes offline for more than 1 minute, Elasticsearch assumes it is dead and begins aggressively replicating its shards to the remaining 4 nodes. You must stop this behavior during the upgrade.

**1. Disable Shard Allocation**
Tell Elasticsearch NOT to rebalance or recreate missing replicas while nodes are rebooting.
```bash
curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}
'
```
*(Note: Setting it to `primaries` ensures that if a primary shard fails, a replica is still promoted to primary to maintain availability, but no new replicas are built.)*

**2. Perform a Global Flush**
Flush the transaction logs to disk. This makes the shard recovery process infinitely faster when the pod restarts.
```bash
curl -X POST "localhost:9200/_flush"
```

**3. Trigger the Data Node Pool Upgrade in GKE**
Initiate the upgrade for the Data node pool to 1.32.

**What will happen under the hood:**
1. GKE creates a new node (Surge).
2. GKE sends SIGTERM to Data Node 1.
3. Elasticsearch receives SIGTERM, stops accepting connections, and gracefully exits.
4. The Pod is terminated. The Regional `pd-ssd` detaches.
5. The Pod is scheduled on the new Node.
6. The Regional `pd-ssd` attaches to the new node (this is generally fast, but because it's regional, if GKE schedules the pod in the *other* zone, it will attach instantly there).
7. Elasticsearch starts, reads the disk, and tells the Master: "I am back, and I have these shards."
8. Because allocation is disabled, Elasticsearch skips network copying and instantly initializes the local shards from disk.
9. Pod becomes Ready. GKE moves to Data Node 2.

**4. Monitor the Upgrade**
During this process, your cluster health will fluctuate to `Yellow` (because replicas are temporarily offline while a node reboots). **This is normal.** Wait for GKE to finish the entire node pool.

**5. Re-enable Shard Allocation**
Once all 5 data nodes are upgraded and running, re-enable standard Elasticsearch routing.
```bash
curl -X PUT "localhost:9200/_cluster/settings" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": null
  }
}
'
```

**6. Wait for Cluster Green**
Elasticsearch will now perform a quick check, realize all shards are exactly where they belong, and the cluster health will return to `Green`.

---

### Summary Checklist
* [ ] Verify PDBs (`maxUnavailable: 1`).
* [ ] Verify `readinessProbes` and `terminationGracePeriodSeconds` (>= 120s).
* [ ] Set GKE Node pools to Surge Upgrade (Surge 1, Unavailable 0).
* [ ] Take ES Snapshot.
* [ ] Upgrade Control Plane.
* [ ] Upgrade Coordinating Pool.
* [ ] Upgrade Master Pool.
* [ ] Disable ES Shard Allocation (`primaries`).
* [ ] Flush ES (`_flush`).
* [ ] Upgrade Data Pool.
* [ ] Re-enable ES Shard Allocation (`null`).
* [ ] Verify Cluster Health is Green.
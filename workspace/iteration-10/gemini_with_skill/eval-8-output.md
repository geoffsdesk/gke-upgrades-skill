For your specific environment—a 9-node Cassandra ring using **Local SSDs**—I strongly recommend a **Conservative Surge Upgrade** over a Blue-Green upgrade. 

Here is why:
Because you are using Local SSDs, your storage is physically tied to the node. When a pod is evicted and rescheduled to a new node, it starts with an empty drive. Cassandra must then stream data from other replicas to rebuild that node. 

If you use a **Blue-Green strategy**, GKE will create 9 new "green" nodes, cordon the 9 "blue" nodes, and begin draining pods. Moving the entire ring to empty nodes during a single transition window puts massive rebuild stress on the database and risks data loss if multiple nodes rebuild simultaneously. 

A **Conservative Surge Upgrade** (`maxSurge=1`, `maxUnavailable=0`) coupled with a strict PodDisruptionBudget (PDB) forces GKE to replace exactly one node at a time. GKE will wait for the new Cassandra pod to start, rebuild its Local SSD data, rejoin the ring, and become "Ready" before it is allowed to evict the next node.

Here is the plan and runbook to execute this safely.

---

### Critical Prerequisites

Before running the upgrade, you must ensure two things are configured in your cluster, as GKE relies on Kubernetes primitives to know when it is safe to proceed:

1. **PodDisruptionBudget (PDB):** You must have a PDB targeting your Cassandra pods with `maxUnavailable: 1`. This physically blocks GKE from taking down a second Cassandra node while the first one is rebuilding.
2. **Strict Readiness Probes:** Your Cassandra pods must have a `readinessProbe` that only returns `true` **after** the node has finished bootstrapping its data and successfully joined the ring (e.g., via `nodetool status`).

*Note on PDB timeouts:* GKE respects PDBs for up to **1 hour** during a surge upgrade. If rebuilding a single Cassandra node takes longer than 60 minutes, GKE may force-evict the next node. If your rebuilds take longer than an hour, you should pause auto-upgrades and handle the node replacements manually.

---

### Upgrade Runbook

Replace `CLUSTER_NAME`, `ZONE`, `NODE_POOL_NAME`, and `TARGET_VERSION` with your actual values.

#### 1. Pre-flight Checks
```bash
# Verify the current state of the node pool
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="table(name, currentMasterVersion, nodePools[].version)"

# Verify your Cassandra PDB exists and currently allows 1 disruption
kubectl get pdb -A | grep cassandra

# Verify all 9 Cassandra nodes are currently Ready
kubectl get pods -l app=cassandra -o wide
```

#### 2. Configure Surge Upgrade Strategy
Set the node pool to use conservative surge settings. This requires quota for 1 additional node (to temporarily reach 10 nodes during the rolling upgrade).

```bash
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

#### 3. Initiate the Upgrade
```bash
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version TARGET_VERSION
```

#### 4. Monitor the Rebuild Progress
During the upgrade, monitor both the Kubernetes level and the Cassandra level.

```bash
# Watch the nodes being replaced one by one
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'

# Watch the pods migrating (ensure only ONE is ever pending/rebuilding)
watch 'kubectl get pods -l app=cassandra -o wide'

# (Optional but recommended) Exec into a healthy Cassandra pod to watch the ring rebuild
kubectl exec -it <healthy-cassandra-pod> -- watch nodetool status
```

---

### Pre-Upgrade Checklist

```markdown
Pre-Upgrade Checklist
- [ ] Cluster: ___ | Mode: Standard | Channel: ___
- [ ] Current version: ___ | Target version: ___

Workload & Stateful Readiness
- [ ] Cassandra `maxUnavailable: 1` PDB is applied and active.
- [ ] Cassandra `readinessProbe` accurately reflects node bootstrap/ring join status.
- [ ] Node rebuild time confirmed to be under 1 hour (GKE PDB timeout threshold).
- [ ] Cassandra ring is currently healthy with no pending compactions or offline nodes (`nodetool status`).
- [ ] terminationGracePeriodSeconds is adequate (e.g., 120s+) for Cassandra to flush memory to disk before SIGKILL.

Infrastructure
- [ ] Node pool strategy configured to Surge: `maxSurge=1, maxUnavailable=0`.
- [ ] Compute Engine quota verified (ability to provision 1 extra node for the surge).
- [ ] Target GKE version evaluated for any deprecated APIs affecting your StatefulSet or operators.
- [ ] Maintenance window communicated to stakeholders (this will be a slow upgrade as nodes rebuild 1-by-1).
```

### Post-Upgrade Checklist

```markdown
Post-Upgrade Checklist

Cluster & Pool Health
- [ ] All 9 nodes in the pool are at the target version: `gcloud container node-pools list --cluster CLUSTER_NAME --zone ZONE`
- [ ] All nodes report Ready status: `kubectl get nodes`

Cassandra Health
- [ ] All 9 Cassandra pods are Running and Ready: `kubectl get pods -l app=cassandra`
- [ ] Cassandra ring is fully healthy with all nodes reporting 'UN' (Up/Normal): `kubectl exec <cassandra-pod> -- nodetool status`
- [ ] No data loss or inconsistency detected via application smoke tests.

Cleanup
- [ ] Surge quota automatically released by GKE.
- [ ] Upgrade timing and rebuild durations documented for next time.
```

### Troubleshooting

If the upgrade appears "stuck":
1. **Check the PDB:** If a Cassandra node fails to rebuild, the PDB will block the rest of the upgrade. Check `kubectl get pdb`. If `ALLOWED DISRUPTIONS` is `0`, GKE is waiting for the current node to become Ready.
2. **Check the Pod Logs:** Look at the logs of the newly scheduled Cassandra pod to see why it is failing to join the ring.
3. **Check Quota:** If you see `Pending` pods and no new nodes spinning up, check `kubectl get events --field-selector reason=FailedScheduling` to ensure your GCP project has the capacity to create the +1 surge node.
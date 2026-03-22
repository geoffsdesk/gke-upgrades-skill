Upgrading a heavily stateful workload like Elasticsearch on GKE Standard requires careful orchestration to ensure zero data loss and continuous availability. 

Because Elasticsearch is highly sensitive to split-brain scenarios and data reallocation storms, this upgrade relies heavily on **PodDisruptionBudgets (PDBs)**, **GKE's native node pool upgrade strategies**, and **regional PersistentVolume attachment limits**.

Here is your comprehensive upgrade plan and runbook to safely move from GKE 1.31 to 1.32.

### GKE Upgrade Strategy for Elasticsearch

While GKE's primary value is its **automated upgrade lifecycle**, heavily stateful clusters often require tightly controlled maintenance windows. 
* **Long-term recommendation:** Place this cluster on the **Regular release channel**, configure a strict weekend **Maintenance Window**, and use a **"No minor or node upgrades" maintenance exclusion** to hold off minor version bumps until you are ready to manually trigger them. 
* **Node Pool Upgrade Strategy:** For Elasticsearch, you have two safe options in GKE:
  1. **Conservative Surge (Recommended if quota is tight):** `maxSurge=1, maxUnavailable=0`. GKE will provision one new node, cordon an old one, and safely evict the ES pod. GKE respects PDBs for up to 1 hour during this process.
  2. **Native Blue-Green (Recommended if quota allows):** GKE duplicates the entire node pool, gradually drains the old "blue" pool into the new "green" pool, and allows for an instant rollback if things go wrong.

---

## 📋 Pre-Upgrade Checklist

**GKE & Version Compatibility**
- [ ] Target version 1.32 is available in your release channel (`gcloud container get-server-config`).
- [ ] No deprecated APIs in use for 1.32 (Check GKE Deprecation Insights dashboard).
- [ ] Ensure Elasticsearch operator (if using Elastic Cloud on Kubernetes - ECK) is compatible with Kubernetes 1.32.

**Workload & Stateful Readiness**
- [ ] **PDBs are configured correctly:**
  - Master nodes: `maxUnavailable: 1` (Maintains 2/3 quorum).
  - Data nodes: `maxUnavailable: 1` (Prevents multiple data nodes dropping simultaneously).
  - Coordinating nodes: `maxUnavailable: 1` or `minAvailable: 1`.
- [ ] `terminationGracePeriodSeconds` on ES pods is sufficient (e.g., 120-300 seconds) to allow Elasticsearch to close indices and release file locks gracefully.
- [ ] Elasticsearch snapshot backup is successfully taken to Google Cloud Storage (GCS).
- [ ] Regional `pd-ssd` PVs are healthy. (Note: Regional PDs replicate across *two* zones. Ensure your node pools span at least those two zones so pods can be rescheduled successfully).

---

## 🛠️ Upgrade Runbook

*Replace `CLUSTER_NAME`, `REGION`, and `TARGET_VERSION` (e.g., `1.32.x-gke.x`) with your specific details.*

### Phase 1: Pre-flight checks

Verify your current versions and confirm PDBs are active.
```bash
# Check current control plane and node pool versions
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="table(name, currentMasterVersion, nodePools[].version)"

# Verify PDBs are protecting Elasticsearch (ALLOWED DISRUPTIONS should be 1)
kubectl get pdb -A
```

### Phase 2: Upgrade the Control Plane

The control plane must always be upgraded first. This causes zero downtime for your worker nodes, but the Kubernetes API will be briefly unavailable.

```bash
gcloud container clusters upgrade CLUSTER_NAME \
  --region REGION \
  --master \
  --cluster-version TARGET_VERSION

# Verify success (takes ~15-20 minutes for regional clusters)
gcloud container clusters describe CLUSTER_NAME \
  --region REGION \
  --format="value(currentMasterVersion)"
```

### Phase 3: Application-Level Prep (Elasticsearch)

Before upgrading node pools, prevent Elasticsearch from aggressively rebalancing terabytes of data when a node restarts.

```bash
# Disable shard allocation (run this against your ES cluster API)
curl -X PUT "localhost:9200/_cluster/settings?pretty" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "primaries"
  }
}'

# Flush translog for faster recovery
curl -X POST "localhost:9200/_flush/synced?pretty"
```

### Phase 4: Upgrade Node Pools (Sequential)

Upgrade order matters. Upgrade **Coordinating** -> **Data** -> **Master** nodes. This ensures the cluster state remains stable while the heaviest components (data nodes) bounce.

For each node pool, apply the **Conservative Surge** strategy to ensure GKE brings up a new node before terminating an old one.

**Step A: Coordinating Nodes**
```bash
# Set conservative surge strategy
gcloud container node-pools update coordinating-pool \
  --cluster CLUSTER_NAME --region REGION \
  --max-surge-upgrade 1 --max-unavailable-upgrade 0

# Initiate upgrade
gcloud container node-pools upgrade coordinating-pool \
  --cluster CLUSTER_NAME --region REGION \
  --cluster-version TARGET_VERSION
```

**Step B: Data Nodes**
*Wait for the Coordinating pool to finish, verify cluster health (`_cluster/health` is yellow/green), then proceed.*
```bash
gcloud container node-pools update data-pool \
  --cluster CLUSTER_NAME --region REGION \
  --max-surge-upgrade 1 --max-unavailable-upgrade 0

gcloud container node-pools upgrade data-pool \
  --cluster CLUSTER_NAME --region REGION \
  --cluster-version TARGET_VERSION
```

**Step C: Master Nodes**
*Wait for Data pool to finish. Master nodes hold the cluster state; upgrading them last ensures minimal disruption.*
```bash
gcloud container node-pools update master-pool \
  --cluster CLUSTER_NAME --region REGION \
  --max-surge-upgrade 1 --max-unavailable-upgrade 0

gcloud container node-pools upgrade master-pool \
  --cluster CLUSTER_NAME --region REGION \
  --cluster-version TARGET_VERSION
```

### Phase 5: Post-Upgrade Validation & Cleanup

Re-enable Elasticsearch shard allocation and verify health.

```bash
# Re-enable full shard allocation
curl -X PUT "localhost:9200/_cluster/settings?pretty" -H 'Content-Type: application/json' -d'
{
  "persistent": {
    "cluster.routing.allocation.enable": "all"
  }
}'

# Check cluster health (wait until it returns to "green")
curl -X GET "localhost:9200/_cluster/health?pretty"
```

---

## 🚑 Troubleshooting

Stateful workload upgrades usually stall for one of three reasons:

**1. Upgrade is stuck waiting on PDBs (Most Common)**
GKE will wait up to 1 hour if a PDB prevents pod eviction. If Elasticsearch hasn't restored cluster health quickly enough, the PDB will block the next node upgrade.
* **Diagnose:** `kubectl get pdb -A` (Look for `ALLOWED DISRUPTIONS = 0`).
* **Fix:** Check Elasticsearch logs to see why the pod isn't rejoining the cluster. If the ES cluster is healthy but K8s is out of sync, temporarily relax the PDB:
  ```bash
  kubectl patch pdb <es-data-pdb> -n <namespace> -p '{"spec":{"maxUnavailable":"100%"}}'
  ```
  *(Remember to revert this after the node migrates!)*

**2. PVC Attachment Issues (FailedAttachVolume)**
Because you use regional `pd-ssd`, the new pod must land in one of the two zones where the disk replica exists. 
* **Diagnose:** `kubectl get events -A --field-selector reason=FailedAttachVolume`
* **Fix:** Verify the replacement node came up in a zone that matches the PV's node affinity rules. GKE scheduler usually handles this automatically, but quota limits in a specific zone can force a node into the wrong zone.

**3. Long Pod Eviction Times**
If Elasticsearch is taking too long to flush data during pod shutdown, GKE will wait up to the `terminationGracePeriodSeconds` limit.
* **Diagnose:** `kubectl get pods | grep Terminating`
* **Fix:** Allow it to complete gracefully. Do not force delete stateful pods unless absolutely necessary, as this can corrupt the Elasticsearch translog.
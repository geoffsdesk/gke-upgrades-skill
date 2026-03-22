Welcome to managing GKE! Because your cluster is enrolled in the **Regular release channel**, GKE actually handles patch upgrades (like moving from one `1.32.x` version to a newer `1.32.y` version) automatically in the background. 

However, running a manual upgrade is a great way to familiarize yourself with the process, take control of the exact timing, or get ahead of the auto-upgrade schedule. 

In GKE Standard, upgrades are a two-step process:
1. **Control Plane (Master):** Must be upgraded first. Workloads keep running, but you won't be able to deploy *new* things for a few minutes while the API server restarts.
2. **Node Pools:** Upgraded second. GKE will safely "cordon and drain" your nodes (move your pods to new nodes) one by one. 

Here is your complete, step-by-step runbook. 

---

### Step 0: Set up your environment variables
To make the commands copy-pasteable, let's set your cluster details as environment variables. Run this in your terminal:

```bash
export CLUSTER_NAME="<REPLACE_WITH_YOUR_CLUSTER_NAME>"
export ZONE="us-west1-b"
```

### Phase 1: Pre-flight Checks
Before changing anything, let's look at the current state of the cluster and find our exact target version.

**1. Check your current cluster and node versions:**
```bash
gcloud container clusters describe $CLUSTER_NAME \
  --zone $ZONE \
  --format="table(name, currentMasterVersion, nodePools[].version)"
```

**2. Find the available 1.32 versions in the Regular channel:**
```bash
gcloud container get-server-config --zone $ZONE --format="yaml(channels)"
```
*Look under the `REGULAR` channel list for the newest `1.32.x-gke.x` version. Copy that exact version string.*

**3. Set your target version variable:**
```bash
export TARGET_VERSION="<REPLACE_WITH_EXACT_VERSION_STRING>" 
# Example: export TARGET_VERSION="1.32.2-gke.1000"
```

**4. Verify cluster health (everything should say "Ready" and "Running"):**
```bash
# Check nodes
kubectl get nodes

# Check for failing pods
kubectl get pods -A | grep -v Running | grep -v Completed
```

**5. Check for overly restrictive Pod Disruption Budgets (PDBs):**
PDBs protect your apps from going down, but if set too strictly, they prevent GKE from upgrading the nodes.
```bash
kubectl get pdb -A
```
*If you see any PDBs where `ALLOWED DISRUPTIONS` is `0`, the upgrade will pause at that app for up to 1 hour before GKE forces it. If this is a production app, coordinate with your team.*

---

### Phase 2: Upgrade the Control Plane
The control plane must be updated first.

**1. Start the control plane upgrade:**
```bash
gcloud container clusters upgrade $CLUSTER_NAME \
  --zone $ZONE \
  --master \
  --cluster-version $TARGET_VERSION
```
*Note: Type `Y` when prompted. This command will take 10–20 minutes to complete. Your running applications will not be disrupted.*

**2. Verify the control plane is updated:**
```bash
gcloud container clusters describe $CLUSTER_NAME \
  --zone $ZONE \
  --format="value(currentMasterVersion)"
```
*(This should now output your `$TARGET_VERSION`)*

---

### Phase 3: Upgrade the Node Pools
Now we upgrade the nodes where your applications actually run. We will use **Surge Upgrades**, which is GKE's default method. It spins up an extra node, moves pods over, and then deletes the old node.

We will configure the surge settings to `maxSurge=1` and `maxUnavailable=0` to ensure no capacity is lost during the upgrade.

#### Upgrading `default-pool`
**1. Configure the surge settings for the pool:**
```bash
gcloud container node-pools update default-pool \
  --cluster $CLUSTER_NAME \
  --zone $ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**2. Trigger the upgrade:**
```bash
gcloud container node-pools upgrade default-pool \
  --cluster $CLUSTER_NAME \
  --zone $ZONE \
  --cluster-version $TARGET_VERSION
```

**3. Watch the progress in a separate terminal window:**
```bash
watch 'kubectl get nodes -o wide -L cloud.google.com/gke-nodepool'
```
*(You will see a new node appear, old nodes get "SchedulingDisabled", and eventually disappear. Wait for the `gcloud` command to finish).*

#### Upgrading `workload-pool`
Once `default-pool` is completely finished, repeat the process for `workload-pool`:

**1. Configure surge settings:**
```bash
gcloud container node-pools update workload-pool \
  --cluster $CLUSTER_NAME \
  --zone $ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**2. Trigger the upgrade:**
```bash
gcloud container node-pools upgrade workload-pool \
  --cluster $CLUSTER_NAME \
  --zone $ZONE \
  --cluster-version $TARGET_VERSION
```

---

### Phase 4: Post-Upgrade Validation
Ensure everything is healthy on the new version.

**1. Confirm all nodes are on the new version and Ready:**
```bash
gcloud container node-pools list --cluster $CLUSTER_NAME --zone $ZONE
kubectl get nodes
```

**2. Confirm system services and workloads are running:**
```bash
# Verify GKE system pods
kubectl get pods -n kube-system

# Verify no application pods are stuck Pending or CrashLoopBackOff
kubectl get pods -A | grep -v Running | grep -v Completed
```

---

### Phase 5: Troubleshooting
If the node pool upgrade seems to "hang" for more than 20-30 minutes on a single node, 99% of the time it is due to one of two things:

1. **A PDB blocking the drain:** GKE is waiting for an app to safely shut down, but the app's Pod Disruption Budget says "do not shut me down." GKE will wait up to 1 hour, then force the eviction.
   * *Check it:* `kubectl get pdb -A`
2. **Resource constraints:** The new replacement node doesn't have enough CPU/Memory to accept the pods from the old node, leaving pods stuck in `Pending`.
   * *Check it:* `kubectl get pods -A | grep Pending` 

If you get completely stuck, you can safely cancel a node pool upgrade. GKE will finish upgrading the current node it's working on and then stop:
```bash
gcloud container operations list --cluster $CLUSTER_NAME --zone $ZONE
# (Find the operation ID for the node upgrade, then you can cancel it via the Google Cloud Console or gcloud)
```
Since you are moving from **1.32 to 1.32**, this is known as a **patch upgrade** (for example, moving from `1.32.1-gke.1000` to `1.32.2-gke.2000`). Patch upgrades contain important security fixes and bug resolutions.

In a GKE Standard cluster, an upgrade happens in two phases:
1.  **The Control Plane (Master):** Google manages this. Upgrading it causes about 5–15 minutes of API downtime (you can't use `kubectl`), but **your applications stay running**.
2.  **The Node Pools:** The actual virtual machines running your apps. GKE will create a new node, move your apps to it, and delete the old node. 

Here is your copy-and-paste runbook.

---

### Step 0: Set Up Your Terminal Variables
To make the rest of the commands copy-and-pasteable, let's define your cluster variables. Run these commands in your terminal (replace `YOUR_PROJECT_ID` and `YOUR_CLUSTER_NAME` with your actual details):

```bash
PROJECT_ID="YOUR_PROJECT_ID"
CLUSTER_NAME="YOUR_CLUSTER_NAME"
ZONE="us-west1-b"

# Log in to Google Cloud (if you haven't already)
gcloud auth login

# Set your project
gcloud config set project $PROJECT_ID

# Get the credentials so kubectl works
gcloud container clusters get-credentials $CLUSTER_NAME --zone $ZONE
```

### Step 1: Pre-Flight Health Check
Before upgrading, ensure your cluster is currently healthy. You don't want to upgrade a broken cluster.

```bash
# Check that all nodes say "Ready"
kubectl get nodes

# Check for any crashing pods (This should ideally return nothing, or only known issues)
kubectl get pods -A | grep -v -E "Running|Completed"
```

### Step 2: Find the Target Version
Since you are on the Regular channel, you need to find the exact patch version available for 1.32 in `us-west1-b`.

Run this command to see available versions:
```bash
gcloud container get-server-config --zone $ZONE --flatten="channels" --filter="channels.channel=REGULAR"
```
Look at the output and find the highest version that starts with `1.32.`. It will look something like `1.32.x-gke.xxxxx`. 

Set that exact version as a variable:
```bash
# REPLACE the version below with the one you found in the previous command!
TARGET_VERSION="1.32.x-gke.xxxxx" 
```

### Step 3: Upgrade the Control Plane (Master)
You must upgrade the Control Plane before the node pools. 

*Note: Your applications will not go down, but your terminal (`kubectl`) will lose connection to the cluster for a few minutes while the master restarts.*

```bash
gcloud container clusters upgrade $CLUSTER_NAME \
    --master \
    --cluster-version $TARGET_VERSION \
    --zone $ZONE
```
*   **Prompt:** It will ask: `Do you want to continue (Y/n)?` Press **Y** and hit Enter.
*   **Wait:** This will take roughly 10 to 15 minutes. Wait for the terminal to say "Updated".

Verify the Control Plane is upgraded:
```bash
gcloud container clusters describe $CLUSTER_NAME --zone $ZONE | grep currentMasterVersion
```

### Step 4: Upgrade Node Pool 1 (`workload-pool`)
Now we upgrade the nodes. We will start with `workload-pool`. GKE uses "Surge Upgrades" by default, meaning it will safely spin up a new node, gracefully drain your pods onto it, and then delete the old node.

```bash
gcloud container clusters upgrade $CLUSTER_NAME \
    --node-pool workload-pool \
    --cluster-version $TARGET_VERSION \
    --zone $ZONE
```
*   **Prompt:** Press **Y** and hit Enter.
*   **Wait:** This can take anywhere from 5 to 30+ minutes depending on how many nodes are in this pool.

### Step 5: Upgrade Node Pool 2 (`default-pool`)
Once `workload-pool` finishes successfully, do the exact same thing for the `default-pool`.

```bash
gcloud container clusters upgrade $CLUSTER_NAME \
    --node-pool default-pool \
    --cluster-version $TARGET_VERSION \
    --zone $ZONE
```
*   **Prompt:** Press **Y** and hit Enter.
*   **Wait:** Wait for the command to finish.

### Step 6: Post-Upgrade Verification
Now that both the Master and the Node Pools are upgraded, let's verify everything is healthy and running the new version.

```bash
# Check that all nodes are on the new TARGET_VERSION and say "Ready"
kubectl get nodes -o wide

# Check that your workloads are running happily
kubectl get pods -A
```

---

### Troubleshooting (Just in case)

**Q: The node pool upgrade has been stuck for a very long time!**
A: This usually happens if you have a `PodDisruptionBudget` (PDB) configured that prevents GKE from moving a pod. GKE will wait 1 hour, and if it still can't move the pod safely, it will forcefully delete it to continue the upgrade. Let it run. 

**Q: Can I roll back?**
A: In GKE, you **cannot** roll back a Control Plane (Master) upgrade. However, you *can* roll back node pools if something goes critically wrong with your apps, though it is rarely needed for patch upgrades. To roll back a node pool, you would downgrade it back to the exact version it was on previously using the same command in Steps 4/5, but passing the older version number.
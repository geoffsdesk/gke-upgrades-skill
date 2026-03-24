You're in a **mixed-version state** with 8 nodes at 1.32 and 12 nodes at the previous version. This is **valid and functional** - your cluster is still operational and workloads continue running normally. Here's your recovery plan:

## Current State Assessment

**Cluster status:** ✅ Functional
- Control plane: 1.32 ✅
- Main workload pool: Mixed (8/20 nodes at 1.32)
- Other pools: Unchanged, awaiting upgrade

**Action needed:** Diagnose the failure cause and choose recovery path.

## Step 1: Diagnose the Failure

```bash
# Check the failed operation details
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE \
  --filter="operationType=UPGRADE_NODES" --limit=5

# Check for stuck pods blocking drain
kubectl get pods -A | grep -E "Terminating|Pending"

# Check PDBs (most common cause)
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# Check resource constraints
kubectl top nodes
kubectl get events -A --field-selector reason=FailedScheduling --sort-by='.lastTimestamp'

# Check current node versions
kubectl get nodes -o wide -L cloud.google.com/gke-nodepool
```

## Step 2: Choose Recovery Path

### **Option A: Resume Upgrade (Recommended)**

Fix the root cause and resume. Most common fixes:

**If PDB is blocking:**
```bash
# Temporarily relax the problematic PDB
kubectl patch pdb PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'

# Resume upgrade
gcloud container node-pools upgrade MAIN_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

**If resource constraints:**
```bash
# Reduce surge to minimal
gcloud container node-pools update MAIN_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Resume upgrade  
gcloud container node-pools upgrade MAIN_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

### **Option B: Rollback (Only if unfixable issue)**

If the root cause can't be resolved:

```bash
# Create new pool at previous version
gcloud container node-pools create main-workload-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version PREVIOUS_VERSION \
  --num-nodes 20 \
  --machine-type MACHINE_TYPE \
  [other original settings]

# Cordon the mixed pool
kubectl cordon -l cloud.google.com/gke-nodepool=MAIN_POOL_NAME

# Migrate workloads gradually
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --grace-period=300

# Delete old pool when migration complete
gcloud container node-pools delete MAIN_POOL_NAME --cluster CLUSTER_NAME --zone ZONE
```

## Step 3: Complete the Fleet Upgrade

Once main pool is resolved:

```bash
# Skip-level upgrade remaining pools (faster than sequential)
gcloud container node-pools upgrade POOL2_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32

gcloud container node-pools upgrade POOL3_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32
```

## Monitoring Recovery

```bash
# Watch node progression
watch 'kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,POOL:.metadata.labels.cloud\.google\.com/gke-nodepool'

# Ensure workloads remain healthy
kubectl get pods -A | grep -v Running | grep -v Completed
```

## Prevention for Next Time

```bash
# Configure conservative surge settings
gcloud container node-pools update POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Review PDB settings before upgrades
kubectl get pdb -A -o custom-columns=NAME:.metadata.name,NAMESPACE:.metadata.namespace,MIN_AVAILABLE:.spec.minAvailable,MAX_UNAVAILABLE:.spec.maxUnavailable
```

**Recommendation:** Start with Option A (resume) - it's simpler and gets all nodes to the same version. Only choose rollback if you discover a critical issue with 1.32 that requires staying on the previous version.

What error message did you see when the upgrade stopped? That will help pinpoint the exact fix needed.
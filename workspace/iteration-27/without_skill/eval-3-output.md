This is a common GKE upgrade issue. Let's diagnose and fix the stuck node pool upgrade systematically:

## Immediate Diagnostics

First, check the upgrade status and any error messages:

```bash
# Check upgrade status
gcloud container operations list --filter="operationType=UPGRADE_NODES" --limit=5

# Get detailed operation info
gcloud container operations describe OPERATION_ID --zone=us-east1

# Check node pool status
kubectl get nodes -o wide
```

## Check Pod Eviction Issues

The most common cause is pods that can't be evicted:

```bash
# Check for pods with disruption issues
kubectl get pods --all-namespaces --field-selector=status.phase=Running

# Look for pods without proper PodDisruptionBudgets
kubectl get pdb --all-namespaces

# Check for pods with restrictive PDBs
kubectl describe pdb --all-namespaces
```

## Common Culprits to Check

1. **PodDisruptionBudgets that are too restrictive:**
```bash
# Find PDBs that might be blocking
kubectl get pdb --all-namespaces -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.spec.minAvailable}{"\t"}{.spec.maxUnavailable}{"\n"}{end}'
```

2. **Pods without proper labels or selectors:**
```bash
# Check pods that might not be covered by deployments
kubectl get pods --all-namespaces -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.metadata.ownerReferences[0].kind}{"\n"}{end}' | grep -v "ReplicaSet\|Job\|DaemonSet"
```

3. **DaemonSets or system pods:**
```bash
# Check DaemonSets that might be problematic
kubectl get ds --all-namespaces
```

## Immediate Fix Options

### Option 1: Temporarily Adjust PodDisruptionBudgets
```bash
# Temporarily make PDBs less restrictive
kubectl patch pdb PDB_NAME -n NAMESPACE -p '{"spec":{"minAvailable":1}}'
```

### Option 2: Force drain problematic nodes
```bash
# Manually drain a stuck node (use carefully)
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --force --grace-period=300
```

### Option 3: Cancel and restart the upgrade
```bash
# Cancel current operation (if completely stuck)
gcloud container operations cancel OPERATION_ID --zone=us-east1

# Restart with surge settings
gcloud container node-pools update POOL_NAME \
    --cluster=CLUSTER_NAME \
    --zone=us-east1 \
    --max-surge=2 \
    --max-unavailable=1
```

## Prevention for Future Upgrades

Create better upgrade settings:

```bash
# Configure node pool for better upgrades
gcloud container node-pools update POOL_NAME \
    --cluster=CLUSTER_NAME \
    --zone=us-east1 \
    --max-surge=3 \
    --max-unavailable=0
```

## Monitor Progress

```bash
# Watch the upgrade progress
watch 'kubectl get nodes -o wide && echo "=== Operations ===" && gcloud container operations list --limit=3'
```

## If All Else Fails

Create a new node pool and migrate:

```bash
# Create new node pool with 1.32
gcloud container node-pools create new-pool \
    --cluster=CLUSTER_NAME \
    --zone=us-east1 \
    --node-version=1.32 \
    --num-nodes=3

# After workloads migrate, delete old pool
gcloud container node-pools delete OLD_POOL_NAME \
    --cluster=CLUSTER_NAME \
    --zone=us-east1
```

Start with the diagnostics to identify the specific blocker, then apply the appropriate fix. The pod eviction issues are usually the culprit in stuck upgrades.
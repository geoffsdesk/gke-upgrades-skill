This is a common GKE node pool upgrade issue. Here's a systematic approach to diagnose and fix it:

## 1. Check Current Upgrade Status

```bash
# Get detailed upgrade status
kubectl get nodes -o wide
gcloud container operations list --filter="operationType=UPGRADE_NODES"

# Check node pool details
gcloud container node-pools describe [NODE_POOL_NAME] \
  --cluster=[CLUSTER_NAME] --zone=us-east1
```

## 2. Identify Pod Draining Issues

The most common cause is pods that can't be evicted. Check for:

```bash
# Look for pods with issues
kubectl get pods --all-namespaces --field-selector=status.phase!=Running

# Check for PodDisruptionBudgets that might be blocking draining
kubectl get pdb --all-namespaces

# Look for pods without proper replica controllers
kubectl get pods --all-namespaces -o wide | grep -v "Deployment\|ReplicaSet\|DaemonSet"
```

## 3. Common Blocking Issues & Solutions

### PodDisruptionBudgets (PDBs)
```bash
# Temporarily relax or delete problematic PDBs
kubectl get pdb --all-namespaces -o yaml > pdb-backup.yaml
kubectl delete pdb [PROBLEMATIC_PDB_NAME] -n [NAMESPACE]
```

### Standalone Pods
```bash
# Delete pods not managed by controllers
kubectl delete pod [POD_NAME] -n [NAMESPACE] --force --grace-period=0
```

### Local Storage/hostPath volumes
```bash
# Check for pods using local storage
kubectl get pods --all-namespaces -o yaml | grep -A5 -B5 hostPath
```

## 4. Force the Upgrade Forward

If pods are stuck, you can:

```bash
# Cancel current upgrade and restart
gcloud container operations cancel [OPERATION_ID]

# Start upgrade with more aggressive settings
gcloud container node-pools upgrade [NODE_POOL_NAME] \
  --cluster=[CLUSTER_NAME] \
  --zone=us-east1 \
  --node-version=1.32 \
  --max-surge=2 \
  --max-unavailable=1
```

## 5. Manual Node Cordon & Drain

For stuck nodes:

```bash
# Identify the nodes being upgraded
kubectl get nodes | grep SchedulingDisabled

# Manually drain problematic nodes
kubectl drain [NODE_NAME] \
  --ignore-daemonsets \
  --delete-emptydir-data \
  --force \
  --grace-period=300
```

## 6. Emergency Recovery Steps

If completely stuck:

```bash
# Create a new node pool with 1.32
gcloud container node-pools create new-pool \
  --cluster=[CLUSTER_NAME] \
  --zone=us-east1 \
  --node-version=1.32 \
  --num-nodes=3

# Migrate workloads gradually, then delete old pool
gcloud container node-pools delete [OLD_POOL_NAME] \
  --cluster=[CLUSTER_NAME] \
  --zone=us-east1
```

## 7. Prevention for Future Upgrades

```yaml
# Add proper PDBs to critical services
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: my-app-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: my-app
```

**Immediate Action:** Check for PodDisruptionBudgets first, as they're the most common cause. If you find restrictive PDBs, temporarily modify them to allow the upgrade to proceed.

Would you like me to help you investigate any specific error messages you're seeing?
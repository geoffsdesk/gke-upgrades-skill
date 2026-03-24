This is a common GKE upgrade issue. Let's diagnose and fix the stuck node pool upgrade systematically.

## Immediate Diagnostics

First, check the current status and identify problem pods:

```bash
# Check upgrade status
gcloud container operations list --filter="status=RUNNING"

# Check node status
kubectl get nodes -o wide

# Find pods that can't be evicted
kubectl get pods --all-namespaces --field-selector=status.phase!=Running
kubectl get pods --all-namespaces -o wide | grep -E "(Pending|Terminating)"

# Check for PodDisruptionBudgets
kubectl get pdb --all-namespaces
```

## Common Causes & Solutions

### 1. **PodDisruptionBudgets (PDBs) - Most Common**
```bash
# Check PDBs that might be blocking drainage
kubectl get pdb --all-namespaces -o yaml

# Look for PDBs with minAvailable >= current replicas
kubectl describe pdb --all-namespaces
```

**Fix:** Temporarily relax PDBs:
```bash
kubectl patch pdb <pdb-name> -n <namespace> -p '{"spec":{"minAvailable":0}}'
# or
kubectl patch pdb <pdb-name> -n <namespace> -p '{"spec":{"maxUnavailable":"50%"}}'
```

### 2. **Pods without Controllers (Naked Pods)**
```bash
# Find pods not managed by deployments/daemonsets
kubectl get pods --all-namespaces -o json | jq -r '.items[] | select(.metadata.ownerReferences == null) | "\(.metadata.namespace)/\(.metadata.name)"'
```

**Fix:** Delete naked pods manually:
```bash
kubectl delete pod <pod-name> -n <namespace> --force --grace-period=0
```

### 3. **Local Storage or hostPath Volumes**
```bash
# Check for pods with local storage
kubectl get pods --all-namespaces -o json | jq -r '.items[] | select(.spec.volumes[]?.hostPath or .spec.volumes[]?.emptyDir) | "\(.metadata.namespace)/\(.metadata.name)"'
```

### 4. **Node Finalizers**
```bash
# Check nodes being upgraded for finalizers
kubectl get nodes -o yaml | grep -A 5 -B 5 finalizers
```

## Quick Resolution Steps

### Option 1: Force Complete the Upgrade
```bash
# Get the operation ID
OPERATION_ID=$(gcloud container operations list --filter="status=RUNNING" --format="value(name)")

# Cancel the stuck operation (if needed)
gcloud container operations cancel $OPERATION_ID --region=us-east1

# Then restart the upgrade
gcloud container node-pools upgrade <POOL_NAME> \
  --cluster=<CLUSTER_NAME> \
  --region=us-east1 \
  --node-version=1.32
```

### Option 2: Force Node Drainage
```bash
# Manually drain problematic nodes
kubectl drain <node-name> \
  --ignore-daemonsets \
  --delete-emptydir-data \
  --force \
  --grace-period=60
```

### Option 3: Emergency Pod Cleanup
```bash
# Force delete stuck terminating pods
kubectl get pods --all-namespaces --field-selector=status.phase=Terminating -o json | \
  jq -r '.items[] | "\(.metadata.namespace) \(.metadata.name)"' | \
  xargs -n2 bash -c 'kubectl delete pod $1 -n $0 --force --grace-period=0'
```

## Production-Safe Approach

1. **Identify the blocker:**
```bash
# Check events for clues
kubectl get events --sort-by=.metadata.creationTimestamp | tail -20

# Check specific node events
kubectl describe node <node-name>
```

2. **Gradual fix:**
```bash
# Scale down problematic deployments temporarily
kubectl scale deployment <deployment-name> --replicas=0 -n <namespace>

# Wait for drainage, then scale back up
kubectl scale deployment <deployment-name> --replicas=<original-count> -n <namespace>
```

## Prevention for Future Upgrades

```bash
# Set proper PDBs before upgrading
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: app-pdb
spec:
  maxUnavailable: 1
  selector:
    matchLabels:
      app: your-app
```

## If All Else Fails

```bash
# Nuclear option - recreate the node pool
gcloud container node-pools create new-pool \
  --cluster=<CLUSTER_NAME> \
  --region=us-east1 \
  --node-version=1.32 \
  --num-nodes=4

# Migrate workloads, then delete old pool
gcloud container node-pools delete <OLD_POOL> \
  --cluster=<CLUSTER_NAME> \
  --region=us-east1
```

Start with the diagnostics to identify the specific blocker, then apply the appropriate fix. Most likely it's PDBs or naked pods preventing drainage.
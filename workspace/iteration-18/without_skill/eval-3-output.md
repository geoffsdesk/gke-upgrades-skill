This is a common GKE node pool upgrade issue. Let's diagnose and fix it systematically:

## 1. Check Pod Disruption Status

First, identify what's preventing pod drainage:

```bash
# Check pods that can't be evicted
kubectl get pods --all-namespaces --field-selector=status.phase=Running -o wide | grep <old-node-names>

# Check for PodDisruptionBudgets that might be blocking drainage
kubectl get pdb --all-namespaces

# Look for pods with disruption issues
kubectl get events --all-namespaces --sort-by='.lastTimestamp' | grep -i "evict\|disrupt"
```

## 2. Common Culprits to Check

### PodDisruptionBudgets (Most Common)
```bash
# Check PDBs that might be too restrictive
kubectl get pdb --all-namespaces -o yaml | grep -A 5 -B 5 "minAvailable\|maxUnavailable"

# Temporarily relax overly restrictive PDBs
kubectl patch pdb <pdb-name> -n <namespace> --type merge -p '{"spec":{"minAvailable":0}}'
```

### DaemonSets
```bash
# Check for DaemonSets that might be blocking
kubectl get ds --all-namespaces
kubectl describe ds <daemonset-name> -n <namespace>
```

### Stuck/Terminating Pods
```bash
# Find pods stuck in terminating state
kubectl get pods --all-namespaces | grep Terminating

# Force delete stuck pods (use carefully)
kubectl delete pod <pod-name> -n <namespace> --force --grace-period=0
```

## 3. Node Pool Upgrade Status
```bash
# Check the current upgrade status
gcloud container operations list --filter="operationType=UPGRADE_NODES" --limit=5

# Get detailed operation info
gcloud container operations describe <operation-id> --region=us-east1
```

## 4. Quick Fixes

### Option A: Fix Pod Issues (Recommended)
```bash
# 1. Temporarily adjust restrictive PDBs
kubectl get pdb --all-namespaces --no-headers | while read ns name rest; do
  kubectl patch pdb $name -n $ns --type merge -p '{"spec":{"minAvailable":null,"maxUnavailable":"50%"}}'
done

# 2. Force drain problematic nodes
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data --force --grace-period=30
```

### Option B: Cancel and Retry (If needed)
```bash
# Cancel the current upgrade if it's completely stuck
gcloud container clusters cancel-operation <operation-id> --region=us-east1

# Wait a few minutes, then retry
gcloud container node-pools upgrade <node-pool-name> \
  --cluster=<cluster-name> \
  --region=us-east1 \
  --node-version=1.32
```

## 5. Monitor Progress
```bash
# Watch the upgrade progress
watch -n 30 'kubectl get nodes -o wide'

# Monitor pod movements
kubectl get events --all-namespaces --sort-by='.lastTimestamp' | tail -20
```

## 6. Prevention for Future Upgrades

```bash
# Set reasonable PDBs before upgrading
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: my-app-pdb
spec:
  maxUnavailable: 25%  # Don't use minAvailable: 100%
  selector:
    matchLabels:
      app: my-app
```

## Most Likely Solution

Based on your symptoms, you probably have PDBs that are too restrictive. Run this to identify and temporarily fix them:

```bash
# Find the problem PDBs
kubectl get pdb --all-namespaces -o custom-columns="NAMESPACE:.metadata.namespace,NAME:.metadata.name,MIN_AVAILABLE:.spec.minAvailable,MAX_UNAVAILABLE:.spec.maxUnavailable"

# Temporarily relax them (replace with actual values)
kubectl patch pdb <restrictive-pdb> -n <namespace> --type merge -p '{"spec":{"minAvailable":null,"maxUnavailable":"50%"}}'
```

The upgrade should resume within 10-15 minutes after fixing the pod drainage issues. Let me know what you find with the diagnostic commands!
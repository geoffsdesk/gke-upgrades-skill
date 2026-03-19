This is a common GKE node pool upgrade issue. Let's diagnose and fix it systematically:

## 1. Check Current Status

```bash
# Check node pool upgrade status
kubectl get nodes -o wide
gcloud container operations list --filter="targetLink:YOUR_CLUSTER_NAME"

# Check which nodes are cordoned/draining
kubectl get nodes --show-labels | grep -E "(SchedulingDisabled|Ready)"
```

## 2. Identify Pod Drainage Issues

The most common cause is pods that can't be evicted:

```bash
# Check for pods with disruption issues
kubectl get pods --all-namespaces --field-selector=status.phase!=Running,status.phase!=Succeeded

# Look for PodDisruptionBudgets that might be blocking drainage
kubectl get pdb --all-namespaces

# Check for pods without proper replica sets (won't be rescheduled)
kubectl get pods --all-namespaces -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.metadata.ownerReferences[0].kind}{"\n"}{end}' | grep -v "ReplicaSet\|DaemonSet\|Job"
```

## 3. Common Fixes

### Fix PodDisruptionBudget Issues
```bash
# Temporarily adjust restrictive PDBs
kubectl patch pdb PDB_NAME -n NAMESPACE --type merge -p '{"spec":{"minAvailable":0}}'

# Or increase maxUnavailable
kubectl patch pdb PDB_NAME -n NAMESPACE --type merge -p '{"spec":{"maxUnavailable":"50%"}}'
```

### Force Drain Stuck Nodes
```bash
# Identify nodes being upgraded
kubectl get nodes -l cloud.google.com/gke-nodepool=YOUR_POOL_NAME

# Force drain specific nodes (use cautiously)
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data --force --grace-period=30
```

### Delete Stuck Pods
```bash
# Find pods stuck in terminating state
kubectl get pods --all-namespaces --field-selector=metadata.deletionTimestamp!=

# Force delete if necessary (last resort)
kubectl delete pod POD_NAME -n NAMESPACE --force --grace-period=0
```

## 4. Address Specific Pod Types

### StatefulSets
```bash
# Check StatefulSet status
kubectl get statefulsets --all-namespaces

# May need to temporarily scale down
kubectl scale statefulset STATEFULSET_NAME --replicas=0 -n NAMESPACE
```

### Singleton Pods (no controllers)
```bash
# Delete pods that won't be recreated
kubectl delete pod POD_NAME -n NAMESPACE
```

## 5. Resume the Upgrade

After fixing drainage issues:

```bash
# Check if upgrade continues automatically
gcloud container operations list --filter="targetLink:YOUR_CLUSTER_NAME" --limit=1

# If stuck, you may need to cancel and restart
gcloud container clusters upgrade YOUR_CLUSTER_NAME --node-pool=YOUR_POOL_NAME --cluster-version=1.30 --zone=us-east1-c
```

## 6. Prevention for Future Upgrades

### Set appropriate PDBs
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: my-app-pdb
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: my-app
```

### Use proper surge settings
```bash
# Configure node pool for better upgrade experience
gcloud container node-pools update YOUR_POOL_NAME \
  --cluster=YOUR_CLUSTER_NAME \
  --zone=us-east1-c \
  --max-surge=3 \
  --max-unavailable=1
```

## 7. If All Else Fails

```bash
# Cancel current upgrade operation
gcloud container operations cancel OPERATION_ID --zone=us-east1-c

# Create new node pool with 1.30 and migrate workloads
gcloud container node-pools create new-pool-130 \
  --cluster=YOUR_CLUSTER_NAME \
  --zone=us-east1-c \
  --node-version=1.30.x-gke.x \
  --num-nodes=4

# Then drain old pool manually and delete it
```

Start with checking the PodDisruptionBudgets and stuck pods - that's the cause in ~80% of cases. Let me know what you find and I can provide more specific guidance!
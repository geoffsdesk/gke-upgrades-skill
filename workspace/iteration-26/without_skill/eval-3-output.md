This is a common GKE node pool upgrade issue. Let's diagnose and fix it systematically:

## 1. Check Pod Disruption Issues

First, identify what's preventing pod drainage:

```bash
# Check pods that might be blocking drainage
kubectl get pods --all-namespaces --field-selector=status.phase=Running -o wide | grep <stuck-node-name>

# Look for pods with disruption budgets
kubectl get pdb --all-namespaces

# Check for pods without proper controllers
kubectl get pods --all-namespaces --field-selector=status.phase=Running -o json | jq '.items[] | select(.metadata.ownerReferences == null or .metadata.ownerReferences == []) | {name: .metadata.name, namespace: .metadata.namespace}'
```

## 2. Common Blocking Scenarios

**DaemonSets blocking drainage:**
```bash
# Check daemonsets that might need tolerations
kubectl get ds --all-namespaces
kubectl describe ds <daemonset-name> -n <namespace>
```

**Pods with restrictive PDBs:**
```bash
# Temporarily relax PDBs if safe to do so
kubectl patch pdb <pdb-name> -n <namespace> --type='merge' -p='{"spec":{"minAvailable":0}}'
```

**Stateful workloads:**
```bash
# Check StatefulSets and their pod management
kubectl get sts --all-namespaces
kubectl get pv,pvc --all-namespaces
```

## 3. Force Drainage if Safe

If you identify the blocking pods and it's safe to proceed:

```bash
# Drain specific nodes manually (use carefully)
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data --force --grace-period=300

# Or cordon and delete specific pods
kubectl cordon <node-name>
kubectl delete pod <pod-name> -n <namespace> --grace-period=300
```

## 4. Check Cluster Resources

```bash
# Ensure cluster has capacity for rescheduled pods
kubectl top nodes
kubectl describe nodes | grep -A 5 "Allocated resources"

# Check for resource quotas
kubectl get resourcequota --all-namespaces
```

## 5. GKE-Specific Checks

```bash
# Check the upgrade operation status
gcloud container operations list --filter="targetLink:your-cluster-name"

# Get detailed operation info
gcloud container operations describe <operation-id> --zone=us-east1

# Check node pool status
gcloud container node-pools describe <node-pool-name> --cluster=<cluster-name> --zone=us-east1
```

## 6. Emergency Resolution Options

If the upgrade remains stuck and you need to proceed:

**Option A: Cancel and retry**
```bash
# Cancel current operation (if possible)
gcloud container operations cancel <operation-id> --zone=us-east1

# Retry with surge settings
gcloud container node-pools update <node-pool-name> \
  --cluster=<cluster-name> \
  --zone=us-east1 \
  --max-surge=3 \
  --max-unavailable=1
```

**Option B: Create new node pool (safest for production)**
```bash
# Create new node pool with v1.32
gcloud container node-pools create new-pool-v132 \
  --cluster=<cluster-name> \
  --zone=us-east1 \
  --node-version=1.32.x \
  --num-nodes=4 \
  --machine-type=<current-machine-type>

# Gradually migrate workloads, then delete old pool
```

## 7. Monitoring and Prevention

```bash
# Monitor the upgrade progress
kubectl get nodes -o wide --watch

# Check events for issues
kubectl get events --sort-by='.lastTimestamp' | tail -20
```

## Quick Action Plan:

1. **Immediate**: Check `kubectl get pdb --all-namespaces` and look for overly restrictive disruption budgets
2. **Identify**: Find pods blocking drainage with the commands above
3. **Resolve**: Address specific blockers (relax PDBs, handle StatefulSets, etc.)
4. **Monitor**: Watch node replacement progress
5. **Escalate**: If still stuck after 30 minutes, consider the new node pool approach

What specific error messages are you seeing in the GKE console or operation logs? This will help narrow down the exact cause.
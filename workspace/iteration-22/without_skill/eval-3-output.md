This is a common GKE upgrade issue. Here's how to diagnose and fix the stuck node pool upgrade:

## 1. Check Node Pool Status and Events

```bash
# Get detailed node pool status
kubectl get nodes -o wide
gcloud container node-pools describe [NODE_POOL_NAME] \
  --cluster=[CLUSTER_NAME] --zone=us-east1

# Check for events
kubectl get events --sort-by=.metadata.creationTimestamp
```

## 2. Identify Pod Drainage Issues

The most common cause is pods that can't be evicted. Check for:

```bash
# Find pods that might be blocking drainage
kubectl get pods --all-namespaces -o wide | grep -E "(Pending|Terminating)"

# Check for PodDisruptionBudgets
kubectl get pdb --all-namespaces

# Look for pods without proper disruption budgets
kubectl get pods --all-namespaces --field-selector=status.phase=Running \
  -o jsonpath='{range .items[*]}{.metadata.namespace}{" "}{.metadata.name}{" "}{.spec.nodeName}{"\n"}{end}' | \
  grep -E "node-being-upgraded"
```

## 3. Common Blocking Issues & Solutions

### A. Pods with PodDisruptionBudgets (PDBs)
```bash
# Check PDB status
kubectl get pdb --all-namespaces -o wide

# Temporarily relax restrictive PDBs
kubectl patch pdb [PDB_NAME] -n [NAMESPACE] --type='merge' \
  -p='{"spec":{"minAvailable":0}}'
```

### B. DaemonSets without proper update strategy
```bash
# Check DaemonSets
kubectl get ds --all-namespaces

# Update DaemonSet strategy if needed
kubectl patch ds [DAEMONSET_NAME] -n [NAMESPACE] --type='merge' \
  -p='{"spec":{"updateStrategy":{"type":"RollingUpdate"}}}'
```

### C. StatefulSets or single-replica deployments
```bash
# Check for single-replica deployments
kubectl get deploy --all-namespaces -o jsonpath='{range .items[?(@.spec.replicas==1)]}{.metadata.namespace}{" "}{.metadata.name}{"\n"}{end}'

# Temporarily scale up critical single-replica deployments
kubectl scale deployment [DEPLOYMENT_NAME] -n [NAMESPACE] --replicas=2
```

## 4. Force Drainage (if needed)

If pods are truly stuck:

```bash
# Get nodes being upgraded
kubectl get nodes --show-labels | grep "node.kubernetes.io/instance-type"

# Force delete stuck pods (use cautiously)
kubectl delete pod [POD_NAME] -n [NAMESPACE] --force --grace-period=0

# Or drain manually with more aggressive settings
kubectl drain [NODE_NAME] --ignore-daemonsets --delete-emptydir-data --force --timeout=300s
```

## 5. Monitor and Resume Upgrade

```bash
# Check upgrade progress
gcloud container operations list --filter="operationType=UPGRADE_NODES"

# If completely stuck, you might need to cancel and retry
gcloud container operations cancel [OPERATION_ID] --zone=us-east1

# Then retry the upgrade
gcloud container node-pools upgrade [NODE_POOL_NAME] \
  --cluster=[CLUSTER_NAME] --zone=us-east1 \
  --node-version=1.32
```

## 6. Prevention for Next Time

Add these to your deployments:
```yaml
# PodDisruptionBudget
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

## Quick Checklist:
- [ ] Check PodDisruptionBudgets
- [ ] Verify no single-replica critical deployments
- [ ] Ensure DaemonSets have rolling update strategy
- [ ] Look for pods with local storage or hostPath volumes
- [ ] Check for pods with anti-affinity rules preventing scheduling

Start with checking PDBs and single-replica deployments - these are the most common culprits for stuck upgrades.
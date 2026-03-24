This is a common issue with GKE node pool upgrades getting stuck during the drain process. Here's how to diagnose and resolve it:

## 1. Check Pod Disruption Issues

First, identify what's preventing pods from draining:

```bash
# Check nodes that are being drained
kubectl get nodes -o wide

# Look for pods that can't be evicted
kubectl get pods --all-namespaces --field-selector=status.phase!=Running

# Check for pods with disruption issues
kubectl get pods --all-namespaces -o json | jq '.items[] | select(.metadata.deletionTimestamp != null) | {name: .metadata.name, namespace: .metadata.namespace, deletion: .metadata.deletionTimestamp}'
```

## 2. Common Blocking Issues

### Pod Disruption Budgets (PDBs)
```bash
# Check PDBs that might be blocking
kubectl get pdb --all-namespaces
kubectl describe pdb --all-namespaces
```

### DaemonSets
```bash
# DaemonSets can block node drainage
kubectl get daemonsets --all-namespaces
```

### Pods with local storage or no controllers
```bash
# Check for standalone pods (not managed by deployments/replicasets)
kubectl get pods --all-namespaces --field-selector=status.phase=Running -o json | jq '.items[] | select(.metadata.ownerReferences == null or (.metadata.ownerReferences | length) == 0) | {name: .metadata.name, namespace: .metadata.namespace}'
```

## 3. Immediate Fixes

### Fix restrictive PDBs temporarily:
```bash
# If PDB is too restrictive, temporarily increase allowed disruptions
kubectl patch pdb <pdb-name> -n <namespace> --type merge -p '{"spec":{"minAvailable":0}}'
```

### Force delete stuck pods (use cautiously):
```bash
# Only for pods that are truly stuck
kubectl delete pod <pod-name> -n <namespace> --force --grace-period=0
```

### Handle DaemonSet pods:
```bash
# DaemonSets usually need to tolerate the upgrade process
kubectl get ds <daemonset-name> -n <namespace> -o yaml | grep -A5 tolerations
```

## 4. Resume the Upgrade

After clearing blocking issues:

```bash
# Check upgrade status
gcloud container operations list --filter="targetLink:clusters/YOUR_CLUSTER_NAME"

# If needed, you can sometimes resume by patching the node pool
gcloud container node-pools describe <node-pool-name> --cluster=<cluster-name> --zone=us-east1
```

## 5. Prevention for Future Upgrades

### Configure appropriate PDBs:
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: my-app-pdb
spec:
  maxUnavailable: 1  # Instead of very restrictive minAvailable
  selector:
    matchLabels:
      app: my-app
```

### Ensure DaemonSets handle updates:
```yaml
spec:
  template:
    spec:
      tolerations:
      - key: "node.kubernetes.io/unschedulable"
        operator: "Exists"
        effect: "NoSchedule"
```

## 6. Nuclear Option (if stuck completely)

If the upgrade is completely stuck:

```bash
# Cancel the current operation (this will rollback)
gcloud container operations cancel <operation-id> --zone=us-east1

# Then retry the upgrade with a different strategy
gcloud container node-pools upgrade <node-pool-name> \
  --cluster=<cluster-name> \
  --zone=us-east1 \
  --node-version=1.32 \
  --max-surge-upgrade=1 \
  --max-unavailable-upgrade=0
```

## Quick Diagnostic Commands

Run these to get immediate insight:

```bash
# Overall cluster status
kubectl get nodes
kubectl get pods --all-namespaces | grep -v Running

# Check for blocking resources
kubectl get pdb --all-namespaces
kubectl get events --all-namespaces --sort-by='.lastTimestamp' | tail -20

# GKE specific operation status
gcloud container operations list --filter="status:RUNNING"
```

Start with checking PDBs and stuck pods - that's usually the culprit. The 1.31→1.32 upgrade itself is generally stable, so it's likely a workload configuration issue preventing proper drainage.
This is a common GKE upgrade issue. Let's diagnose and fix the stuck node pool upgrade systematically.

## Immediate Diagnostics

First, check the upgrade status and identify problematic pods:

```bash
# Check upgrade status
gcloud container operations list --filter="operationType=UPGRADE_NODES"

# Check node pool status
kubectl get nodes -o wide

# Identify pods blocking drain on remaining nodes
kubectl get pods --all-namespaces --field-selector=status.phase!=Succeeded -o wide | grep <old-node-names>

# Check for PodDisruptionBudgets
kubectl get pdb --all-namespaces
```

## Common Culprits & Solutions

### 1. **PodDisruptionBudgets (PDBs)**
Most common cause of stuck drains:

```bash
# Check PDB status
kubectl get pdb --all-namespaces -o yaml

# Temporarily relax overly restrictive PDBs
kubectl patch pdb <pdb-name> -n <namespace> --type='merge' -p='{"spec":{"minAvailable":0}}'

# Or increase maxUnavailable
kubectl patch pdb <pdb-name> -n <namespace> --type='merge' -p='{"spec":{"maxUnavailable":"50%"}}'
```

### 2. **DaemonSets**
Check for DaemonSets without proper update strategy:

```bash
kubectl get daemonsets --all-namespaces

# Fix DaemonSet update strategy if needed
kubectl patch daemonset <ds-name> -n <namespace> --type='merge' -p='{"spec":{"updateStrategy":{"type":"RollingUpdate"}}}'
```

### 3. **StatefulSets with Persistent Volumes**
```bash
kubectl get statefulsets --all-namespaces

# Check for pods with local storage or specific node affinity
kubectl describe pod <stuck-pod> | grep -E "Volumes|Affinity|Tolerations"
```

## Force Resolution Options

### Option 1: Manual Pod Deletion (Safest)
```bash
# Delete stuck pods manually (they'll reschedule on new nodes)
kubectl delete pod <pod-name> -n <namespace> --grace-period=30

# For persistent workloads, ensure they can reschedule
kubectl get pv,pvc --all-namespaces
```

### Option 2: Bypass Drain Protection
```bash
# Cordon and force drain specific nodes
kubectl cordon <node-name>
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data --force --grace-period=30
```

### Option 3: Cancel and Restart Upgrade
If the upgrade is completely stuck:

```bash
# Cancel current upgrade (may not always work mid-operation)
gcloud container operations cancel <operation-id> --region=us-east1

# If cancel doesn't work, try upgrading with different strategy
gcloud container node-pools upgrade <pool-name> \
  --cluster=<cluster-name> \
  --region=us-east1 \
  --node-version=1.30 \
  --max-surge=2 \
  --max-unavailable=0
```

## Prevention for Future Upgrades

Configure your node pool for smoother upgrades:

```bash
# Set better upgrade strategy
gcloud container node-pools update <pool-name> \
  --cluster=<cluster-name> \
  --region=us-east1 \
  --max-surge=3 \
  --max-unavailable=1
```

Add these to your workload manifests:
```yaml
# Add to Deployment/StatefulSet specs
spec:
  template:
    spec:
      terminationGracePeriodSeconds: 30
      # For non-critical workloads
      priority: -1
```

## Emergency Workaround

If nothing else works and you need to complete the upgrade urgently:

1. **Scale down problematic workloads** temporarily:
```bash
kubectl scale deployment <deployment-name> --replicas=0 -n <namespace>
```

2. **Wait for upgrade to complete**

3. **Scale back up** on new nodes:
```bash
kubectl scale deployment <deployment-name> --replicas=<original-count> -n <namespace>
```

## Monitor Progress
```bash
# Watch the upgrade progress
watch kubectl get nodes

# Monitor pod rescheduling
watch kubectl get pods --all-namespaces -o wide
```

Start with checking PDBs - they're the #1 cause of stuck upgrades. Let me know what you find and I can provide more specific guidance!
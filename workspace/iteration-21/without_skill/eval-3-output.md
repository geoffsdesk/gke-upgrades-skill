This is a common GKE node pool upgrade issue. Here's a systematic approach to diagnose and fix it:

## 1. Check Pod Disruption Issues

First, identify what's preventing pod drainage:

```bash
# Check pods that can't be evicted
kubectl get pods --all-namespaces --field-selector=status.phase=Running

# Look for pods with disruption budgets
kubectl get pdb --all-namespaces

# Check for pods stuck in terminating state
kubectl get pods --all-namespaces | grep Terminating
```

## 2. Common Culprits & Solutions

**Pod Disruption Budgets (PDBs):**
```bash
# List all PDBs
kubectl get pdb --all-namespaces -o wide

# Temporarily relax overly restrictive PDBs
kubectl patch pdb <pdb-name> -n <namespace> --type merge -p '{"spec":{"minAvailable":0}}'
```

**DaemonSets without proper update strategy:**
```bash
# Check DaemonSets
kubectl get daemonsets --all-namespaces

# Update strategy if needed
kubectl patch daemonset <ds-name> -n <namespace> -p '{"spec":{"updateStrategy":{"type":"RollingUpdate"}}}'
```

**Pods without proper termination:**
```bash
# Force delete stuck terminating pods (use cautiously)
kubectl delete pod <pod-name> -n <namespace> --force --grace-period=0
```

## 3. Check Node Pool Status

```bash
# Get detailed node pool status
gcloud container node-pools describe <node-pool-name> \
  --cluster=<cluster-name> \
  --zone=us-east1

# Check node conditions
kubectl describe nodes | grep -A 5 "Conditions:"
```

## 4. Immediate Solutions

**Option A: Increase drain timeout**
```bash
# Cancel current upgrade
gcloud container node-pools upgrade <node-pool-name> \
  --cluster=<cluster-name> \
  --zone=us-east1 \
  --cancel

# Restart with longer timeout
gcloud container node-pools upgrade <node-pool-name> \
  --cluster=<cluster-name> \
  --zone=us-east1 \
  --node-version=1.32 \
  --max-surge=1 \
  --max-unavailable=0
```

**Option B: Manual intervention**
```bash
# Cordon and drain nodes manually
kubectl cordon <node-name>
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data --force --grace-period=30
```

## 5. Preventive Measures for Future

Add these to your workload manifests:

```yaml
# Proper PDB
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: my-app-pdb
spec:
  minAvailable: 50%  # or maxUnavailable: 1
  selector:
    matchLabels:
      app: my-app
```

```yaml
# Proper termination in pods
spec:
  terminationGracePeriodSeconds: 30
  containers:
  - name: app
    lifecycle:
      preStop:
        exec:
          command: ["/bin/sh", "-c", "sleep 15"]
```

## 6. Monitor Progress

```bash
# Watch the upgrade
watch 'gcloud container operations list --filter="operationType=UPGRADE_NODES" --limit=5'

# Monitor node status
watch 'kubectl get nodes -o wide'
```

## Quick Emergency Fix

If you need to unblock immediately:

```bash
# 1. Identify problematic pods
kubectl get pods --all-namespaces --field-selector=spec.nodeName=<stuck-node-name>

# 2. Delete non-critical stuck pods
kubectl delete pod <pod-name> -n <namespace> --grace-period=0 --force

# 3. Temporarily relax PDBs
kubectl get pdb --all-namespaces -o name | xargs -I {} kubectl patch {} --type merge -p '{"spec":{"minAvailable":0}}'
```

**Remember to restore your PDBs after the upgrade completes!**

What specific error messages are you seeing in the GKE console or when you run `kubectl get events --sort-by='.lastTimestamp'`?
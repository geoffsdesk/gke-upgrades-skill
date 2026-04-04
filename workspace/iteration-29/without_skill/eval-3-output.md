This is a common issue with GKE node pool upgrades. Let's diagnose and fix this step by step.

## First, check the current state:

```bash
# Check upgrade status
kubectl get nodes
gcloud container operations list --filter="operationType=UPGRADE_NODES"

# Check which pods are blocking drainage
kubectl get pods --all-namespaces --field-selector=status.phase!=Running
kubectl get pods --all-namespaces -o wide | grep -E "(Pending|Terminating)"
```

## Common causes and solutions:

### 1. **PodDisruptionBudgets (PDBs) blocking drainage**
```bash
# Check PDBs
kubectl get pdb --all-namespaces
kubectl describe pdb --all-namespaces

# Look for PDBs with minAvailable too high or maxUnavailable too low
# Temporarily adjust problematic PDBs:
kubectl patch pdb <pdb-name> -n <namespace> --type merge -p '{"spec":{"minAvailable":1}}'
```

### 2. **Pods with no controllers (naked pods)**
```bash
# Find pods without controllers
kubectl get pods --all-namespaces -o json | jq -r '.items[] | select(.metadata.ownerReferences == null) | "\(.metadata.namespace)/\(.metadata.name)"'

# These need manual deletion:
kubectl delete pod <pod-name> -n <namespace>
```

### 3. **Stuck terminating pods**
```bash
# Find terminating pods
kubectl get pods --all-namespaces | grep Terminating

# Force delete if needed (use cautiously):
kubectl delete pod <pod-name> -n <namespace> --grace-period=0 --force
```

### 4. **Nodes in NotReady state**
```bash
# Check node conditions
kubectl describe nodes | grep -A 5 "Conditions:"

# If nodes are stuck, you might need to manually delete them
gcloud container clusters resize <cluster-name> --node-pool <pool-name> --num-nodes <current-num-minus-stuck-nodes> --zone us-east1
```

## Immediate actions to try:

### Option 1: Cancel and restart with surge settings
```bash
# Cancel current upgrade
gcloud container operations cancel <operation-id>

# Configure surge settings for smoother upgrades
gcloud container node-pools update <node-pool-name> \
  --cluster=<cluster-name> \
  --zone=us-east1 \
  --max-surge=3 \
  --max-unavailable=0

# Restart upgrade
gcloud container clusters upgrade <cluster-name> \
  --node-pool=<node-pool-name> \
  --cluster-version=1.32 \
  --zone=us-east1
```

### Option 2: Manual node cordon and drain
```bash
# Get the nodes that need upgrading
kubectl get nodes -l cloud.google.com/gke-nodepool=<node-pool-name>

# For each old node:
kubectl cordon <node-name>
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data --grace-period=300
```

### Option 3: Emergency fix - adjust problematic workloads
```bash
# Scale down deployments temporarily if safe to do so
kubectl scale deployment <deployment-name> -n <namespace> --replicas=<lower-number>

# Or patch PDBs to be less restrictive temporarily
kubectl get pdb --all-namespaces -o yaml > pdb-backup.yaml
kubectl patch pdb <pdb-name> -n <namespace> --type merge -p '{"spec":{"maxUnavailable":"50%"}}'
```

## Prevention for future upgrades:

```bash
# Always set appropriate surge settings
gcloud container node-pools update <node-pool-name> \
  --cluster=<cluster-name> \
  --zone=us-east1 \
  --max-surge=2 \
  --max-unavailable=0

# Review PDBs before upgrades
kubectl get pdb --all-namespaces -o custom-columns=NAMESPACE:.metadata.namespace,NAME:.metadata.name,MIN_AVAILABLE:.spec.minAvailable,MAX_UNAVAILABLE:.spec.maxUnavailable
```

**Start with checking the PDBs and stuck pods - that's the most likely culprit.** If you find the issue, I can help you craft the specific fix. What do you see when you run the diagnostic commands?
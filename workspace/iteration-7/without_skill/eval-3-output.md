This is a common GKE upgrade issue. Let's diagnose and resolve it systematically:

## 1. First, check the upgrade status and identify problematic pods

```bash
# Check cluster upgrade status
gcloud container operations list --region=us-east1

# Check node pool upgrade status
kubectl get nodes -o wide
kubectl describe nodes | grep -A5 -B5 "Conditions"

# Identify pods that can't be evicted
kubectl get pods --all-namespaces --field-selector=status.phase=Running
kubectl get pods --all-namespaces -o wide | grep <old-node-names>
```

## 2. Check for common blocking issues

**PodDisruptionBudgets (most common cause):**
```bash
# List all PDBs
kubectl get pdb --all-namespaces

# Check PDB status
kubectl describe pdb --all-namespaces

# Look for PDBs with 0 allowed disruptions
kubectl get pdb --all-namespaces -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.status.disruptionsAllowed}{"\n"}{end}'
```

**Pods without replica sets/controllers:**
```bash
# Find standalone pods (not managed by deployments/daemonsets)
kubectl get pods --all-namespaces --field-selector=status.phase=Running -o json | jq -r '.items[] | select(.metadata.ownerReferences == null) | "\(.metadata.namespace)\t\(.metadata.name)"'
```

## 3. Common fixes

**Option A: Temporarily relax PodDisruptionBudgets**
```bash
# Temporarily increase allowed disruptions
kubectl patch pdb <pdb-name> -n <namespace> -p '{"spec":{"minAvailable":0}}'

# Or disable temporarily
kubectl patch pdb <pdb-name> -n <namespace> -p '{"spec":{"maxUnavailable":"100%"}}'
```

**Option B: Manually drain problematic pods**
```bash
# Force drain specific nodes
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data --force --grace-period=0

# Or cordon and delete specific pods
kubectl cordon <node-name>
kubectl delete pod <pod-name> -n <namespace> --force --grace-period=0
```

**Option C: Use GKE's surge upgrade (recommended for future)**
```bash
# Cancel current upgrade first
gcloud container operations cancel <operation-id> --region=us-east1

# Start upgrade with surge settings
gcloud container node-pools update <pool-name> \
  --cluster=<cluster-name> \
  --region=us-east1 \
  --max-surge=2 \
  --max-unavailable=0
```

## 4. If the upgrade is completely stuck

**Cancel and restart with better settings:**
```bash
# Cancel current operation
gcloud container operations cancel <operation-id> --region=us-east1

# Wait for cancellation
gcloud container operations wait <operation-id> --region=us-east1

# Restart with optimized settings
gcloud container clusters upgrade <cluster-name> \
  --region=us-east1 \
  --node-pool=<pool-name> \
  --cluster-version=1.32 \
  --max-surge=3 \
  --max-unavailable=1
```

## 5. Prevention for next time

**Set appropriate PDB policies:**
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: my-app-pdb
spec:
  maxUnavailable: 25%  # Instead of minAvailable
  selector:
    matchLabels:
      app: my-app
```

**Configure node pool for better upgrades:**
```bash
gcloud container node-pools create new-pool \
  --cluster=<cluster-name> \
  --region=us-east1 \
  --max-surge=2 \
  --max-unavailable=0 \
  --enable-autoupgrade
```

Start with checking the PDBs - that's the most common culprit. If you find PDBs blocking the drainage, temporarily relax them and the upgrade should proceed. Let me know what you find!